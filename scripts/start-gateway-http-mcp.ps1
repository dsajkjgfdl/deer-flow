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

function Add-NoProxyHost {
    param([string]$HostName)

    if (-not $HostName) {
        return
    }

    $items = @()
    if ($env:NO_PROXY) {
        $items = $env:NO_PROXY -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }
    if ($items -notcontains $HostName) {
        $items += $HostName
        $env:NO_PROXY = ($items -join ",")
    }
}

function Add-NoProxyUrlHost {
    param([string]$Url)

    if (-not $Url) {
        return
    }

    try {
        $uri = [System.Uri]$Url
        Add-NoProxyHost $uri.Host
    }
    catch {
        return
    }
}

function Require-EnvironmentVariable {
    param([string]$Name)

    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, "Process"))) {
        throw "Required environment variable is missing: $Name"
    }
}

function Initialize-HrLlmProviderEnvironment {
    if (-not $env:HR_LLM_PROFILE) {
        $env:HR_LLM_PROFILE = "qwen"
    }
    $profile = $env:HR_LLM_PROFILE.ToLowerInvariant()
    if ($profile -notin @("qwen", "deepseek")) {
        throw "HR_LLM_PROFILE must be either 'qwen' or 'deepseek'"
    }

    if (-not $env:QWEN_CHAT_API_BASE) {
        if ($env:VLLM_CHAT_API_BASE) {
            $env:QWEN_CHAT_API_BASE = $env:VLLM_CHAT_API_BASE
        }
        else {
            $env:QWEN_CHAT_API_BASE = "http://36.212.39.231:11435/v1"
        }
    }
    if (-not $env:QWEN_CHAT_MODEL) {
        if ($env:VLLM_CHAT_MODEL) {
            $env:QWEN_CHAT_MODEL = $env:VLLM_CHAT_MODEL
        }
        else {
            $env:QWEN_CHAT_MODEL = "Qwen3"
        }
    }
    if (-not $env:QWEN_API_KEY) {
        if ($env:VLLM_API_KEY) {
            $env:QWEN_API_KEY = $env:VLLM_API_KEY
        }
        elseif ($env:OPENAI_API_KEY) {
            $env:QWEN_API_KEY = $env:OPENAI_API_KEY
        }
    }

    if (-not $env:VLLM_CHAT_API_BASE) { $env:VLLM_CHAT_API_BASE = $env:QWEN_CHAT_API_BASE }
    if (-not $env:VLLM_CHAT_MODEL) { $env:VLLM_CHAT_MODEL = $env:QWEN_CHAT_MODEL }
    if (-not $env:VLLM_API_KEY) { $env:VLLM_API_KEY = $env:QWEN_API_KEY }

    if (-not $env:DEEPSEEK_API_BASE) {
        $env:DEEPSEEK_API_BASE = "https://api.deepseek.com"
    }
    if (-not $env:DEEPSEEK_MODEL) {
        $env:DEEPSEEK_MODEL = "deepseek-v4-pro"
    }
    if (-not $env:DEEPSEEK_API_KEY -and $env:DASHSCOPE_API_KEY) {
        $env:DEEPSEEK_API_KEY = $env:DASHSCOPE_API_KEY
    }

    Add-NoProxyUrlHost $env:QWEN_CHAT_API_BASE
    Add-NoProxyUrlHost $env:DEEPSEEK_API_BASE
    Add-NoProxyHost "127.0.0.1"
    Add-NoProxyHost "localhost"

    Require-EnvironmentVariable "QWEN_API_KEY"
    Require-EnvironmentVariable "DEEPSEEK_API_KEY"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$configPath = Join-Path $repoRoot "config.yaml"
$extensionsPath = Join-Path $repoRoot "extensions_config.local-http.json"
$deerFlowHome = Join-Path $backendDir ".deer-flow"

Import-DotEnv (Join-Path $repoRoot ".env")

Initialize-HrLlmProviderEnvironment

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
