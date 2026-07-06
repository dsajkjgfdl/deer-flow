[CmdletBinding()]
param(
    [string]$HrMcpSuiteRoot = "",
    [string]$OutputDir = "",
    [string]$Tag = "offline",
    [string]$Platform = "linux/amd64",
    [string]$PipIndexUrl = $env:PIP_INDEX_URL,
    [string]$PipExtraIndexUrl = $env:PIP_EXTRA_INDEX_URL,
    [string]$PipTrustedHost = $env:PIP_TRUSTED_HOST,
    [string]$UvIndexUrl = $env:UV_INDEX_URL,
    [string]$NpmRegistry = $env:NPM_REGISTRY,
    [string]$AptMirror = $env:APT_MIRROR,
    [string]$PythonImage = "python:3.12-slim-bookworm",
    [string]$FrontendNodeImage = "node:22-alpine",
    [string]$BackendNodeImage = "node:22-bookworm-slim",
    [string]$UvImage = "ghcr.io/astral-sh/uv:0.7.20",
    [string]$DockerCliImage = "docker:cli",
    [string]$NginxImage = "nginx:alpine",
    [string]$MysqlImage = "mysql:8.4",
    [string]$Neo4jImage = "neo4j:5",
    [switch]$SkipBuild,
    [switch]$SkipPull,
    [switch]$SkipSave,
    [switch]$SkipBundle
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Host ">> $FilePath $($Arguments -join ' ')"
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Add-BuildArg {
    param(
        [Parameter(Mandatory = $true)][System.Collections.Generic.List[string]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowEmptyString()][string]$Value
    )

    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        $Arguments.Add("--build-arg")
        $Arguments.Add("${Name}=${Value}")
    }
}

function Copy-Tree {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExcludeDirectory = @(),
        [string[]]$ExcludeFile = @()
    )

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    $args = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($ExcludeDirectory.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludeDirectory
    }
    if ($ExcludeFile.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludeFile
    }

    & robocopy @args | Out-Host
    $code = $LASTEXITCODE
    if ($code -gt 7) {
        throw "robocopy failed with exit code $code while copying $Source"
    }
    $global:LASTEXITCODE = 0
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$deerFlowRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path

if ([string]::IsNullOrWhiteSpace($HrMcpSuiteRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($env:HR_MCP_SUITE_ROOT)) {
        $HrMcpSuiteRoot = $env:HR_MCP_SUITE_ROOT
    } elseif (Test-Path -LiteralPath "D:\study\my-mcp\hr-mcp-suite") {
        $HrMcpSuiteRoot = "D:\study\my-mcp\hr-mcp-suite"
    } else {
        throw "Set -HrMcpSuiteRoot or HR_MCP_SUITE_ROOT to the hr-mcp-suite repository path."
    }
}
$HrMcpSuiteRoot = (Resolve-Path $HrMcpSuiteRoot).Path

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $deerFlowRoot "dist\hr-boss-offline"
}
$OutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)

