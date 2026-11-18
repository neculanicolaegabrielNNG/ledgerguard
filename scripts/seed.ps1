param(
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Set-Location (Get-ProjectRoot)
if ($Password -ne "") {
    $env:LEDGERGUARD_SEED_PASSWORD = $Password
}
Invoke-Checked (Get-VenvPython) @("-m", "ledgerguard.seed")
