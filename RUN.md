# Pornire și testare

Toate comenzile se rulează în PowerShell, din folderul `ledgerguard`. Singura cerință: Python 3.12 sau mai nou.

## 1. Mediu și pachete

```powershell
cd "<calea către>\ledgerguard"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[core,ui,test,dev]"
```

Dacă politica de execuție blochează scripturile `.ps1`, rulează-le astfel:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

## 2. Migrări și date inițiale

```powershell
.\scripts\migrate.ps1
.\scripts\seed.ps1
```

`seed.ps1` creează utilizatorii `admin@ledgerguard.local`, `compliance@ledgerguard.local` și `client@ledgerguard.local`, clienți sintetici, istoric de curs și reguli antifraudă. Parola se citește din `-Password` sau din `LEDGERGUARD_SEED_PASSWORD`; dacă lipsesc, se generează una și se scrie în `data\seed_credentials.txt`.

Echivalent fără scripturi:

```powershell
.\.venv\Scripts\python.exe -m ledgerguard.common.migrate
.\.venv\Scripts\python.exe -m ledgerguard.seed
```

## 3. Pornire

```powershell
.\scripts\run.ps1
```

- Interfață: http://127.0.0.1:8000/login
- API: http://127.0.0.1:8000/api/v1 (documentație interactivă: http://127.0.0.1:8000/docs)

Echivalent: `.\.venv\Scripts\python.exe -m uvicorn ledgerguard.app.main:create_app --factory --host 127.0.0.1 --port 8000`

## 4. Teste

```powershell
.\scripts\test.ps1
.\scripts\test.ps1 -Suite unit
.\scripts\test.ps1 -Suite robot
.\scripts\test.ps1 -Suite robot -Include "rule:velocity"
```

Rezultatele Robot se scriu în `reports\robot` (`report.html`, `log.html`, `output.xml`). Panoul de calitate din interfață citește `output.xml`.

Echivalent:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m robot --outputdir reports\robot tests\robot\api tests\robot\db tests\robot\fx tests\robot\fraud tests\robot\agents
```

## 5. Verificări statice

```powershell
.\scripts\lint.ps1
```

## 6. Opțional

Agent AI cu model (altfel se folosește `OfflineAnalyst`):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ai]"
$env:ANTHROPIC_API_KEY = "<cheia ta>"
.\scripts\run.ps1
```

Curs real BNR sau Frankfurter (necesită internet; la eșec se revine la furnizorul simulat):

```powershell
$env:LEDGERGUARD_FX_PROVIDER = "bnr"
.\scripts\run.ps1
```

Teste UI (în afara suitei implicite):

```powershell
.\.venv\Scripts\python.exe -m pip install robotframework-browser
.\.venv\Scripts\python.exe -m Browser.entry init
$env:LEDGERGUARD_DB = "$PWD\data\ledgerguard.db"
$env:LEDGERGUARD_UI_PASSWORD = "<parola din seed>"
$env:LEDGERGUARD_UI_CUSTOMER = "client@ledgerguard.local"
$env:LEDGERGUARD_UI_COMPLIANCE = "compliance@ledgerguard.local"
$env:LEDGERGUARD_UI_TARGET_ACCOUNT = "<identificatorul unui cont destinatar>"
.\.venv\Scripts\python.exe -m robot --outputdir reports\ui tests\robot\ui_optional
```

Variabile de mediu utile: `LEDGERGUARD_DB`, `LEDGERGUARD_JWT_SECRET`, `LEDGERGUARD_WORKER` (0 dezactivează workerii), `LEDGERGUARD_UI` (0 dezactivează interfața), `LEDGERGUARD_FX_REFRESH_SECONDS`, `LEDGERGUARD_FX_SEED`.
