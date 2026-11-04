param(
    [Parameter(Mandatory = $true)][string]$FrontendDirectory,
    [string]$PythonPath = (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'),
    [int]$Port = 8000,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$backendRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$frontendRoot = (Resolve-Path -LiteralPath $FrontendDirectory).Path
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Install the Backend environment or pass -PythonPath.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'package.json'))) { throw 'Pass the frontend directory containing package.json.' }
if (-not $SkipBuild) {
    Push-Location -LiteralPath $frontendRoot
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
$dist = Join-Path $frontendRoot 'dist'
if (-not (Test-Path -LiteralPath (Join-Path $dist 'index.html'))) { throw 'Frontend dist/index.html is missing.' }
Write-Output "Test-mode demo: http://127.0.0.1:$Port"
Write-Output 'This uses a fake predictor, not a trained model. Stop the server with Ctrl+C.'
Write-Output "For a temporary tunnel in another terminal: cloudflared tunnel --url http://127.0.0.1:$Port"
& $PythonPath (Join-Path $backendRoot 'run.py') --test-mode --port $Port --frontend-dist $dist
exit $LASTEXITCODE
