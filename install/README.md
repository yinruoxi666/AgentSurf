# AgentSurf Windows Deployment

This folder contains the PowerShell deployment entrypoint for installing
AgentSurf on another Windows machine after the repository has already been
copied, unzipped, or cloned there.

## Requirements

- Windows PowerShell.
- Python or Conda is already installed.
- The AgentSurf repository is already present on the target machine.
- Optional for desktop/browser workflows: Chrome, OpenClaw, and ESEzvizClient.

The installer does not install Python, Git, Chrome, OpenClaw, ESEzvizClient, or
Playwright bundled browsers.

## Install

Open PowerShell in the AgentSurf repository root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install\install-agent.ps1
```

The script looks for Python in this order:

1. The explicit `-PythonPath` argument.
2. `python` on `PATH`.
3. `.\.conda\agentsurf\python.exe` inside this repository.

To use a specific interpreter:

```powershell
.\install\install-agent.ps1 -PythonPath ".\.conda\agentsurf\python.exe"
```

The script installs AgentSurf with:

```powershell
python -m pip install --no-cache-dir -e ".[server,qwen,desktop]"
```

It also verifies:

```powershell
python -m agentsurf.cli acp --help
python -m agentsurf.cli ezviz-agent --help
python -m agentsurf.cli ezviz-desktop --help
python -m agentsurf.cli ezviz-desktop-agent --help
```

Close any running `agentsurf.exe` or OpenClaw-launched AgentSurf process before
running the installer. Windows cannot replace `agentsurf.exe` while it is in
use.

## EZVIZ Desktop Agent

Set the Qwen API key in the same PowerShell session:

```powershell
$env:PYTHONUTF8="1"
$env:DASHSCOPE_API_KEY="your-dashscope-api-key"
```

Start the desktop EZVIZ agent:

```powershell
python -m agentsurf.cli ezviz-desktop-agent --exe-path "C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe" --debug
```

For one-shot navigation:

```powershell
python -m agentsurf.cli ezviz-desktop --section playback --exe-path "C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe" --debug
```

The desktop visual confirmation colors can be adjusted in:

```text
config\ezviz_desktop\visual_confirmation.json
```

## OpenClaw ACP Command

Use this command in OpenClaw's custom ACP agent configuration, replacing the
repository path if needed:

```json
{
  "command": "C:\\Users\\yinruoxi\\Documents\\Codex\\AgentSurf\\.conda\\agentsurf\\Scripts\\agentsurf.exe",
  "args": [
    "acp",
    "--desktop-chrome",
    "--chrome-path",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "--ezviz-exe-path",
    "C:\\Program Files (x86)\\ESEzvizClient\\ESEzvizClient.exe"
  ]
}
```

If `agentsurf.exe` is on `PATH`, the command can be shortened to:

```json
{
  "command": "agentsurf",
  "args": [
    "acp",
    "--desktop-chrome",
    "--chrome-path",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "--ezviz-exe-path",
    "C:\\Program Files (x86)\\ESEzvizClient\\ESEzvizClient.exe"
  ]
}
```

## Optional Browser Install

If you need Playwright's bundled Chromium instead of local Chrome:

```powershell
python -m playwright install chromium
```

## Verification

```powershell
python -m unittest discover -s tests -v
```
