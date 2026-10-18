[CmdletBinding()]
param([switch]$Recreate)

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($sourceRoot.TrimEnd('\') -ine 'E:\Study\RoamSync') {
    throw 'Official deployment must run from E:\Study\RoamSync.'
}
$composePath = Join-Path $sourceRoot 'compose.yaml'
$settingsPath = Join-Path $sourceRoot '.env'
if (-not (Test-Path -LiteralPath $settingsPath)) { throw 'Missing official .env file.' }
# Prevent inherited app settings from silently overriding the official .env.
foreach ($line in [IO.File]::ReadAllLines($settingsPath)) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=') {
        Remove-Item -LiteralPath ('Env:' + $Matches[1]) -ErrorAction SilentlyContinue
    }
}
$composeArgs = @('compose', '--project-directory', $sourceRoot, '--env-file', $settingsPath,
    '-p', 'roamsync', '-f', $composePath)
& docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Official Compose configuration is invalid.' }
Write-Output 'Building and starting the official source. Existing database data is preserved.'
$upArgs = @('up', '-d', '--build', '--wait', '--wait-timeout', '180')
if ($Recreate) { $upArgs += '--force-recreate' }
& docker @composeArgs @upArgs
if ($LASTEXITCODE -ne 0) { throw 'Docker build or startup failed.' }
& (Join-Path $PSScriptRoot 'verify-roamsync.ps1')
Write-Output 'Ready: http://127.0.0.1:3000'
