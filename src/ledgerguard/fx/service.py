from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ledgerguard.audit import service as audit
from ledgerguard.common.clock import iso_before, seconds_between, to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import conflict, invalid
from ledgerguard.common.ids import new_id
from ledgerguard.common.money import (
    BASE_CURRENCY,
    FOREIGN_CURRENCIES,
    RATE_SCALE,
    SUPPORTED_CURRENCIES,
    change_bps,
    convert_minor,
    format_rate,
    to_ron_minor,
)
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq
from ledgerguard.fx import repository
from ledgerguard.fx.providers import FxProvider


@dataclass(frozen=True)
class RateRef:
    rate_id: str | None
    currency: str
    rate_e8: int
    valid_from: str


# ————————————————————————————————————————

@dataclass(frozen=True)
class Conversion:
    source_currency: str
    target_currency: str
    source_amount_minor: int
    target_amount_minor: int
    amount_ron_minor: int
    source_rate: RateRef
    target_rate: RateRef
    spread_bps: int


# ————————————————————————————————————————

def ron_rate(ctx: Ctx) -> RateRef:
    return RateRef(None, BASE_CURRENCY, RATE_SCALE, to_iso(ctx.clock.now()))


# ————————————————————————————————————————

def _ref(found: Row) -> RateRef:
    return RateRef(found["id"], found["base"], int(found["rate_e8"]), found["valid_from"])


# ————————————————————————————————————————

def rate_as_of(ctx: Ctx, currency: str, at_iso: str) -> RateRef:
    if currency == BASE_CURRENCY:
        return RateRef(None, BASE_CURRENCY, RATE_SCALE, at_iso)
    found = repository.latest_rate(ctx.conn, currency, at_iso)
    if found is None:
        found = repository.earliest_rate(ctx.conn, currency)
    if found is None:
        raise conflict("fx_rate_missing", "Nu există curs valutar pentru moneda cerută.", {"currency": currency})
    return _ref(found)


# ————————————————————————————————————————

def rate_for(ctx: Ctx, currency: str) -> RateRef:
    if currency == BASE_CURRENCY:
        return ron_rate(ctx)
    now = ctx.clock.now()
    found = repository.latest_rate(ctx.conn, currency, to_iso(now))
    if found is None:
        raise conflict("fx_rate_missing", "Nu există curs valutar pentru moneda cerută.", {"currency": currency})
    age = seconds_between(found["valid_from"], now)
    if age > ctx.settings.fx_max_age_seconds:
        raise conflict(
            "fx_rate_stale",
            "Cursul valutar este expirat. Conversiile noi sunt respinse.",
            {"currency": currency, "age_seconds": age, "max_age_seconds": ctx.settings.fx_max_age_seconds},
        )
    return _ref(found)


# ————————————————————————————————————————

def quote_conversion(
    ctx: Ctx, amount_minor: int, source_currency: str, target_currency: str
) -> Conversion:
    if amount_minor <= 0:
        raise invalid("invalid_amount", "Suma trebuie să fie pozitivă.")
    source_rate = rate_for(ctx, source_currency)
    amount_ron = to_ron_minor(amount_minor, source_rate.rate_e8)
    if source_currency == target_currency:
        return Conversion(
            source_currency, target_currency, amount_minor, amount_minor, amount_ron, source_rate, source_rate, 0
        )
    target_rate = rate_for(ctx, target_currency)
    spread = ctx.settings.fx_spread_bps
    target_amount = convert_minor(amount_minor, source_rate.rate_e8, target_rate.rate_e8, spread)
    if target_amount <= 0:
        raise invalid("amount_too_small", "Suma este prea mică pentru conversie.")
    return Conversion(
        source_currency, target_currency, amount_minor, target_amount, amount_ron, source_rate, target_rate, spread
    )


# ————————————————————————————————————————

def seed_initial_rates(ctx: Ctx, rates: dict[str, int], source: str) -> bool:
    with ctx.transaction():
        if repository.count_rates(ctx.conn) > 0:
            return False
        now = to_iso(ctx.clock.now())
        for currency in FOREIGN_CURRENCIES:
            repository.insert_rate(ctx.conn, new_id("fxr"), currency, rates[currency], now, source)
        return True


# ————————————————————————————————————————