$frontendImage = "hr-boss/deer-flow-frontend:$Tag"
$gatewayImage = "hr-boss/deer-flow-gateway:$Tag"
$text2cypherImage = "hr-boss/text2cypher-mcp:$Tag"
$graphragImage = "hr-boss/hr-graphrag-mcp:$Tag"
$dataBuilderImage = "hr-boss/hr-data-builder:$Tag"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if (-not $SkipBuild) {
    $frontendArgs = [System.Collections.Generic.List[string]]::new()
    $frontendArgs.AddRange([string[]]@(
        "build", "--platform", $Platform,
        "-f", (Join-Path $deerFlowRoot "frontend\Dockerfile"),
        "--target", "prod",
        "-t", $frontendImage
    ))
    Add-BuildArg $frontendArgs "NPM_REGISTRY" $NpmRegistry
    Add-BuildArg $frontendArgs "FRONTEND_NODE_IMAGE" $FrontendNodeImage
    $frontendArgs.Add($deerFlowRoot)
    Invoke-Checked docker $frontendArgs.ToArray()

    $gatewayArgs = [System.Collections.Generic.List[string]]::new()
    $gatewayArgs.AddRange([string[]]@(
        "build", "--platform", $Platform,
        "-f", (Join-Path $deerFlowRoot "backend\Dockerfile"),
        "-t", $gatewayImage
    ))
    Add-BuildArg $gatewayArgs "APT_MIRROR" $AptMirror
    Add-BuildArg $gatewayArgs "PYTHON_IMAGE" $PythonImage
    Add-BuildArg $gatewayArgs "BACKEND_NODE_IMAGE" $BackendNodeImage
    Add-BuildArg $gatewayArgs "UV_IMAGE" $UvImage
    Add-BuildArg $gatewayArgs "DOCKER_CLI_IMAGE" $DockerCliImage
    Add-BuildArg $gatewayArgs "UV_INDEX_URL" $(if ([string]::IsNullOrWhiteSpace($UvIndexUrl)) { "https://pypi.org/simple" } else { $UvIndexUrl })
    $gatewayArgs.Add($deerFlowRoot)
    Invoke-Checked docker $gatewayArgs.ToArray()

    foreach ($mcp in @(
        @{ Dockerfile = "Dockerfile.text2cypher"; Image = $text2cypherImage },
        @{ Dockerfile = "Dockerfile.graphrag-mcp"; Image = $graphragImage }
    )) {
        $mcpArgs = [System.Collections.Generic.List[string]]::new()
        $mcpArgs.AddRange([string[]]@(
            "build", "--platform", $Platform,
            "-f", (Join-Path $HrMcpSuiteRoot "deployment\docker\$($mcp.Dockerfile)"),
            "-t", [string]$mcp.Image
        ))
        Add-BuildArg $mcpArgs "APT_MIRROR" $AptMirror
        Add-BuildArg $mcpArgs "PYTHON_IMAGE" $PythonImage
        Add-BuildArg $mcpArgs "PIP_INDEX_URL" $PipIndexUrl
        Add-BuildArg $mcpArgs "PIP_EXTRA_INDEX_URL" $PipExtraIndexUrl
        Add-BuildArg $mcpArgs "PIP_TRUSTED_HOST" $PipTrustedHost
        $mcpArgs.Add($HrMcpSuiteRoot)
        Invoke-Checked docker $mcpArgs.ToArray()
    }

    $contextRoot = Join-Path $OutputDir "build-context"
    if (Test-Path -LiteralPath $contextRoot) {
        Remove-Item -LiteralPath $contextRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $contextRoot "deer-flow\deployment\hr-boss") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $contextRoot "deer-flow\backend\scripts") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $contextRoot "hr-mcp-suite\services") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $contextRoot "hr-mcp-suite\data") | Out-Null
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "deployment\hr-boss\sync_huoju_hr_data.py") -Destination (Join-Path $contextRoot "deer-flow\deployment\hr-boss\sync_huoju_hr_data.py")
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "backend\scripts\import_huoju_hr_mysql.py") -Destination (Join-Path $contextRoot "deer-flow\backend\scripts\import_huoju_hr_mysql.py")
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "backend\scripts\clean_huoju_hr_mysql.py") -Destination (Join-Path $contextRoot "deer-flow\backend\scripts\clean_huoju_hr_mysql.py")
    Copy-Tree -Source (Join-Path $HrMcpSuiteRoot "services\graphrag-mcp") -Destination (Join-Path $contextRoot "hr-mcp-suite\services\graphrag-mcp") -ExcludeDirectory @(".venv", ".pytest_cache", "__pycache__") -ExcludeFile @("*.pyc", "*.pyo", "*.log")
    Copy-Tree -Source (Join-Path $HrMcpSuiteRoot "data\byog_graphrag") -Destination (Join-Path $contextRoot "hr-mcp-suite\data\byog_graphrag") -ExcludeDirectory @(".venv", ".pytest_cache", "__pycache__", "cache", "hr_agent", "logs", "output") -ExcludeFile @("*.pyc", "*.pyo", "*.log")

    $dataBuilderArgs = [System.Collections.Generic.List[string]]::new()
    $dataBuilderArgs.AddRange([string[]]@(
        "build", "--platform", $Platform,
        "-f", (Join-Path $deerFlowRoot "deployment\hr-boss\Dockerfile.data-builder.offline"),
        "-t", $dataBuilderImage
    ))
    Add-BuildArg $dataBuilderArgs "APT_MIRROR" $AptMirror
    Add-BuildArg $dataBuilderArgs "PYTHON_IMAGE" $PythonImage
    Add-BuildArg $dataBuilderArgs "PIP_INDEX_URL" $PipIndexUrl
    Add-BuildArg $dataBuilderArgs "PIP_EXTRA_INDEX_URL" $PipExtraIndexUrl
    Add-BuildArg $dataBuilderArgs "PIP_TRUSTED_HOST" $PipTrustedHost
    $dataBuilderArgs.Add($contextRoot)
    Invoke-Checked docker $dataBuilderArgs.ToArray()
}

