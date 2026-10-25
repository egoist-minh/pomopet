param(
    [string]$Executable = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\win-unpacked\PomoPet.exe')
)

$ErrorActionPreference = 'Stop'
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$temporaryData = Join-Path ([System.IO.Path]::GetTempPath()) ("PomoPet Packaged Smoke " + [guid]::NewGuid().ToString('N'))
$existingBackendIds = @(Get-Process -Name 'pomopet-backend' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$applicationProcess = $null
$startedAt = Get-Date

New-Item -ItemType Directory -Path $temporaryData | Out-Null
try {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $resolvedExecutable
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    [void]$startInfo.Environment.Remove('ELECTRON_RUN_AS_NODE')
    $startInfo.Environment['POMOPET_USER_DATA_DIR'] = $temporaryData
    $rendererMarkerPath = Join-Path $temporaryData 'renderer-ready'
    $startInfo.Environment['POMOPET_SMOKE_MARKER'] = $rendererMarkerPath
    $applicationProcess = [System.Diagnostics.Process]::Start($startInfo)

    $databasePath = Join-Path $temporaryData 'pomopet.db'
    $ready = $false
    for ($attempt = 0; $attempt -lt 150; $attempt++) {
        if ($applicationProcess.HasExited) {
            $startupErrorPath = Join-Path $temporaryData 'startup-error.log'
            $startupError = if (Test-Path -LiteralPath $startupErrorPath) { Get-Content -Raw -LiteralPath $startupErrorPath } else { 'no startup log' }
            throw "Packaged app exited early with code $($applicationProcess.ExitCode): $startupError"
        }
        if ((Test-Path -LiteralPath $databasePath -PathType Leaf) -and (Test-Path -LiteralPath $rendererMarkerPath -PathType Leaf)) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw 'Packaged app did not initialize both its backend and renderer' }

    $coldStartMilliseconds = [int]((Get-Date) - $startedAt).TotalMilliseconds
    Start-Sleep -Seconds 2
    $newBackends = @(Get-Process -Name 'pomopet-backend' -ErrorAction SilentlyContinue | Where-Object { $_.Id -notin $existingBackendIds })
    if ($newBackends.Count -eq 0) { throw 'Packaged app did not keep a backend process running' }

    $applicationProcess.Refresh()
    $workingSetBytes = $applicationProcess.WorkingSet64 + (($newBackends | Measure-Object -Property WorkingSet64 -Sum).Sum)
    Write-Host "Packaged app smoke test passed. cold_start_ms=$coldStartMilliseconds idle_working_set_bytes=$workingSetBytes"
} finally {
    if ($applicationProcess -and -not $applicationProcess.HasExited) {
        & taskkill.exe /PID $applicationProcess.Id /T /F 2>&1 | Out-Null
        [void]$applicationProcess.WaitForExit(5000)
    }

    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        $remaining = @(Get-Process -Name 'pomopet-backend' -ErrorAction SilentlyContinue | Where-Object { $_.Id -notin $existingBackendIds })
        if ($remaining.Count -eq 0) { break }
        Start-Sleep -Milliseconds 200
    }
    if ($remaining.Count -gt 0) { throw 'Packaged backend remained after Electron exited' }

    $expectedPrefix = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $resolvedTemporaryData = [System.IO.Path]::GetFullPath($temporaryData)
    if ($resolvedTemporaryData.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        for ($attempt = 0; $attempt -lt 10; $attempt++) {
            try {
                Remove-Item -LiteralPath $resolvedTemporaryData -Recurse -Force
                break
            } catch {
                if ($attempt -eq 9) { throw }
                Start-Sleep -Milliseconds 200
            }
        }
    }
}
