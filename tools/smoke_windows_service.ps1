param([Parameter(Mandatory = $true)][string]$BundleRoot)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'This service installation smoke check is for disposable GitHub runners only.' }
$resolvedBundle = (Resolve-Path -LiteralPath $BundleRoot).ProviderPath
$allowedRoot = (Join-Path $env:GITHUB_WORKSPACE 'dist').TrimEnd('\') + '\'
if (-not $resolvedBundle.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Smoke bundle must be under this checkout dist directory.'
}
if (Get-Service RustDeskCompanyAPI -ErrorAction SilentlyContinue) { throw 'The smoke service name is already in use.' }
if (Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq 21114 }) { throw 'Smoke API port is already in use.' }
$wrapper = Join-Path $resolvedBundle 'windows/rdm-api-service.exe'
$oldPassword = $env:RDM_BOOTSTRAP_PASSWORD
$oldDatabase = $env:RDM_DATABASE
$installed = $false
Push-Location $resolvedBundle
try {
    New-Item -ItemType Directory -Force data/logs/api | Out-Null
    $env:RDM_BOOTSTRAP_PASSWORD = [Guid]::NewGuid().ToString('N')
    $env:RDM_DATABASE = Join-Path $resolvedBundle 'data/management.sqlite3'
    & (Join-Path $resolvedBundle 'rustdesk-management.exe') create-admin --username admin
    if ($LASTEXITCODE -ne 0) { throw 'Administrator bootstrap failed.' }
    & icacls.exe $resolvedBundle /grant '*S-1-5-19:(OI)(CI)RX'
    if ($LASTEXITCODE -ne 0) { throw 'Service read permissions failed.' }
    & icacls.exe (Join-Path $resolvedBundle 'data') /grant '*S-1-5-19:(OI)(CI)M'
    if ($LASTEXITCODE -ne 0) { throw 'Service data permissions failed.' }
    & $wrapper install
    if ($LASTEXITCODE -ne 0) { throw 'Service installation failed.' }
    $installed = $true
    & $wrapper start
    if ($LASTEXITCODE -ne 0) { throw 'Service startup failed.' }
    $healthy = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $null = Invoke-RestMethod -Uri http://127.0.0.1:21114/healthz -TimeoutSec 2
            $healthy = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'LocalService API did not become healthy; inspect data/logs/api.' }
    Write-Output 'Packaged API started successfully as a LocalService Windows service.'
} finally {
    if ($installed) {
        & $wrapper stop
        & $wrapper uninstall
        if ($LASTEXITCODE -ne 0) { throw 'Smoke service cleanup failed.' }
    }
    $env:RDM_BOOTSTRAP_PASSWORD = $oldPassword
    $env:RDM_DATABASE = $oldDatabase
    Pop-Location
}