def refresh(ctx: Ctx, provider: FxProvider) -> dict[str, Any]:
    quotes = provider.fetch()
    source = provider.name
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    now_iso = to_iso(ctx.clock.now())
    with ctx.transaction():
        for currency in FOREIGN_CURRENCIES:
            candidate = quotes.get(currency)
            if candidate is None or candidate <= 0:
                continue
            previous = repository.latest_rate(ctx.conn, currency, now_iso)
            if previous is not None:
                change = change_bps(int(previous["rate_e8"]), candidate)
                if abs(change) > ctx.settings.fx_max_change_bps:
                    alert_id = new_id("fxa")
                    repository.insert_alert(
                        ctx.conn, alert_id, currency, int(previous["rate_e8"]), candidate, change, source, now_iso
                    )
                    detail = {
                        "currency": currency,
                        "previous_rate_e8": int(previous["rate_e8"]),
                        "proposed_rate_e8": candidate,
                        "change_bps": change,
                        "source": source,
                    }
                    audit.record(ctx, "fx.rate_rejected", "fx_alert", alert_id, detail)
                    audit.emit_event(ctx, "fx.alert", {"alert_id": alert_id, **detail})
                    rejected.append(detail)
                    continue
            rate_id = new_id("fxr")
            repository.insert_rate(ctx.conn, rate_id, currency, candidate, now_iso, source)
            applied.append({"currency": currency, "rate_e8": candidate, "id": rate_id, "source": source})
    return {"applied": applied, "rejected": rejected, "source": source}


# ————————————————————————————————————————

def current_rates(ctx: Ctx) -> list[dict[str, Any]]:
    now = ctx.clock.now()
    result: list[dict[str, Any]] = []
    for currency in FOREIGN_CURRENCIES:
        found = repository.latest_rate(ctx.conn, currency, to_iso(now))
        if found is None:
            continue
        age = seconds_between(found["valid_from"], now)
        result.append(
            {
                "currency": currency,
                "quote": BASE_CURRENCY,
                "rate_e8": int(found["rate_e8"]),
                "rate": format_rate(int(found["rate_e8"])),
                "valid_from": found["valid_from"],
                "source": found["source"],
                "age_seconds": age,
                "status": "fresh" if age <= ctx.settings.fx_max_age_seconds else "stale",
            }
        )
    return result


# ————————————————————————————————————————

def rates_at(ctx: Ctx, at_iso: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for currency in FOREIGN_CURRENCIES:
        found = repository.latest_rate(ctx.conn, currency, at_iso)
        if found is not None:
            result.append(
                {"currency": currency, "rate_e8": int(found["rate_e8"]), "valid_from": found["valid_from"]}
            )
    return result


# ————————————————————————————————————————

def history(ctx: Ctx, currency: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    if currency is not None and currency not in SUPPORTED_CURRENCIES:
        raise invalid("unsupported_currency", "Moneda nu este suportată.", {"currency": currency})
    size = clamp_limit(limit)
    rows = repository.list_rates(ctx.conn, currency, decode_seq(cursor), size)
    page = build_page(rows, size)
    page["items"] = [{**item, "rate": format_rate(int(item["rate_e8"]))} for item in page["items"]]
    return page


# ————————————————————————————————————————

def alerts(ctx: Ctx, currency: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    size = clamp_limit(limit)
    rows = repository.list_alerts(ctx.conn, currency, decode_seq(cursor), size)
    return build_page(rows, size)


# ————————————————————————————————————————

def context(ctx: Ctx, currency: str, lookback_seconds: int = 86_400) -> dict[str, Any]:
    now = ctx.clock.now()
    now_iso = to_iso(now)
    if currency == BASE_CURRENCY:
        return {
            "currency": currency,
            "rate_e8": RATE_SCALE,
            "reference_rate_e8": RATE_SCALE,
            "change_bps": 0,
            "alerts_recent": 0,
            "status": "base",
        }
    current = rate_as_of(ctx, currency, now_iso)
    reference = rate_as_of(ctx, currency, iso_before(now, lookback_seconds))
    age = seconds_between(current.valid_from, now)
    return {
        "currency": currency,
        "rate_e8": current.rate_e8,
        "reference_rate_e8": reference.rate_e8,
        "change_bps": change_bps(reference.rate_e8, current.rate_e8),
        "alerts_recent": repository.count_alerts_since(ctx.conn, currency, iso_before(now, lookback_seconds)),
        "age_seconds": age,
        "status": "fresh" if age <= ctx.settings.fx_max_age_seconds else "stale",
        "valid_from": current.valid_from,
        "source_rate_id": current.rate_id,
    }
