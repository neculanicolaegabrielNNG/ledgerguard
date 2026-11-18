function Get-ProjectRoot {
    return Split-Path -Parent $PSScriptRoot
}

# ————————————————————————————————————————

function Get-VenvPython {
    $python = Join-Path (Get-ProjectRoot) ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Mediul virtual lipsește. Urmează pașii din RUN.md."
    }
    return $python
}

# ————————————————————————————————————————

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
