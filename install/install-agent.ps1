param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
    throw "AgentSurf repository root was not found. Run this script from the copied/cloned AgentSurf repository."
}

if (-not $PythonPath) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $PythonPath = $PythonCommand.Source
    }
}

if (-not $PythonPath) {
    $LocalCondaPython = Join-Path $RepoRoot ".conda\agentsurf\python.exe"
    if (Test-Path $LocalCondaPython) {
        $PythonPath = $LocalCondaPython
    }
}

if (-not $PythonPath) {
    throw "Python was not found. Activate your Python/Conda environment or pass -PythonPath <path-to-python.exe>."
}

$PythonPath = (Resolve-Path $PythonPath).Path
$PythonDir = Split-Path -Parent $PythonPath
$AgentSurfPath = Join-Path $PythonDir "Scripts\agentsurf.exe"

$RunningAgentSurf = @(
    Get-Process agentsurf -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -eq $AgentSurfPath
        }
        catch {
            $false
        }
    }
)
if ($RunningAgentSurf.Count -gt 0) {
    $ProcessIds = ($RunningAgentSurf | ForEach-Object { $_.Id }) -join ", "
    throw "agentsurf.exe is currently running from this environment (PID: $ProcessIds). Close AgentSurf/OpenClaw processes and retry."
}

Write-Host "AgentSurf install root: $RepoRoot"
Write-Host "Using Python: $PythonPath"
Invoke-Checked $PythonPath "--version"

Write-Host "Upgrading pip, setuptools, and wheel..."
Invoke-Checked $PythonPath "-m" "pip" "install" "--no-cache-dir" "--upgrade" "pip" "setuptools" "wheel"

Write-Host "Installing AgentSurf runtime dependencies..."
try {
    Invoke-Checked $PythonPath "-m" "pip" "install" "--no-cache-dir" "-e" ".[server,qwen,desktop]"
}
catch {
    Write-Host ""
    Write-Host "Install failed. If the error mentions WinError 32 or agentsurf.exe is in use,"
    Write-Host "close running AgentSurf/OpenClaw terminals and retry this script."
    throw
}

Write-Host "Verifying AgentSurf CLI commands..."
Invoke-Checked $PythonPath "-m" "agentsurf.cli" "acp" "--help"
Invoke-Checked $PythonPath "-m" "agentsurf.cli" "ezviz-agent" "--help"
Invoke-Checked $PythonPath "-m" "agentsurf.cli" "ezviz-desktop" "--help"
Invoke-Checked $PythonPath "-m" "agentsurf.cli" "ezviz-desktop-agent" "--help"

Write-Host ""
Write-Host "AgentSurf installation is complete."
Write-Host "This script does not install Python, OpenClaw, Chrome, or Playwright bundled browsers."
Write-Host "If you need Playwright's bundled browser later, run: python -m playwright install chromium"
Write-Host ""
Write-Host "Example EZVIZ desktop agent startup:"
Write-Host '  $env:PYTHONUTF8="1"'
Write-Host '  $env:DASHSCOPE_API_KEY="your-dashscope-api-key"'
Write-Host "  & `"$PythonPath`" -m agentsurf.cli ezviz-desktop-agent --exe-path `"C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe`" --debug"
