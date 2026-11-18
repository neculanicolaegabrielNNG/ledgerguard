from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from ledgerguard.common.errors import invalid

BASE_CURRENCY = "RON"
SUPPORTED_CURRENCIES: tuple[str, ...] = ("RON", "EUR", "USD", "CHF")
FOREIGN_CURRENCIES: tuple[str, ...] = ("EUR", "USD", "CHF")
RATE_SCALE = 10**8
BPS_SCALE = 10_000
MINOR_PER_UNIT = 100


def round_half_even_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    quotient, remainder = divmod(abs(numerator), denominator)
    twice = remainder * 2
    if twice > denominator or (twice == denominator and quotient % 2 == 1):
        quotient += 1
    return quotient if numerator >= 0 else -quotient


# ————————————————————————————————————————

def to_ron_minor(amount_minor: int, rate_e8: int) -> int:
    return round_half_even_div(amount_minor * rate_e8, RATE_SCALE)


# ————————————————————————————————————————

def convert_minor(amount_minor: int, source_rate_e8: int, target_rate_e8: int, spread_bps: int) -> int:
    numerator = amount_minor * source_rate_e8 * (BPS_SCALE - spread_bps)
    denominator = target_rate_e8 * BPS_SCALE
    return round_half_even_div(numerator, denominator)


# ————————————————————————————————————————

def change_bps(previous_e8: int, current_e8: int) -> int:
    return round_half_even_div((current_e8 - previous_e8) * BPS_SCALE, previous_e8)


# ————————————————————————————————————————

def apply_bps(rate_e8: int, bps: int) -> int:
    return round_half_even_div(rate_e8 * (BPS_SCALE + bps), BPS_SCALE)


# ————————————————————————————————————————

def parse_decimal_rate_e8(text: str) -> int:
    try:
        value = Decimal(text.strip())
    except InvalidOperation as error:
        raise ValueError(f"invalid rate: {text}") from error
    scaled = (value * RATE_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN)
    return int(scaled)


# ————————————————————————————————————————

def parse_amount_minor(text: str) -> int:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"invalid amount: {text}") from error
    scaled = (value * MINOR_PER_UNIT).to_integral_value(rounding=ROUND_HALF_EVEN)
    return int(scaled)


# ————————————————————————————————————————

def format_rate(rate_e8: int) -> str:
    return f"{rate_e8 // RATE_SCALE}.{rate_e8 % RATE_SCALE:08d}"


# ————————————————————————————————————————

def format_minor(amount_minor: int, currency: str) -> str:
    sign = "-" if amount_minor < 0 else ""
    whole, fraction = divmod(abs(amount_minor), MINOR_PER_UNIT)
    return f"{sign}{whole}.{fraction:02d} {currency}"


# ————————————————————————————————————————

def require_currency(currency: str) -> str:
    if currency not in SUPPORTED_CURRENCIES:
        raise invalid("unsupported_currency", "Moneda nu este suportată.", {"currency": currency})
    return currency
