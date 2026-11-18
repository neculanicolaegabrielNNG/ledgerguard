# Reguli antifrauda (valori implicite)

Toate sumele sunt in subunitati RON (`amount_ron_minor`). Regulile sunt randuri in `fraud_rules`, versionate. Pragurile globale: `review` la scor >= 50, `block` la scor >= 90, scor plafonat la 100.

| id | tip | efect | scor | parametri impliciti |
|---|---|---|---|---|
| R-AMOUNT-HISTORY | amount_vs_history | score_add | 40 | min_history_count=3, multiplier=5, floor_ron_minor=300000 |
| R-VELOCITY | velocity | score_add | 35 | window_seconds=600, max_count=5 |
| R-STRUCTURING | structuring | review | 60 | threshold_ron_minor=5000000, band_pct=20, window_seconds=86400, min_count=3 |
| R-NEW-ACCOUNT | new_account_volume | score_add | 40 | max_age_seconds=604800, volume_ron_minor=2000000, window_seconds=86400 |
| R-NEW-BENEFICIARY | new_beneficiary_large | score_add | 30 | amount_ron_minor=1500000 |
| R-CIRCULAR | circular_flow | review | 70 | max_depth=4, window_seconds=604800 |
| R-BEHAVIOR | behavior_change | score_add | 30 | min_history_count=5, ratio=4, recent_seconds=86400, baseline_seconds=2592000, floor_ron_minor=500000 |
| R-FX-ANOMALY | fx_anomaly | score_add | 30 | max_change_bps=300, lookback_seconds=86400, alerts_trigger=1 |

## Semantica

- `amount_vs_history`: suma depaseste `multiplier` x media transferurilor finalizate ale clientului (minim `min_history_count`) si pragul `floor_ron_minor`.
- `velocity`: numarul de transferuri ale clientului in fereastra, inclusiv cel curent, depaseste `max_count`.
- `structuring`: cel putin `min_count` transferuri (inclusiv cel curent) in banda `[threshold * (100 - band_pct) / 100, threshold)` in fereastra.
- `new_account_volume`: contul sursa are varsta sub `max_age_seconds` si volumul trimis in fereastra depaseste `volume_ron_minor`.
- `new_beneficiary_large`: destinatar nemaivazut pentru client si suma peste prag.
- `circular_flow`: exista drum de la destinatar inapoi la sursa prin transferuri recente, in cel mult `max_depth` pasi.
- `behavior_change`: volumul recent depaseste `ratio` x media zilnica a bazei de comparatie.
- `fx_anomaly`: variatia cursului in `lookback_seconds` depaseste `max_change_bps`, sau exista alerte de curs recente.

## Efecte

- `score_add`: adauga `score` la scor.
- `review`: adauga `score` si forteaza cel putin `under_review`.
- `block`: adauga `score` si forteaza `blocked`.

## Versionare

Orice modificare creeaza un rand nou cu `version + 1` si `valid_from = acum`. Randurile existente nu se modifica. Regula activa la momentul `t` este versiunea maxima cu `valid_from <= t`. Evaluarile stocheaza versiunea fiecarei reguli aplicate.
