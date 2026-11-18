# Invarianti de testat

## Ledger

- I1: pentru fiecare moneda, suma `amount_minor` din `ledger_entries` este zero.
- I2: pentru fiecare tranzactie si fiecare moneda, suma `amount_minor` este zero.
- I3: `UPDATE` si `DELETE` pe `ledger_entries` si `transactions` esueaza (triggere).
- I4: soldul afisat de API este egal cu suma recalculata direct din ledger.
- I5: nicio moneda a unui rand de ledger nu difera de moneda contului.
- I6: conturile de client nu au sold negativ.
- I7: corectia unei tranzactii este o tranzactie inversa, cu aceleasi sume RON stocate, negate.

## Bani si curs

- M1: nicio valoare monetara nu este float.
- M2: `amount_ron_minor` si `fx_rate_e8` se calculeaza la creare si nu se recalculeaza.
- M3: o schimbare ulterioara de curs nu modifica randurile existente.
- M4: curs mai vechi decat pragul respinge conversiile noi (`fx_rate_stale`).
- M5: variatie peste prag fata de cursul anterior nu se aplica si genereaza alerta.
- M6: conversii repetate nu creeaza si nu pierd bani: per moneda suma ramane zero, iar pierderea clientului este egala cu castigul conturilor de schimb.

## Transferuri

- T1: aceeasi `Idempotency-Key` returneaza acelasi rezultat si nu muta bani de doua ori.
- T2: aceeasi cheie cu continut diferit este respinsa (`idempotency_key_reuse`).
- T3: doua transferuri concurente din acelasi cont nu produc sold negativ.
- T4: orice tranzitie in afara tabelei de tranzitii este respinsa (`invalid_transition`).
- T5: fiecare tranzitie are rand in `transfer_transitions` si in `audit_log`.

## Antifrauda si agenti

- F1: fiecare evaluare contine regulile declansate cu valori masurate si versiunea regulii.
- F2: modificarea unei reguli creeaza versiune noua; versiunile vechi raman.
- A1: agentul nu executeaza decizii finale; decizia o ia un om.
- A2: textul introdus de utilizator (descrieri) nu schimba recomandarea agentului.
- A3: fiecare apel de tool este in audit cu intrari, iesiri si motiv.
- A4: asistentul client nu muta bani fara confirmare explicita si respecta limita de suma.

## Simulator

- S1: acelasi seed produce aceleasi metrici.
