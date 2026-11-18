# Arhitectura modulelor

```mermaid
flowchart TD
    UI[ui NiceGUI] -->|HTTP /api/v1| API[FastAPI app]
    API --> auth
    API --> accounts
    API --> transfers
    API --> fraud
    API --> agents
    API --> simulation
    API --> audit
    transfers --> accounts
    transfers --> fx
    transfers --> ledger
    transfers --> fraud
    ledger --> accounts
    fraud --> fx
    fraud -. HistoryPort .-> transfers
    agents --> transfers
    agents --> fraud
    simulation -->|HTTP| API
    accounts --> audit
    ledger --> audit
    fx --> audit
    fraud --> audit
    transfers --> audit
    agents --> audit
    workers[workers asyncio] --> fx
    workers --> transfers
    workers --> agents
    workers --> audit
```

## Straturi

`api` (rute, validare Pydantic) -> `service` (reguli de business, functii pure de domeniu) -> `repository` (SQL explicit).

## Flux de transfer

1. API valideaza cererea si `Idempotency-Key`.
2. O singura tranzactie SQL (`BEGIN IMMEDIATE`): cheie de idempotenta, transfer `created`, cotare FX, evaluare antifrauda, tranzitii de stare, postare in ledger daca decizia este `approve`, raspuns salvat sub cheia de idempotenta.
3. `under_review` deschide un caz in coada de conformitate; agentul recomanda, omul decide.

## Cross-cutting

- `correlation_id`: middleware, apoi `Ctx`, audit, tool-uri de agent, erori.
- `Clock`: injectat in `Ctx`, singura sursa de timp.
- Evenimente (webhook): `audit.service.emit_event`, livrate de worker.
