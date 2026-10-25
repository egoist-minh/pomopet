$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $repositoryRoot 'backend'
$specPath = Join-Path $backendDirectory 'pomopet-backend.spec'
$distDirectory = Join-Path $backendDirectory 'dist'
$workDirectory = Join-Path $backendDirectory 'build'

Push-Location $backendDirectory
try {
    conda run --no-capture-output -n pomopet python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $distDirectory `
        --workpath $workDirectory `
        $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$executable = Join-Path $distDirectory 'pomopet-backend.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Backend executable was not created: $executable"
}

Write-Host "Backend executable: $executable"
