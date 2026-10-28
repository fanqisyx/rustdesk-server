param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [ValidateRange(1024,65535)][int]$HttpPort = 21114
)
$ErrorActionPreference = 'Stop'
$targetRoot = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($targetRoot -eq [System.IO.Path]::GetPathRoot($targetRoot).TrimEnd('\') -or
    $targetRoot.StartsWith($env:WINDIR, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a dedicated empty application directory outside Windows and drive roots.'
}
if ((Test-Path -LiteralPath $targetRoot) -and @(Get-ChildItem -Force -LiteralPath $targetRoot).Count) {
    throw 'Choose an empty application directory. Existing files and data will not be overwritten.'
}
if (Test-Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\RustDeskCompanyServer') {
    throw 'A management installation is already registered. Back up data and uninstall it first.'
}
if (Get-Service -Name RustDeskCompanyAPI, RustDeskCompanyHTTPS -ErrorAction SilentlyContinue) {
    throw 'Company management services already exist. Back up data and uninstall the previous management extension first.'
}
$occupied = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq $HttpPort })
if ($occupied.Count) {
    throw ('The selected HTTP port is occupied. No existing service was stopped. ' +
        (($occupied | Select-Object LocalAddress,LocalPort,OwningProcess | Out-String).Trim()))
}
if (Get-NetFirewallRule -Name RustDeskCompanyHTTP -ErrorAction SilentlyContinue) {
    throw 'The company HTTP firewall rule already exists; inspect it before installation.'
}
Write-Output "HTTP preflight passed for TCP $HttpPort. Ports 80/443 and hbbs/hbbr will be retained."
