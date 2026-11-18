param(
    [int]$Port = 8000,
    [string]$BindAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Set-Location (Get-ProjectRoot)
Invoke-Checked (Get-VenvPython) @(
    "-m", "uvicorn", "ledgerguard.app.main:create_app", "--factory",
    "--host", $BindAddress, "--port", "$Port"
)
