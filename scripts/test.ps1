param(
    [ValidateSet("all", "unit", "robot")]
    [string]$Suite = "all",
    [string]$Include = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-ProjectRoot
Set-Location $root
$python = Get-VenvPython
$exitCode = 0

if ($Suite -eq "all" -or $Suite -eq "unit") {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { $exitCode = $LASTEXITCODE }
}

if ($Suite -eq "all" -or $Suite -eq "robot") {
    $arguments = @("-m", "robot", "--outputdir", "reports\robot", "--nostatusrc")
    if ($Include -ne "") {
        $arguments += @("--include", $Include)
    }
    $arguments += @("tests\robot\api", "tests\robot\db", "tests\robot\fx", "tests\robot\fraud", "tests\robot\agents")
    & $python @arguments
    $robotCode = $LASTEXITCODE
    if ($robotCode -ne 0) { $exitCode = $robotCode }
}

exit $exitCode
