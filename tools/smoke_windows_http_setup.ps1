param([Parameter(Mandatory = $true)][string]$SetupFile)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'This installer check requires a disposable GitHub runner.' }
$target = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../dist/http-setup-smoke'))
$allowedRoot = (Join-Path $env:GITHUB_WORKSPACE 'dist').TrimEnd('\') + '\'
if (-not $target.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected HTTP setup target.' }
$reservation = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,0)
$reservation.Start()
$httpPort = $reservation.LocalEndpoint.Port
$saved = @{}
foreach ($name in @('RDM_INSTALL_PUBLIC_IP','RDM_INSTALL_HTTP_PORT','RDM_BOOTSTRAP_PASSWORD')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name)
}
try {
    $env:RDM_INSTALL_PUBLIC_IP = '203.0.113.10'
    $env:RDM_INSTALL_HTTP_PORT = [string]$httpPort
    $env:RDM_BOOTSTRAP_PASSWORD = [Guid]::NewGuid().ToString('N')
    $setup = (Resolve-Path -LiteralPath $SetupFile).ProviderPath
    $process = Start-Process -FilePath $setup -ArgumentList @('/S', "/D=$target") -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000) -or $process.ExitCode -ne 20) {
        throw 'HTTP setup did not refuse the occupied selected port before installation.'
    }
    if (Test-Path -LiteralPath (Join-Path $target 'rustdesk-management.exe')) { throw 'HTTP setup copied files before preflight passed.' }
    $reservation.Stop()
    $process = Start-Process -FilePath $setup -ArgumentList @('/S', "/D=$target") -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000) -or $process.ExitCode -ne 0) { throw "HTTP setup failed: $($process.ExitCode)" }
    $healthy = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:$httpPort/healthz" -TimeoutSec 2
            $healthy = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'HTTP setup did not start a healthy API service.' }
    if (Get-Service RustDeskCompanyHTTPS -ErrorAction SilentlyContinue) { throw 'HTTP setup unexpectedly installed HTTPS.' }
    $rule = Get-NetFirewallRule -Name RustDeskCompanyHTTP
    $ports = @($rule | Get-NetFirewallPortFilter | Select-Object -ExpandProperty LocalPort)
    if ($ports.Count -ne 1 -or $ports[0] -ne [string]$httpPort) { throw 'HTTP setup opened unexpected firewall ports.' }
    $baseUrl = "http://127.0.0.1:$httpPort"
    $account = @{username='http-smoke'; password=[Guid]::NewGuid().ToString('N')}
    $account.password_confirmation = $account.password
    $registered = Invoke-RestMethod "$baseUrl/api/register" -Method Post -ContentType application/json -Body ($account | ConvertTo-Json)
    if ($registered.service -ne 'rustdesk-company-management') { throw 'HTTP registration returned an unexpected service.' }
    $null = Invoke-RestMethod "$baseUrl/api/login" -Method Post -ContentType application/json -Body ($account | ConvertTo-Json)
    Write-Output 'HTTP Setup installed the API on the selected port and passed registration/login without installing HTTPS.'
} finally {
    $reservation.Stop()
    if (Test-Path -LiteralPath (Join-Path $target 'Uninstall.exe')) {
        $process = Start-Process -FilePath (Join-Path $target 'Uninstall.exe') `
            -ArgumentList @('/S', "_?=$target") -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(60000) -or $process.ExitCode -ne 0) { throw 'HTTP Setup uninstall failed.' }
        if (Get-Service RustDeskCompanyAPI -ErrorAction SilentlyContinue) { throw 'HTTP service was not removed.' }
        if (Get-NetFirewallRule -Name RustDeskCompanyHTTP -ErrorAction SilentlyContinue) { throw 'HTTP firewall rule was not removed.' }
        if (-not (Test-Path -LiteralPath (Join-Path $target 'data/management.sqlite3'))) { throw 'HTTP uninstall removed the database.' }
    }
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
}
