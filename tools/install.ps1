$ErrorActionPreference = 'Stop'
$TaskRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $TaskRoot 'local-data/python'
$RuntimeExe = Join-Path $RuntimeDir 'python.exe'
if (-not (Test-Path -LiteralPath $RuntimeExe)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RuntimeDir) | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'python') -Destination $RuntimeDir -Recurse
}
& $RuntimeExe -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Write-Host 'Local runtime ready. Start with pnpm tauri dev; startup never installs dependencies.'
