# LedgerGuard

Sistem financiar multi-valutar demonstrativ (RON, EUR, USD, CHF): ledger cu partidă dublă, curs valutar simulat sau BNR, transferuri cu automat de stări, antifraudă bazată pe reguli versionate, agenți AI cu mod offline, simulator atacator contra apărător, interfață NiceGUI și teste Robot Framework.

- Pornire și teste: [RUN.md](RUN.md)
- Decizii de proiectare: [DECISIONS.md](DECISIONS.md)
- Proiectare: [docs/](docs/) (structură, arhitectură, contract API, reguli antifraudă, invarianți, schemă SQL)

Stack: Python 3.12+, SQLite, FastAPI, Pydantic v2, NiceGUI, pytest, Robot Framework. Funcționează complet offline, fără cheie API.
