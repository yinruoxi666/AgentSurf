# AgentSurf

AgentSurf is a minimal Browser Agent v3 implementation based on the requirement
documents in `需求/`. It models the requested architecture:

- LangGraph orchestration for plan -> act -> observe -> replan workflows.
- Playwright-backed browser tools exposed through a FastAPI service.
- Screenshot and DOM observation with a pluggable analyzer interface.
- Visible desktop Chrome automation for human handoff workflows.
- A conversational EZVIZ console agent routed through Qwen and safe tool calls.

## Project Layout

```text
src/agentsurf/
  acp.py            ACP stdio agent adapter for OpenClaw integration
  agent.py          Planner and browser-agent control loop
  browser.py        Browser tool interface, in-memory session, Playwright session
  cli.py            Command-line interface
  graph.py          Optional LangGraph workflow builder
  llm.py            Qwen/OpenAI-compatible routing client and local fallback router
  runtime.py        Interactive REPL runtime for the EZVIZ console agent
  schemas.py        Shared request, response, action, and observation models
  server.py         FastAPI browser tool service
  tools/desktop_ezviz.py
                    Windows desktop tool layer for ESEzvizClient
  tools/ezviz.py    Safe EZVIZ web-console tool layer
  vision.py         Screenshot vision analyzer interface and default analyzer
tests/
  test_agent.py
  test_ezviz.py
```

## Setup

This workspace includes a local Conda prefix at `.conda/agentsurf` after setup.
Activate it with:

```powershell
conda activate C:\Users\yinruoxi\Documents\Codex\AgentSurf\.conda\agentsurf
```

Core tests only need `pydantic`:

```powershell
python -m pip install -e .
python -m unittest discover -s tests
```

To run the browser tool server with Playwright:

```powershell
python -m pip install -e ".[server]"
agentsurf serve --host 127.0.0.1 --port 8000
```

To enable Qwen routing through Alibaba Cloud Model Studio:

```powershell
python -m pip install -e ".[server,qwen,desktop]"
$env:DASHSCOPE_API_KEY="your-dashscope-api-key"
$env:QWEN_MODEL="qwen-plus"
$env:QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

`QWEN_MODEL` and `QWEN_BASE_URL` are optional. AgentSurf defaults to
`qwen-plus` and DashScope's OpenAI-compatible endpoint. If your Model Studio
workspace requires a regional WorkspaceId endpoint, set `QWEN_BASE_URL` to that
full `/compatible-mode/v1` URL.

## Visible Desktop Chrome

If local Chrome is already installed, AgentSurf can control it directly without
downloading Playwright's bundled Chromium:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe open-url https://www.baidu.com --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

To open a visible desktop Chrome window and keep it open for visual handoff:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe desktop-open https://www.baidu.com --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --hold
```

This uses `.runtime/chrome-profile` as an automation-only Chrome profile, so it
does not read or modify your default Chrome profile.

To type a natural-language task and let AgentSurf resolve the target site:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe desktop-agent --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --hold
Task> 帮我打开哔哩哔哩
```

You can also pass the task directly:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe desktop-agent "帮我打开哔哩哔哩" --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --hold
```

The default natural-language desktop command uses
`.runtime/chrome-agent-profile`.

For non-visible verification in locked-down environments:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe open-url https://www.baidu.com --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless
```

To expose the same visible Chrome session through the FastAPI server:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe serve --desktop-chrome --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

## OpenClaw ACP Agent

AgentSurf can also run as an ACP stdio agent so OpenClaw can launch it as an
external agent/harness:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe acp --desktop-chrome --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

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

The ACP adapter supports `initialize`, `session/new`, `session/prompt`,
`session/cancel`, and `session/close`. Prompt text is executed by the AgentSurf
browser agent and returned through `session/update` text chunks. Add `--headless`
for non-visible smoke tests, or keep it omitted to let OpenClaw drive a visible
Chrome profile at `.runtime/acp-profile`.

## ESEzvizClient Desktop Agent

Run this command to open ESEzvizClient and enter video monitor:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe ezviz-desktop --open-video-monitor --exe-path "C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe"
```

