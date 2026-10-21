$ErrorActionPreference = 'Stop'
$TaskRoot = Split-Path -Parent $PSScriptRoot
$RuntimeExe = Join-Path $TaskRoot 'local-data/python/python.exe'
$GpuRuntime = Join-Path $TaskRoot 'local-data/gpu-runtime'
if (-not (Test-Path -LiteralPath $RuntimeExe)) { throw 'Run tools/install.ps1 first.' }
& $RuntimeExe -m pip install --disable-pip-version-check --no-deps --upgrade --target $GpuRuntime --index-url https://pypi.org/simple --find-links (Join-Path $TaskRoot 'local-data/gpu-wheels') -r (Join-Path $PSScriptRoot 'requirements-gpu.txt')
if ($LASTEXITCODE -ne 0) { throw 'GPU runtime installation failed.' }
$PreviousDevice = $env:HSR_OCR_DEVICE
try {
    $env:HSR_OCR_DEVICE = 'gpu'
    & $RuntimeExe (Join-Path $PSScriptRoot 'check_gpu.py')
    if ($LASTEXITCODE -ne 0) { throw 'GPU OCR validation failed; existing device setting was not changed.' }
} finally {
    $env:HSR_OCR_DEVICE = $PreviousDevice
}
$ConfigPath = Join-Path $TaskRoot 'local-data/ocr-runtime.json'
if (Test-Path -LiteralPath $ConfigPath) {
    Copy-Item -LiteralPath $ConfigPath -Destination ($ConfigPath + '.bak') -Force
}
[System.IO.File]::WriteAllText($ConfigPath, '{"device":"gpu"}', [System.Text.UTF8Encoding]::new($false))
Write-Host 'GPU OCR verified and enabled. Restart the scanner. CPU runtime remains available.'
