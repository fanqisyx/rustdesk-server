param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repositoryRoot
try {
    & $Python -c "import sys; assert sys.platform == 'win32', 'Build on Windows'"
    if ($LASTEXITCODE -ne 0) { throw 'A Windows Python installation is required.' }
    $staticPath = Join-Path $repositoryRoot 'management/static'
    & $Python -m PyInstaller --noconfirm --onefile --console --noupx `
        --name rustdesk-management --paths management `
        --add-data "${staticPath}:static" --collect-submodules uvicorn `
        --hidden-import backports.tarfile `
        --distpath dist/native --workpath build/management --specpath build `
        management/app.py
    if ($LASTEXITCODE -ne 0) { throw 'Management executable build failed.' }
    if (-not (Test-Path -LiteralPath 'dist/native/rustdesk-management.exe')) {
        throw 'The expected executable was not produced.'
    }
    & $Python tools/collect_runtime_licenses.py
    if ($LASTEXITCODE -ne 0) { throw 'Runtime license collection failed.' }
    Write-Output (Join-Path $repositoryRoot 'dist/native/rustdesk-management.exe')
} finally {
    Pop-Location
}
