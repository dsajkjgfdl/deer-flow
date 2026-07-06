param(
    [string]$Config = "",
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$BackendDir = Join-Path $RepoRoot "backend"
$Cleaner = Join-Path $BackendDir "scripts\clear_conversation_data.py"

if ([string]::IsNullOrWhiteSpace($Config)) {
    $Config = Join-Path $RepoRoot "config.yaml"
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = $RepoRoot
}

if (-not (Test-Path -LiteralPath $Cleaner)) {
    throw "Cleaner script not found: $Cleaner"
}

Push-Location $BackendDir
try {
    uv run python $Cleaner --config $Config --project-root $ProjectRoot --yes
}
finally {
    Pop-Location
}
