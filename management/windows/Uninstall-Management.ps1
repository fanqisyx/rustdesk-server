[CmdletBinding(SupportsShouldProcess = $true)]
param()
$ErrorActionPreference = 'Stop'
$bundleRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).ProviderPath
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $WhatIfPreference -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run the uninstaller from an elevated PowerShell window.'
}
$ownedServices = @()
foreach ($record in @(@{Name='RustDeskCompanyHTTPS'; File='rdm-https-service.exe'},
                       @{Name='RustDeskCompanyAPI'; File='rdm-api-service.exe'})) {
    $service = Get-CimInstance Win32_Service -Filter "Name='$($record.Name)'"
    if ($null -eq $service) { continue }
    $wrapper = Join-Path $PSScriptRoot $record.File
    $expected = '^\s*"?' + [regex]::Escape($wrapper) + '"?(\s|$)'
    if ($service.PathName -notmatch $expected) {
        throw "Refusing to change a service registered to another directory: $($record.Name)"
    }
    $ownedServices += @{Name=$record.Name; Wrapper=$wrapper}
}
foreach ($record in $ownedServices) {
    if (-not $PSCmdlet.ShouldProcess($record.Name, 'Stop and uninstall this management service')) { continue }
    if ((Get-Service $record.Name).Status -ne 'Stopped') {
        & $record.Wrapper stop
        if ($LASTEXITCODE -ne 0) { throw "Could not stop $($record.Name)" }
    }
    & $record.Wrapper uninstall
    if ($LASTEXITCODE -ne 0) { throw "Could not uninstall $($record.Name)" }
}
$rule = Get-NetFirewallRule -Name RustDeskCompanyHTTPS -ErrorAction SilentlyContinue
if ($null -ne $rule) {
    $programs = @($rule | Get-NetFirewallApplicationFilter | Select-Object -ExpandProperty Program)
    if ($programs.Count -eq 1 -and $programs[0] -ieq (Join-Path $PSScriptRoot 'caddy.exe')) {
        if ($PSCmdlet.ShouldProcess('RustDeskCompanyHTTPS', 'Remove this application firewall rule')) {
            $rule | Remove-NetFirewallRule
        }
    } else {
        Write-Warning 'The firewall rule now points elsewhere; it was retained.'
    }
}
Write-Output "Management services removed. Data retained at $bundleRoot\data. hbbs/hbbr were not changed."
