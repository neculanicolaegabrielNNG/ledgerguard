from __future__ import annotations

from typing import Any

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "id": "R-AMOUNT-HISTORY",
        "name": "Sumă neobișnuit de mare față de istoric",
        "type": "amount_vs_history",
        "priority": 10,
        "effect": "score_add",
        "params": {"score": 40, "min_history_count": 3, "multiplier": 5, "floor_ron_minor": 300_000},
    },
    {
        "id": "R-VELOCITY",
        "name": "Multe tranzacții în interval scurt",
        "type": "velocity",
        "priority": 20,
        "effect": "score_add",
        "params": {"score": 35, "window_seconds": 600, "max_count": 5},
    },
    {
        "id": "R-STRUCTURING",
        "name": "Tranzacții fragmentate sub prag",
        "type": "structuring",
        "priority": 30,
        "effect": "review",
        "params": {
            "score": 60,
            "threshold_ron_minor": 5_000_000,
            "band_pct": 20,
            "window_seconds": 86_400,
            "min_count": 3,
        },
    },
    {
        "id": "R-NEW-ACCOUNT",
        "name": "Cont nou cu volum mare",
        "type": "new_account_volume",
        "priority": 40,
        "effect": "score_add",
        "params": {
            "score": 40,
            "max_age_seconds": 604_800,
            "volume_ron_minor": 2_000_000,
            "window_seconds": 86_400,
        },
    },
    {
        "id": "R-NEW-BENEFICIARY",
        "name": "Destinatar nou cu sumă mare",
        "type": "new_beneficiary_large",
        "priority": 50,
        "effect": "score_add",
        "params": {"score": 30, "amount_ron_minor": 1_500_000},
    },
    {
        "id": "R-CIRCULAR",
        "name": "Cerc de transferuri între conturi legate",
        "type": "circular_flow",
        "priority": 60,
        "effect": "review",
        "params": {"score": 70, "max_depth": 4, "window_seconds": 604_800},
    },
    {
        "id": "R-BEHAVIOR",
        "name": "Schimbare bruscă de comportament",
        "type": "behavior_change",
        "priority": 70,
        "effect": "score_add",
        "params": {
            "score": 30,
            "min_history_count": 5,
            "ratio": 4,
            "recent_seconds": 86_400,
            "baseline_seconds": 2_592_000,
            "floor_ron_minor": 500_000,
        },
    },
    {
        "id": "R-FX-ANOMALY",
        "name": "Curs valutar anormal la momentul tranzacției",
        "type": "fx_anomaly",
        "priority": 80,
        "effect": "score_add",
        "params": {"score": 30, "max_change_bps": 300, "lookback_seconds": 86_400, "alerts_trigger": 1},
    },
]
