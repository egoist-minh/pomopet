param(
    [string]$Executable = (Join-Path (Split-Path -Parent $PSScriptRoot) 'backend\dist\pomopet-backend.exe')
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$temporaryData = Join-Path ([System.IO.Path]::GetTempPath()) ("pomopet-smoke-" + [guid]::NewGuid().ToString('N'))
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$tokenBytes = New-Object byte[] 32
$randomNumberGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$randomNumberGenerator.GetBytes($tokenBytes)
$randomNumberGenerator.Dispose()
$token = [Convert]::ToBase64String($tokenBytes)
$process = $null

New-Item -ItemType Directory -Path $temporaryData | Out-Null
try {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $resolvedExecutable
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.Environment['POMOPET_RUNTIME_TOKEN'] = $token
    $startInfo.Arguments = "--host 127.0.0.1 --port $port --data-dir `"$temporaryData`" --parent-pid $PID"
    $process = [System.Diagnostics.Process]::Start($startInfo)

    $headers = @{ 'X-PomoPet-Token' = $token }
    $ready = $false
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -Headers $headers -TimeoutSec 1
            if ($response.status -eq 'ok') {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    if (-not $ready) { throw 'Packaged backend did not become healthy' }

    $unauthorized = $false
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/tasks/" -TimeoutSec 2 | Out-Null
    } catch {
        $unauthorized = $_.Exception.Response.StatusCode.value__ -eq 401
    }
    if (-not $unauthorized) { throw 'Packaged backend accepted a request without its runtime token' }
    if (-not (Test-Path -LiteralPath (Join-Path $temporaryData 'pomopet.db'))) {
        throw 'Packaged backend did not create its database in the supplied data directory'
    }

    Write-Host 'Packaged backend smoke test passed.'
} finally {
    if ($process -and -not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F 2>&1 | Out-Null
        [void]$process.WaitForExit(5000)
    }
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