Open a video monitor sub-page directly:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe ezviz-desktop --section playback --exe-path "C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe"
```

Supported sections are `preview`, `playback`, `messages`, and
`terminal_config`. Natural-language ACP prompts such as `打开回放`,
`看告警消息`, and `进入终端配置` route to the same desktop tools.

Run the Qwen tool-calling desktop agent for natural conversation:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe ezviz-desktop-agent --exe-path "C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe"
```

Set `DASHSCOPE_API_KEY` to let Qwen choose one of the desktop function calls
and generate the final natural-language reply. If Qwen is not configured, the
agent falls back to local routing for the same navigation tools.

If the client shows login, captcha, terminal binding, or another blocking prompt,
finish that step manually in the desktop app, then run the command again. V1 only
opens the app and navigates video monitor pages; it does not add/delete devices,
change settings, or submit forms.

If the client is running with higher Windows privileges or does not expose Qt
controls to UI Automation, the command returns `requires_user_action` and asks
you to click `视频监控` manually, or rerun AgentSurf/Codex as Administrator.

## EZVIZ Console Agent

Run the conversational EZVIZ web-console agent:

```powershell
.\.conda\agentsurf\Scripts\agentsurf.exe ezviz-agent --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

Useful options:

- `--profile-dir .runtime\ezviz-console-profile` keeps an independent Chrome
  automation profile and preserves login state between runs.
- `--console-url https://open.ys7.com/console/home.html` overrides the default
  EZVIZ console URL. `AGENTSURF_EZVIZ_CONSOLE_URL` can also be used.
- `--qwen-model qwen-plus` and `--qwen-base-url ...` override Qwen settings.
- `--headless` is useful for smoke tests; omit it for real desktop handoff.
- `--verbose` keeps longer page observations in tool output.

REPL commands:

- `/help` shows examples and current tool capabilities.
- `/status` reports current URL, title, login state, and page summary.
- `/login-done` or `/continue` tells the agent to re-check the page after you
  finish QR, SMS, captcha, or account login manually.
- `/exit` stops the agent. The Chrome profile directory is retained.

Natural-language examples:

Recommended prompts:

```text
打开萤石云控制台
我登录好了，继续
查看设备列表
看看设备列表
看一下当前页面有什么设备
这个页面是登录状态吗
```

```text
打开萤石云控制台
我登录好了，继续
查看设备列表
打开云录制页面
看一下当前页面有什么设备
这个页面是登录状态吗
```

Device-list requests open `https://open.ys7.com/console/device.html` directly.
If the browser is redirected to login, the agent saves that device-list action
and retries it after `/login-done` or `/continue`.

Safety boundary for v1:

- The agent only navigates and reads page state.
- Requests that include dangerous actions such as delete, buy, renew, transfer,
  save, submit, unbind, password change, enable, or disable return
  `confirmation_required`.
- The agent never reads, stores, or auto-fills passwords, SMS codes, captchas, or
  QR-login secrets. Login is always a human handoff.

## Usage

Run a local deterministic agent loop:

```powershell
agentsurf run "open https://example.com and observe it"
```

Start the FastAPI browser tool server:

```powershell
agentsurf serve
```

The server exposes:

- `POST /open_url` with `{ "url": "https://example.com" }`
- `POST /click` with `{ "selector": "#submit" }`
- `POST /type` with `{ "selector": "#email", "text": "name@example.com" }`
- `POST /screenshot`
- `GET /health`

## Requirement Mapping

- `open_url(url)`, `click(selector)`, `type(selector, text)`, and `screenshot()`
  are implemented in `agentsurf.browser` and exposed by `agentsurf.server`.
- The agent loop observes screenshots and page state, runs analysis, plans the
  next browser action, executes it, and repeats until complete.
- `agentsurf.graph.build_langgraph_workflow` provides the optional LangGraph
  version of the same loop when `langgraph` is installed.
- `agentsurf.vision.VisionAnalyzer` is provider-neutral, so GPT-4o, Qwen-VL, or
  another multimodal model can be plugged in without changing browser tooling.
- `agentsurf.runtime.EzvizAgentRuntime` and `agentsurf.tools.ezviz` implement
  the safe EZVIZ console workflow described in the requirement plan.