if (-not $SkipPull) {
    foreach ($image in @($NginxImage, $MysqlImage, $Neo4jImage)) {
        Invoke-Checked docker @("pull", $image)
    }
}

$imageTar = Join-Path $OutputDir "hr-boss-images.tar"
if (-not $SkipSave) {
    $images = @(
        $frontendImage,
        $gatewayImage,
        $text2cypherImage,
        $graphragImage,
        $dataBuilderImage,
        $NginxImage,
        $MysqlImage,
        $Neo4jImage
    )
    Invoke-Checked docker (@("save", "-o", $imageTar) + $images)
}

$bundleRoot = Join-Path $OutputDir "deploy-bundle"
$bundleTar = Join-Path $OutputDir "hr-boss-deploy-bundle.tgz"
if (-not $SkipBundle) {
    if (Test-Path -LiteralPath $bundleRoot) {
        Remove-Item -LiteralPath $bundleRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $bundleRoot | Out-Null

    New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "docker\nginx") | Out-Null
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "docker\docker-compose.hr-boss.offline.yaml") -Destination (Join-Path $bundleRoot "docker\docker-compose.hr-boss.offline.yaml")
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "docker\nginx\nginx.conf") -Destination (Join-Path $bundleRoot "docker\nginx\nginx.conf")

    New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "deployment\hr-boss") | Out-Null
    foreach ($file in @(
        "offline.env.example",
        "config.hr-boss.example.yaml",
        "extensions_config.docker.json"
    )) {
        Copy-Item -LiteralPath (Join-Path $deerFlowRoot "deployment\hr-boss\$file") -Destination (Join-Path $bundleRoot "deployment\hr-boss\$file")
    }
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "deployment\hr-boss\load-and-run.sh") -Destination (Join-Path $bundleRoot "load-and-run.sh")

    New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "backend\.deer-flow") | Out-Null
    Copy-Tree -Source (Join-Path $deerFlowRoot "backend\.deer-flow\agents") -Destination (Join-Path $bundleRoot "backend\.deer-flow\agents")
    Copy-Tree -Source (Join-Path $deerFlowRoot "skills") -Destination (Join-Path $bundleRoot "skills")

    New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "frontend") | Out-Null
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot "frontend\.env.example") -Destination (Join-Path $bundleRoot "frontend\.env.example")
    Copy-Item -LiteralPath (Join-Path $deerFlowRoot ".env.example") -Destination (Join-Path $bundleRoot ".env.example")

    New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "hr-mcp-suite\data") | Out-Null
    Copy-Tree -Source (Join-Path $HrMcpSuiteRoot "data\byog_graphrag") -Destination (Join-Path $bundleRoot "hr-mcp-suite\data\byog_graphrag") -ExcludeDirectory @(".venv", ".pytest_cache", "__pycache__", "cache", "hr_agent", "logs", "output") -ExcludeFile @("*.pyc", "*.pyo", "*.log")

    if (Test-Path -LiteralPath $bundleTar) {
        Remove-Item -LiteralPath $bundleTar -Force
    }
    Invoke-Checked tar @("-czf", $bundleTar, "-C", $bundleRoot, ".")
}

Write-Host ""
Write-Host "Offline bundle ready:"
Write-Host "  Images: $imageTar"
Write-Host "  Deploy: $bundleTar"
Write-Host ""
Write-Host "Upload both files to the server, extract the deploy bundle, then run:"
Write-Host "  bash load-and-run.sh /path/to/hr-boss-images.tar"
