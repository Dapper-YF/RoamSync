param(
    [switch]$DeviceTests,
    [switch]$Online,
    [string]$JavaHome = 'D:/Android/Android Studio/jbr',
    [string]$AndroidSdk = 'D:/Android/SDK',
    [string]$PublicMapEnv = 'E:/Study/RoamSync/.env'
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$names = @('JAVA_HOME', 'ANDROID_HOME', 'ANDROID_API_BASE_URL', 'AMAP_WEB_KEY', 'AMAP_ANDROID_KEY', 'AMAP_SECURITY_CODE')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

try {
    if (-not (Test-Path -LiteralPath $JavaHome -PathType Container)) { throw "Android JBR not found: $JavaHome" }
    if (-not (Test-Path -LiteralPath $AndroidSdk -PathType Container)) { throw "Android SDK not found: $AndroidSdk" }
    $env:JAVA_HOME = $JavaHome
    $env:ANDROID_HOME = $AndroidSdk
    # USB-connected devices reach the isolated API through adb reverse.
    $env:ANDROID_API_BASE_URL = 'http://127.0.0.1:18004/'
    foreach ($name in @('AMAP_WEB_KEY', 'AMAP_ANDROID_KEY', 'AMAP_SECURITY_CODE')) {
        [Environment]::SetEnvironmentVariable($name, '', 'Process')
    }

    # Only import client-side map configuration; do not load server credentials.
    if (Test-Path -LiteralPath $PublicMapEnv -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $PublicMapEnv) {
            if ($line -match '^\s*(AMAP_WEB_KEY|AMAP_ANDROID_KEY|AMAP_SECURITY_CODE)\s*=(.*)$') {
                $value = $Matches[2].Trim().Trim('"').Trim("'")
                [Environment]::SetEnvironmentVariable($Matches[1], $value, 'Process')
            }
        }
    }

    Push-Location (Join-Path $workspace 'android')
    try {
        $tasks = @(':app:testDebugUnitTest', ':app:assembleDebug')
        if ($DeviceTests) { $tasks += ':app:assembleDebugAndroidTest' }
        if (-not $Online) { $tasks = @('--offline') + $tasks }
        & ./gradlew.bat @tasks
        if ($LASTEXITCODE -ne 0) { throw 'Android preview build failed' }
    } finally { Pop-Location }

    $apk = Join-Path $workspace 'android/app/build/outputs/apk/debug/app-debug.apk'
    Write-Output "API endpoint embedded in preview: $env:ANDROID_API_BASE_URL"
    Write-Output "Preview package: com.roamsync.app.v2preview"
    Write-Output "Preview APK: $apk"
    Get-FileHash -LiteralPath $apk -Algorithm SHA256
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
