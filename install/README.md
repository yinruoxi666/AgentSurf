# AgentSurf Install Commands

This folder contains installation commands for AgentSurf and OpenClaw ACP
integration.

## What It Installs

- AgentSurf editable package.
- Browser server dependencies: FastAPI, Uvicorn, Playwright.
- Qwen/OpenAI-compatible SDK dependency: OpenAI Python SDK.
- Windows desktop automation dependencies: pywinauto, pyautogui, psutil.
- `agentsurf` CLI entry point.

It does not install Python, OpenClaw, Chrome, or Playwright bundled browsers.
The default browser path assumes you already have desktop Chrome installed.

## Usage

Run from PowerShell after activating the Python or Conda environment you want to
use:

```powershell
.\install\install-agent.ps1
```

If `python` is not on `PATH`, the script falls back to
`.\.conda\agentsurf\python.exe` when it exists. You can also pass an explicit
interpreter:

```powershell
.\install\install-agent.ps1 -PythonPath ".\.conda\agentsurf\python.exe"
```

If script execution is blocked by Windows policy for this terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install\install-agent.ps1
```

Close any running `agentsurf.exe` or OpenClaw-launched AgentSurf process before
running the installer. Windows cannot replace `agentsurf.exe` while it is in
use.

## OpenClaw ACP Command

Use this command in OpenClaw's custom ACP agent configuration:

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
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  ]
}
```

## Optional Qwen Environment

Set these only when you want normal Qwen chat/routing features:

```powershell
$env:DASHSCOPE_API_KEY="your-dashscope-api-key"
$env:QWEN_MODEL="qwen-plus"
$env:QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

`QWEN_MODEL` and `QWEN_BASE_URL` are optional because AgentSurf has defaults.

## Verification

```powershell
agentsurf acp --help
agentsurf ezviz-agent --help
agentsurf ezviz-desktop --help
python -m unittest discover -s tests -v
```

If you need Playwright's bundled browser instead of local Chrome:

```powershell
python -m playwright install chromium
```
