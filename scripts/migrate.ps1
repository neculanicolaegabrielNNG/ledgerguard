$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Set-Location (Get-ProjectRoot)
Invoke-Checked (Get-VenvPython) @("-m", "ledgerguard.common.migrate")
