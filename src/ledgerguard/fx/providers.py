from __future__ import annotations

import json
import random
import threading
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from ledgerguard.common.money import FOREIGN_CURRENCIES, apply_bps, parse_decimal_rate_e8
from ledgerguard.common.settings import Settings

INITIAL_RATES_E8: dict[str, int] = {
    "EUR": 497_000_000,
    "USD": 457_000_000,
    "CHF": 531_000_000,
}
BNR_NAMESPACE = "{http://www.bnr.ro/xsd}"
HttpGet = Callable[[str], str]


class FxProvider(Protocol):
    @property
    def name(self) -> str: ...

    def fetch(self) -> dict[str, int]: ...


# ————————————————————————————————————————

class SimulatedProvider:
    def __init__(self, seed: int, volatility_bps: int, initial: dict[str, int] | None = None) -> None:
        self._rng = random.Random(seed)
        self._volatility = volatility_bps
        self._rates = dict(initial or INITIAL_RATES_E8)
        self._frozen = False
        self._lock = threading.Lock()

    # ————————————————————————————————————————

    @property
    def name(self) -> str:
        return "simulated"

    # ————————————————————————————————————————

    @property
    def frozen(self) -> bool:
        return self._frozen

    # ————————————————————————————————————————

    def initial_rates(self) -> dict[str, int]:
        with self._lock:
            return dict(self._rates)

    # ————————————————————————————————————————

    def fetch(self) -> dict[str, int]:
        with self._lock:
            if not self._frozen:
                for currency in sorted(self._rates):
                    delta = self._rng.randint(-self._volatility, self._volatility)
                    self._rates[currency] = apply_bps(self._rates[currency], delta)
            return dict(self._rates)

    # ————————————————————————————————————————

    def shock(self, currency: str, bps: int) -> int:
        with self._lock:
            self._rates[currency] = apply_bps(self._rates[currency], bps)
            return self._rates[currency]

    # ————————————————————————————————————————

    def freeze(self, frozen: bool) -> None:
        with self._lock:
            self._frozen = frozen


# ————————————————————————————————————————

def http_get_text(url: str, timeout: float = 5.0) -> str:
    if not url.startswith("https://"):
        raise ValueError("only https urls are allowed")
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return str(response.read().decode("utf-8"))


# ————————————————————————————————————————

def parse_bnr_xml(text: str) -> dict[str, int]:
    root = ET.fromstring(text)
    rates: dict[str, int] = {}
    for node in root.iter(f"{BNR_NAMESPACE}Rate"):
        currency = node.get("currency")
        if currency not in FOREIGN_CURRENCIES or node.text is None:
            continue
        multiplier = Decimal(node.get("multiplier", "1"))
        rates[currency] = parse_decimal_rate_e8(str(Decimal(node.text.strip()) / multiplier))
    return rates


# ————————————————————————————————————————

class BnrProvider:
    def __init__(self, url: str, http_get: HttpGet = http_get_text) -> None:
        self._url = url
        self._http_get = http_get

    # ————————————————————————————————————————

    @property
    def name(self) -> str:
        return "bnr"

    # ————————————————————————————————————————

    def fetch(self) -> dict[str, int]:
        return parse_bnr_xml(self._http_get(self._url))


# ————————————————————————————————————————

class FrankfurterProvider:
    def __init__(self, base_url: str, http_get: HttpGet = http_get_text) -> None:
        self._base_url = base_url.rstrip("/")
        self._http_get = http_get

    # ————————————————————————————————————————

    @property
    def name(self) -> str:
        return "frankfurter"

    # ————————————————————————————————————————

    def fetch(self) -> dict[str, int]:
        rates: dict[str, int] = {}
        for currency in FOREIGN_CURRENCIES:
            text = self._http_get(f"{self._base_url}/latest?from={currency}&to=RON")
            payload = json.loads(text, parse_float=Decimal)
            rates[currency] = parse_decimal_rate_e8(str(payload["rates"]["RON"]))
        return rates


# ————————————————————————————————————————

class FallbackProvider:
    def __init__(self, primary: FxProvider, fallback: SimulatedProvider) -> None:
        self._primary = primary
        self._fallback = fallback
        self._last_name = fallback.name

    # ————————————————————————————————————————

    @property
    def name(self) -> str:
        return self._last_name

    # ————————————————————————————————————————

    def fetch(self) -> dict[str, int]:
        try:
            quotes = self._primary.fetch()
            if quotes and all(value > 0 for value in quotes.values()):
                self._last_name = self._primary.name
                return quotes
        except Exception:
            pass
        self._last_name = self._fallback.name
        return self._fallback.fetch()


# ————————————————————————————————————————

def build_provider(settings: Settings, simulated: SimulatedProvider) -> FxProvider:
    if settings.fx_provider == "bnr":
        return FallbackProvider(BnrProvider(settings.bnr_url), simulated)
    if settings.fx_provider == "frankfurter":
        return FallbackProvider(FrankfurterProvider(settings.frankfurter_url), simulated)
    return simulated
