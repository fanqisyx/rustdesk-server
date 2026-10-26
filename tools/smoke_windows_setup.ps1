param([Parameter(Mandatory = $true)][string]$SetupFile)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'This installer smoke check requires a disposable GitHub runner.' }
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$target = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot 'dist/setup-smoke'))
$allowedRoot = (Join-Path $env:GITHUB_WORKSPACE 'dist').TrimEnd('\') + '\'
if (-not $target.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected setup smoke target.' }
$oldIp = $env:RDM_INSTALL_PUBLIC_IP
$oldPassword = $env:RDM_BOOTSTRAP_PASSWORD
$listener = $null
try {
    if (-not (Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(80,443,21114) })) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,21114)
        $listener.Start()
    }
    $env:RDM_INSTALL_PUBLIC_IP = '203.0.113.10'
    $env:RDM_BOOTSTRAP_PASSWORD = [Guid]::NewGuid().ToString('N')
    $process = Start-Process -FilePath (Resolve-Path -LiteralPath $SetupFile).ProviderPath `
        -ArgumentList @('/S', "/D=$target") -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) { throw 'Setup did not reject the occupied port in time.' }
    if ($process.ExitCode -ne 20) { throw "Setup did not reach the expected preflight conflict guard: $($process.ExitCode)" }
    if (Test-Path -LiteralPath (Join-Path $target 'rustdesk-management.exe')) { throw 'Setup copied application files before preflight passed.' }
    if (Get-Service RustDeskCompanyAPI,RustDeskCompanyHTTPS -ErrorAction SilentlyContinue) { throw 'Setup created services despite a conflict.' }
    Write-Output 'Graphical Setup safely refused a port conflict before copying files or creating services.'
} finally {
    if ($null -ne $listener) { $listener.Stop() }
    $env:RDM_INSTALL_PUBLIC_IP = $oldIp
    $env:RDM_BOOTSTRAP_PASSWORD = $oldPassword
}
