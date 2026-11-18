# Structura repo-ului

```
ledgerguard/
  pyproject.toml
  DECISIONS.md  RUN.md  README.md
  docs/                         artefacte de proiectare (Faza 0)
  migrations/                   0001_*.sql ... aplicate de runnerul propriu
  scripts/                      migrate.ps1 seed.ps1 run.ps1 test.ps1 lint.ps1
  src/ledgerguard/
    common/                     clock, erori, bani, db, context, migrari, idempotenta, paginare, rate limit
    accounts/ fx/ ledger/ transfers/ fraud/ agents/ audit/ simulation/ auth/
        api.py                  rute si validare
        service.py              logica de business
        repository.py           SQL explicit
    app/                        main, deps, wiring, workflows, workers, bootstrap
    ui/                         NiceGUI (acces doar prin API)
  tests/
    unit/                       pytest pentru functii pure de domeniu
    robot/
      api/ db/ agents/ fx/ fraud/
      resources/                keyword-uri comune, ApiLibrary.py, DbLibrary.py
      variables/                configurare
      ui_optional/              teste UI, in afara suitei implicite
  data/                         baza SQLite locala si credentialele de seed
  reports/                      iesiri Robot si pytest
```

Reguli de dependenta intre module (sageata inseamna "importa serviciul public al"):

```
auth, audit, accounts      -> (nimic)
fx                         -> audit
ledger                     -> accounts, audit
fraud                      -> fx, audit (istoric prin HistoryPort)
transfers                  -> accounts, fx, ledger, fraud, audit
agents                     -> transfers, fraud, fx, accounts, audit
simulation                 -> doar prin API (client HTTP)
app (wiring, workflows)    -> orchestreaza modulele
```

Un modul nu citeste si nu scrie in tabelele altui modul.
