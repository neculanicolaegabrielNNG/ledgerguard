from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

STRATEGIES: tuple[str, ...] = ("structuring", "mule_accounts", "account_takeover", "transfer_cycle")
WARMUP_SECONDS = 8 * 86_400
MINOR_PER_RON = 100
BENIGN_SPACING_SECONDS = 150
BENIGN_OWNERS = ("benign0", "benign1", "benign2", "benign3")


@dataclass(frozen=True)
class AccountSpec:
    key: str
    owner: str
    initial_minor: int
    established: bool


# ————————————————————————————————————————

@dataclass(frozen=True)
class Step:
    index: int
    from_key: str
    to_key: str
    amount_minor: int
    offset_seconds: int
    malicious: bool
    label: str


# ————————————————————————————————————————

@dataclass(frozen=True)
class Scenario:
    strategy: str
    accounts: list[AccountSpec]
    steps: list[Step]
    warmup_seconds: int


# ————————————————————————————————————————

def _ron(units: int) -> int:
    return units * MINOR_PER_RON


# ————————————————————————————————————————

def _structuring(rng: random.Random) -> tuple[list[AccountSpec], list[Step]]:
    mules = ["mule0", "mule1", "mule2"]
    accounts = [AccountSpec("attacker", "attacker", _ron(400_000), True)]
    accounts += [AccountSpec(mule, mule, 0, True) for mule in mules]
    steps = [
        Step(0, "attacker", mules[position % 3], _ron(rng.randint(40_100, 49_900)), position * 600, True, "structuring")
        for position in range(5)
    ]
    return accounts, steps


# ————————————————————————————————————————

def _mule_accounts(rng: random.Random) -> tuple[list[AccountSpec], list[Step]]:
    accounts = [
        AccountSpec("attacker", "attacker", _ron(120_000), False),
        AccountSpec("mule0", "mule0", 0, False),
        AccountSpec("mule1", "mule1", 0, False),
        AccountSpec("mule2", "mule2", 0, False),
    ]
    amounts = [rng.randint(11_000, 13_000), rng.randint(11_000, 13_000), rng.randint(16_000, 19_000)]
    steps = [
        Step(0, "attacker", f"mule{position}", _ron(amount), position * 300, True, "mule_chain")
        for position, amount in enumerate(amounts)
    ]
    return accounts, steps


# ————————————————————————————————————————

def _account_takeover(rng: random.Random) -> tuple[list[AccountSpec], list[Step]]:
    accounts = [
        AccountSpec("victim", "victim", _ron(200_000), True),
        AccountSpec("friend", "friend", 0, True),
        AccountSpec("thief", "thief", 0, True),
    ]
    history = [
        Step(0, "victim", "friend", _ron(rng.randint(80, 150)), position * 3_600, False, "victim_history")
        for position in range(6)
    ]
    takeover_start = 6 * 3_600
    takeover = [
        Step(0, "victim", "thief", _ron(rng.randint(35_000, 45_000)), takeover_start + position * 300, True, "takeover")
        for position in range(2)
    ]
    return accounts, history + takeover


# ————————————————————————————————————————

def _transfer_cycle(rng: random.Random) -> tuple[list[AccountSpec], list[Step]]:
    names = ["ring0", "ring1", "ring2"]
    accounts = [AccountSpec(name, name, _ron(100_000), True) for name in names]
    base = rng.randint(9_000, 10_000)
    steps = [
        Step(0, names[position], names[(position + 1) % 3], _ron(base - position * 500), position * 600, True, "cycle")
        for position in range(3)
    ]
    return accounts, steps


# ————————————————————————————————————————

BUILDERS: dict[str, Callable[[random.Random], tuple[list[AccountSpec], list[Step]]]] = {
    "structuring": _structuring,
    "mule_accounts": _mule_accounts,
    "account_takeover": _account_takeover,
    "transfer_cycle": _transfer_cycle,
}


# ————————————————————————————————————————

def _benign_steps(rng: random.Random, count: int, horizon: int) -> tuple[list[AccountSpec], list[Step]]:
    accounts = [AccountSpec(owner, owner, _ron(50_000), True) for owner in BENIGN_OWNERS]
    slots = max(1, horizon // BENIGN_SPACING_SECONDS)
    offsets = sorted(rng.sample(range(slots + count), count)) if count else []
    steps: list[Step] = []
    pairs = [(low, high) for low in range(len(BENIGN_OWNERS)) for high in range(low + 1, len(BENIGN_OWNERS))]
    for offset in offsets:
        low, high = rng.choice(pairs)
        steps.append(
            Step(
                0,
                BENIGN_OWNERS[low],
                BENIGN_OWNERS[high],
                _ron(rng.randint(20, 400)),
                offset * BENIGN_SPACING_SECONDS,
                False,
                "benign",
            )
        )
    return accounts, steps


# ————————————————————————————————————————

def build_scenario(strategy: str, seed: int, benign_count: int) -> Scenario:
    if strategy not in BUILDERS:
        raise ValueError(f"unknown strategy: {strategy}")
    rng = random.Random(seed)
    attack_accounts, attack_steps = BUILDERS[strategy](rng)
    horizon = max(step.offset_seconds for step in attack_steps) + 1_200
    benign_accounts, benign_steps = _benign_steps(rng, benign_count, horizon)
    merged = sorted(
        [*attack_steps, *benign_steps], key=lambda step: (step.offset_seconds, 0 if step.malicious else 1)
    )
    ordered = [
        Step(position, step.from_key, step.to_key, step.amount_minor, step.offset_seconds, step.malicious, step.label)
        for position, step in enumerate(merged)
    ]
    accounts = attack_accounts + (benign_accounts if benign_count else [])
    return Scenario(strategy, accounts, ordered, WARMUP_SECONDS)
