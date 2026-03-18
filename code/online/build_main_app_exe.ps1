$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

py -m PyInstaller --noconfirm --clean .\main_app.spec

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $scriptDir\dist\BCI-Control-Car\BCI-Control-Car.exe"
