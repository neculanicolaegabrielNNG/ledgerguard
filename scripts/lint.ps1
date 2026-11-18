$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Set-Location (Get-ProjectRoot)
$python = Get-VenvPython
Invoke-Checked $python @("-m", "ruff", "check", "src", "tests")
Invoke-Checked $python @("-m", "mypy", "src")
