param([Parameter(Mandatory = $true)][string]$InstallRoot)
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
    throw 'A previous graphical management installation is registered. Uninstall it before choosing a new directory.'
}
if (Get-Service -Name RustDeskCompanyAPI, RustDeskCompanyHTTPS -ErrorAction SilentlyContinue) {
    throw 'Company management services already exist. Back up data and uninstall the previous management extension first.'
}
$occupied = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(80,443,21114) })
if ($occupied.Count) {
    throw ('Required ports are occupied. No existing service was stopped. ' +
        (($occupied | Select-Object LocalAddress,LocalPort,OwningProcess | Out-String).Trim()))
}
if (Get-NetFirewallRule -Name RustDeskCompanyHTTPS -ErrorAction SilentlyContinue) {
    throw 'The company HTTPS firewall rule already exists; inspect it before installation.'
}
Write-Output 'Preflight passed. Existing hbbs/hbbr will be retained.'
