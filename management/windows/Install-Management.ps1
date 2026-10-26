[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)][string]$PublicIp,
    [switch]$SkipFirewall
)
$ErrorActionPreference = 'Stop'
$bundleRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).ProviderPath
$address = $null
if ($PublicIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
    -not [System.Net.IPAddress]::TryParse($PublicIp, [ref]$address) -or
    $address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    [System.Net.IPAddress]::IsLoopback($address)) {
    throw 'PublicIp must be the fixed public IPv4 address, without a port or URL prefix.'
}
$PublicIp = $address.ToString()
$driveRoot = [System.IO.Path]::GetPathRoot($bundleRoot).TrimEnd('\')
if ($bundleRoot.TrimEnd('\') -eq $driveRoot -or
    $bundleRoot.StartsWith($env:WINDIR, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Extract to a dedicated application directory outside Windows and drive roots.'
}
foreach ($relativeFile in @('rustdesk-management.exe', 'windows\caddy.exe',
        'windows\rdm-api-service.exe', 'windows\rdm-https-service.exe',
        'windows\rdm-api-service.xml', 'windows\rdm-https-service.xml', 'windows\Caddyfile.ip')) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot $relativeFile) -PathType Leaf)) {
        throw "Incomplete Windows release bundle: $relativeFile"
    }
}
$services = @(Get-Service -Name RustDeskCompanyAPI, RustDeskCompanyHTTPS -ErrorAction SilentlyContinue)
if ($services.Count -gt 0) {
    throw 'Company services already exist. Follow the upgrade instructions; this installer does not overwrite them.'
}
$listeners = @(Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in @(80, 443, 21114) })
if ($listeners.Count -gt 0) {
    throw ('A required port is already in use. Do not stop unknown services: ' +
        (($listeners | Select-Object LocalAddress, LocalPort, OwningProcess | Out-String).Trim()))
}
if (-not $SkipFirewall -and (Get-NetFirewallRule -Name RustDeskCompanyHTTPS -ErrorAction SilentlyContinue)) {
    throw 'The company firewall rule already exists. Inspect it before installation.'
}
if (-not $PSCmdlet.ShouldProcess($bundleRoot,
        "Install company API and HTTPS services for $PublicIp; keep hbbs/hbbr untouched")) { return }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer from an elevated PowerShell window.'
}
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $File" }
}
$oldDatabase = $env:RDM_DATABASE
Push-Location $bundleRoot
try {
    $dataRoot = Join-Path $bundleRoot 'data'
    foreach ($directory in @($dataRoot, "$dataRoot\caddy", "$dataRoot\logs\api", "$dataRoot\logs\https")) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $env:RDM_DATABASE = Join-Path $dataRoot 'management.sqlite3'
    if (-not (Test-Path -LiteralPath $env:RDM_DATABASE)) {
        Write-Host 'Create the first administrator. Enter a password of at least 12 characters.'
        Invoke-Checked (Join-Path $bundleRoot 'rustdesk-management.exe') @('create-admin', '--username', 'admin')
    } else {
        Write-Host 'Existing management database preserved; no administrator password is changed.'
    }
    $caddyFile = Join-Path $PSScriptRoot 'Caddyfile.ip'
    $configuration = [System.IO.File]::ReadAllText($caddyFile).Replace('203.0.113.10', $PublicIp)
    [System.IO.File]::WriteAllText($caddyFile, $configuration, (New-Object System.Text.UTF8Encoding($false)))
    Invoke-Checked (Join-Path $PSScriptRoot 'caddy.exe') @('validate', '--config', $caddyFile, '--adapter', 'caddyfile')
    Invoke-Checked 'icacls.exe' @($bundleRoot, '/inheritance:r', '/grant:r',
        '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-19:(OI)(CI)RX', '*S-1-5-32-545:(OI)(CI)RX')
    Invoke-Checked 'icacls.exe' @($dataRoot, '/inheritance:r', '/grant:r',
        '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-19:(OI)(CI)M')
    if (-not $SkipFirewall) {
        New-NetFirewallRule -Name RustDeskCompanyHTTPS -DisplayName 'RustDesk company HTTPS' `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80,443 `
            -Program (Join-Path $PSScriptRoot 'caddy.exe') | Out-Null
    }
    Invoke-Checked (Join-Path $PSScriptRoot 'rdm-api-service.exe') @('install')
    Invoke-Checked (Join-Path $PSScriptRoot 'rdm-https-service.exe') @('install')
    Invoke-Checked (Join-Path $PSScriptRoot 'rdm-api-service.exe') @('start')
    Invoke-Checked (Join-Path $PSScriptRoot 'rdm-https-service.exe') @('start')
    Write-Host "Services installed. Verify https://$PublicIp/healthz from another network before migrating clients."
    Write-Host 'Logs: data\logs. A running service does not by itself confirm certificate issuance.'
} finally {
    $env:RDM_DATABASE = $oldDatabase
    Pop-Location
}
