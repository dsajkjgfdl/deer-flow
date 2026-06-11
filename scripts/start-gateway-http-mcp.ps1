param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8001,
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            continue
        }

        $name = $matches[1]
        if ([Environment]::GetEnvironmentVariable($name, "Process")) {
            continue
        }

        $value = $matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$configPath = Join-Path $repoRoot "config.yaml"
$extensionsPath = Join-Path $repoRoot "extensions_config.local-http.json"
$deerFlowHome = Join-Path $backendDir ".deer-flow"

Import-DotEnv (Join-Path $repoRoot ".env")

foreach ($requiredPath in @($configPath, $extensionsPath, $deerFlowHome)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required DeerFlow path not found: $requiredPath"
    }
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv command was not found in PATH"
}

$env:DEER_FLOW_PROJECT_ROOT = $repoRoot
$env:DEER_FLOW_CONFIG_PATH = $configPath
$env:DEER_FLOW_EXTENSIONS_CONFIG_PATH = $extensionsPath
$env:DEER_FLOW_HOME = $deerFlowHome
$env:PYTHONPATH = $backendDir

$arguments = @(
    "run",
    "uvicorn",
    "app.gateway.app:app",
    "--host", $HostAddress,
    "--port", [string]$Port
)
if (-not $NoReload) {
    $arguments += "--reload"
}

Write-Host "Starting DeerFlow Gateway at http://127.0.0.1:${Port}"
Write-Host "Using MCP config: $extensionsPath"
Push-Location $backendDir
try {
    & uv @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
