from __future__ import annotations

import pytest

from ledgerguard.common.money import (
    apply_bps,
    change_bps,
    convert_minor,
    format_minor,
    format_rate,
    parse_amount_minor,
    parse_decimal_rate_e8,
    round_half_even_div,
    to_ron_minor,
)


def test_half_even_rounds_ties_to_even() -> None:
    assert round_half_even_div(5, 2) == 2
    assert round_half_even_div(7, 2) == 4
    assert round_half_even_div(-5, 2) == -2
    assert round_half_even_div(-7, 2) == -4


# ————————————————————————————————————————

def test_half_even_rounds_non_ties_to_nearest() -> None:
    assert round_half_even_div(10, 3) == 3
    assert round_half_even_div(11, 3) == 4
    assert round_half_even_div(-11, 3) == -4


# ————————————————————————————————————————

def test_half_even_rejects_non_positive_denominator() -> None:
    with pytest.raises(ValueError):
        round_half_even_div(1, 0)


# ————————————————————————————————————————

def test_to_ron_minor_is_exact_for_whole_rates() -> None:
    assert to_ron_minor(10_000, 497_000_000) == 49_700


# ————————————————————————————————————————

def test_to_ron_minor_is_symmetric_for_negative_amounts() -> None:
    assert to_ron_minor(-1_001, 497_000_000) == -to_ron_minor(1_001, 497_000_000)


# ————————————————————————————————————————

def test_convert_applies_spread_with_single_rounding() -> None:
    assert convert_minor(10_000, 497_000_000, 457_000_000, 50) == 10_821
    assert convert_minor(10_000, 497_000_000, 457_000_000, 0) == 10_875


# ————————————————————————————————————————

def test_repeated_round_trip_never_gains_money_without_spread() -> None:
    balance = 100_000
    for _ in range(50):
        converted = convert_minor(balance, 497_000_000, 457_000_000, 0)
        balance = convert_minor(converted, 457_000_000, 497_000_000, 0)
    assert balance <= 100_000


# ————————————————————————————————————————

def test_change_and_apply_bps() -> None:
    assert change_bps(100_000_000, 105_000_000) == 500
    assert change_bps(100_000_000, 95_000_000) == -500
    assert apply_bps(100_000_000, 500) == 105_000_000


# ————————————————————————————————————————

def test_decimal_parsing_has_no_float_drift() -> None:
    assert parse_decimal_rate_e8("4.9712") == 497_120_000
    assert parse_amount_minor("125.50") == 12_550
    assert parse_amount_minor("125,5") == 12_550
    assert parse_amount_minor("0.29") == 29


# ————————————————————————————————————————

def test_formatting() -> None:
    assert format_rate(497_120_000) == "4.97120000"
    assert format_minor(-12_550, "EUR") == "-125.50 EUR"
    assert format_minor(5, "RON") == "0.05 RON"
