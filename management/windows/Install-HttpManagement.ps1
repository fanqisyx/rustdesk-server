[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)][string]$PublicIp,
    [ValidateRange(1024,65535)][int]$HttpPort = 21114,
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
foreach ($relativeFile in @('rustdesk-management.exe', 'windows\rdm-api-service.exe', 'windows\rdm-api-service.xml')) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot $relativeFile) -PathType Leaf)) {
        throw "Incomplete Windows release bundle: $relativeFile"
    }
}
if (Get-Service -Name RustDeskCompanyAPI, RustDeskCompanyHTTPS -ErrorAction SilentlyContinue) {
    throw 'Company services already exist. Back up data and uninstall the previous management extension first.'
}
$listeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq $HttpPort })
if ($listeners.Count) {
    throw ('The selected HTTP port is occupied. Do not stop unknown services: ' +
        (($listeners | Select-Object LocalAddress,LocalPort,OwningProcess | Out-String).Trim()))
}
if (-not $SkipFirewall -and (Get-NetFirewallRule -Name RustDeskCompanyHTTP -ErrorAction SilentlyContinue)) {
    throw 'The company HTTP firewall rule already exists. Inspect it before installation.'
}
if (-not $PSCmdlet.ShouldProcess($bundleRoot,
        "Install plaintext HTTP API on TCP $HttpPort for $PublicIp; passwords and tokens are not encrypted")) { return }
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
    foreach ($directory in @($dataRoot, "$dataRoot\logs\api")) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $env:RDM_DATABASE = Join-Path $dataRoot 'management.sqlite3'
    if (-not (Test-Path -LiteralPath $env:RDM_DATABASE)) {
        Write-Host 'Create the first administrator. Enter a password of at least 12 characters.'
        Invoke-Checked (Join-Path $bundleRoot 'rustdesk-management.exe') @('create-admin', '--username', 'admin')
    } else {
        Write-Host 'Existing management database preserved; no administrator password is changed.'
    }
    $serviceFile = Join-Path $PSScriptRoot 'rdm-api-service.xml'
    [xml]$service = [System.IO.File]::ReadAllText($serviceFile)
    $service.service.arguments = "serve --host 0.0.0.0 --port $HttpPort"
    $service.Save($serviceFile)
    Invoke-Checked 'icacls.exe' @($bundleRoot, '/inheritance:r', '/grant:r',
        '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-19:(OI)(CI)RX', '*S-1-5-32-545:(OI)(CI)RX')
    Invoke-Checked 'icacls.exe' @($dataRoot, '/inheritance:r', '/grant:r',
        '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-19:(OI)(CI)M')
    if (-not $SkipFirewall) {
        New-NetFirewallRule -Name RustDeskCompanyHTTP -DisplayName 'RustDesk company plaintext HTTP' `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $HttpPort `
            -Program (Join-Path $bundleRoot 'rustdesk-management.exe') | Out-Null
    }
    Invoke-Checked (Join-Path $PSScriptRoot 'rdm-api-service.exe') @('install')
    Invoke-Checked (Join-Path $PSScriptRoot 'rdm-api-service.exe') @('start')
    Write-Host "HTTP management installed: http://${PublicIp}:$HttpPort"
    Write-Warning 'HTTP sends passwords and login tokens without encryption. No HTTPS service or certificate was installed.'
    Write-Host 'Ports 80/443 and hbbs/hbbr were not changed. Logs: data\logs\api.'
} finally {
    $env:RDM_DATABASE = $oldDatabase
    Pop-Location
}
