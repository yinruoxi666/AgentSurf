from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from .acp import run_acp_stdio
from .agent import BrowserAgent, RuleBasedPlanner
from .browser import InMemoryBrowserSession, PlaywrightBrowserSession
from .debug_logging import DebugLogger
from .desktop_runtime import run_desktop_ezviz_repl
from .runtime import run_ezviz_repl
from .tools.desktop_ezviz import DEFAULT_EZVIZ_CLIENT_EXE, DesktopEzvizClientTools
from .vision import HeuristicVisionAnalyzer


async def run_task(task: str, max_steps: int) -> None:
    browser = InMemoryBrowserSession()
    agent = BrowserAgent(browser, HeuristicVisionAnalyzer(), RuleBasedPlanner())
    state = await agent.run(task, max_steps=max_steps)
    print(json.dumps(state.model_dump(mode="json"), indent=2))


async def open_url(url: str, chrome_path: str | None, headless: bool, verbose: bool) -> None:
    browser = PlaywrightBrowserSession(
        headless=headless,
        executable_path=chrome_path,
        channel=None if chrome_path else "chrome",
    )
    await browser.start()
    try:
        observation = await browser.open_url(url)
        payload = observation.model_dump(mode="json") if verbose else {
            "url": observation.url,
            "title": observation.title,
            "element_count": len(observation.ui_state.get("elements", [])),
        }
        print(json.dumps(payload, indent=2))
    finally:
        await browser.close()


async def desktop_open(
    url: str,
    chrome_path: str | None,
    profile_dir: str,
    hold: bool,
    verbose: bool,
) -> None:
    browser = PlaywrightBrowserSession(
        headless=False,
        executable_path=chrome_path,
        channel=None if chrome_path else "chrome",
        user_data_dir=profile_dir,
    )
    await browser.start()
    try:
        observation = await browser.open_url(url)
        payload = observation.model_dump(mode="json") if verbose else {
            "url": observation.url,
            "title": observation.title,
            "element_count": len(observation.ui_state.get("elements", [])),
            "profile_dir": str(Path(profile_dir).resolve()),
        }
        print(json.dumps(payload, indent=2))
        if hold:
            print("Desktop Chrome is open. Press Ctrl+C in this terminal to close automation.")
            await asyncio.Event().wait()
    finally:
        await browser.close()


async def desktop_agent(
    task: str | None,
    chrome_path: str | None,
    profile_dir: str,
    hold: bool,
    headless: bool,
    max_steps: int,
    verbose: bool,
) -> None:
    user_task = task or input("Task> ").strip()
    if not user_task:
        raise ValueError("Task cannot be empty")

    browser = PlaywrightBrowserSession(
        headless=headless,
        executable_path=chrome_path,
        channel=None if chrome_path else "chrome",
        user_data_dir=profile_dir,
    )
    await browser.start()
    try:
        agent = BrowserAgent(browser, HeuristicVisionAnalyzer(), RuleBasedPlanner())
        state = await agent.run(user_task, max_steps=max_steps)
        observation = state.current_observation
        payload = state.model_dump(mode="json") if verbose else {
            "task": user_task,
            "done": state.done,
            "url": observation.url if observation else None,
            "title": observation.title if observation else None,
            "actions": [step.action.model_dump(mode="json") for step in state.steps],
            "profile_dir": str(Path(profile_dir).resolve()),
        }
        print(json.dumps(payload, indent=2))
        if hold:
            print("Desktop Chrome is open. Press Ctrl+C in this terminal to close automation.")
            await asyncio.Event().wait()
    finally:
        await browser.close()


def create_debug_logger(debug: bool, debug_log_path: str | None) -> DebugLogger | None:
    if not debug:
        return None
    logger = DebugLogger(path=debug_log_path)
    logger.log("debug.enabled", {"log_path": str(logger.path)})
    return logger


async def ezviz_desktop(
    exe_path: str,
    open_video_monitor: bool,
    observe: bool,
    section: str | None,
    debug_logger: DebugLogger | None = None,
) -> None:
    if debug_logger is not None:
        debug_logger.log(
            "ezviz_desktop.start",
            {
                "exe_path": exe_path,
                "open_video_monitor": open_video_monitor,
                "observe": observe,
                "section": section,
            },
        )
    tools = DesktopEzvizClientTools(exe_path=exe_path, debug_logger=debug_logger)
    if section:
        if debug_logger is not None:
            debug_logger.log("ezviz_desktop.dispatch", {"tool": "open_video_monitor_section", "section": section})
        result = await asyncio.to_thread(tools.open_video_monitor_section, section)
    elif open_video_monitor:
        if debug_logger is not None:
            debug_logger.log("ezviz_desktop.dispatch", {"tool": "open_video_monitor"})
        result = await asyncio.to_thread(tools.open_video_monitor)
    elif observe:
        if debug_logger is not None:
            debug_logger.log("ezviz_desktop.dispatch", {"tool": "observe_window"})
        result = await asyncio.to_thread(tools.observe_window)
    else:
        if debug_logger is not None:
            debug_logger.log("ezviz_desktop.dispatch", {"tool": "open_client"})
        result = await asyncio.to_thread(tools.open_client)
    if debug_logger is not None:
        debug_logger.log("ezviz_desktop.result", result.to_dict())
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def serve(
    host: str,
    port: int,
    desktop_chrome: bool,
    chrome_path: str | None,
    profile_dir: str,
) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise RuntimeError("Uvicorn is not installed. Install with `python -m pip install -e .[server]`.") from exc

    if desktop_chrome:
        os.environ["AGENTSURF_BROWSER_HEADLESS"] = "false"
        os.environ["AGENTSURF_CHROME_PROFILE_DIR"] = profile_dir
        if chrome_path:
            os.environ["AGENTSURF_CHROME_EXECUTABLE"] = chrome_path
        else:
            os.environ["AGENTSURF_BROWSER_CHANNEL"] = "chrome"

    uvicorn.run("agentsurf.server:create_app", factory=True, host=host, port=port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentSurf Browser Agent v3")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a deterministic local agent loop")
    run_parser.add_argument("task")
    run_parser.add_argument("--max-steps", type=int, default=8)

    serve_parser = subparsers.add_parser("serve", help="Start the browser tool server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--desktop-chrome", action="store_true")
    serve_parser.add_argument("--chrome-path")
    serve_parser.add_argument("--profile-dir", default=".runtime/chrome-profile")

    open_parser = subparsers.add_parser("open-url", help="Open a URL with Playwright-controlled Chrome")
    open_parser.add_argument("url")
    open_parser.add_argument("--chrome-path")
    open_parser.add_argument("--headless", action="store_true")
    open_parser.add_argument("--verbose", action="store_true")

    desktop_parser = subparsers.add_parser("desktop-open", help="Open a URL in visible desktop Chrome")
    desktop_parser.add_argument("url")
    desktop_parser.add_argument("--chrome-path")
    desktop_parser.add_argument("--profile-dir", default=".runtime/chrome-profile")
    desktop_parser.add_argument("--hold", action="store_true")
    desktop_parser.add_argument("--verbose", action="store_true")

    desktop_agent_parser = subparsers.add_parser(
        "desktop-agent",
        help="Run a natural-language task in visible desktop Chrome",
    )
    desktop_agent_parser.add_argument("task", nargs="?")
    desktop_agent_parser.add_argument("--chrome-path")
    desktop_agent_parser.add_argument("--profile-dir", default=".runtime/chrome-agent-profile")
    desktop_agent_parser.add_argument("--hold", action="store_true")
    desktop_agent_parser.add_argument("--headless", action="store_true")
    desktop_agent_parser.add_argument("--max-steps", type=int, default=8)
    desktop_agent_parser.add_argument("--verbose", action="store_true")

    ezviz_parser = subparsers.add_parser(
        "ezviz-agent",
        help="Run a Qwen-routed conversational agent for the EZVIZ web console",
    )
    ezviz_parser.add_argument("--chrome-path")
    ezviz_parser.add_argument("--profile-dir", default=".runtime/ezviz-console-profile")
    ezviz_parser.add_argument("--console-url")
    ezviz_parser.add_argument("--qwen-model")
    ezviz_parser.add_argument("--qwen-base-url")
    ezviz_parser.add_argument("--headless", action="store_true")
    ezviz_parser.add_argument("--verbose", action="store_true")

    acp_parser = subparsers.add_parser("acp", help="Run an ACP stdio agent for OpenClaw integration")
    acp_parser.add_argument("--desktop-chrome", action="store_true")
    acp_parser.add_argument("--chrome-path")
    acp_parser.add_argument("--profile-dir", default=".runtime/acp-profile")
    acp_parser.add_argument("--headless", action="store_true")
    acp_parser.add_argument("--max-steps", type=int, default=8)
    acp_parser.add_argument("--ezviz-exe-path", default=DEFAULT_EZVIZ_CLIENT_EXE)
    acp_parser.add_argument("--qwen-model")
    acp_parser.add_argument("--qwen-base-url")

    ezviz_desktop_parser = subparsers.add_parser(
        "ezviz-desktop",
        help="Open ESEzvizClient and optionally enter video monitor",
    )
    ezviz_desktop_parser.add_argument("--exe-path", default=DEFAULT_EZVIZ_CLIENT_EXE)
    ezviz_desktop_parser.add_argument("--open-video-monitor", action="store_true")
    ezviz_desktop_parser.add_argument("--section", choices=["preview", "playback", "messages", "terminal_config"])
    ezviz_desktop_parser.add_argument("--observe", action="store_true")
    ezviz_desktop_parser.add_argument("--debug", action="store_true")
    ezviz_desktop_parser.add_argument("--debug-log-path")

    ezviz_desktop_agent_parser = subparsers.add_parser(
        "ezviz-desktop-agent",
        help="Run a Qwen tool-calling conversational agent for ESEzvizClient",
    )
    ezviz_desktop_agent_parser.add_argument("--exe-path", default=DEFAULT_EZVIZ_CLIENT_EXE)
    ezviz_desktop_agent_parser.add_argument("--qwen-model")
    ezviz_desktop_agent_parser.add_argument("--qwen-base-url")
    ezviz_desktop_agent_parser.add_argument("--verbose", action="store_true")
    ezviz_desktop_agent_parser.add_argument("--debug", action="store_true")
    ezviz_desktop_agent_parser.add_argument("--debug-log-path")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        asyncio.run(run_task(args.task, args.max_steps))
    elif args.command == "serve":
        serve(args.host, args.port, args.desktop_chrome, args.chrome_path, args.profile_dir)
    elif args.command == "open-url":
        asyncio.run(open_url(args.url, args.chrome_path, args.headless, args.verbose))
    elif args.command == "desktop-open":
        asyncio.run(desktop_open(args.url, args.chrome_path, args.profile_dir, args.hold, args.verbose))
    elif args.command == "desktop-agent":
        asyncio.run(
            desktop_agent(
                args.task,
                args.chrome_path,
                args.profile_dir,
                args.hold,
                args.headless,
                args.max_steps,
                args.verbose,
            )
        )
    elif args.command == "ezviz-agent":
        asyncio.run(
            run_ezviz_repl(
                chrome_path=args.chrome_path,
                profile_dir=args.profile_dir,
                console_url=args.console_url,
                qwen_model=args.qwen_model,
                qwen_base_url=args.qwen_base_url,
                headless=args.headless,
                verbose=args.verbose,
            )
        )
    elif args.command == "acp":
        asyncio.run(
            run_acp_stdio(
                desktop_chrome=args.desktop_chrome,
                chrome_path=args.chrome_path,
                profile_dir=args.profile_dir,
                headless=args.headless or not args.desktop_chrome,
                max_steps=args.max_steps,
                ezviz_exe_path=args.ezviz_exe_path,
                qwen_model=args.qwen_model,
                qwen_base_url=args.qwen_base_url,
            )
        )
    elif args.command == "ezviz-desktop":
        debug_logger = create_debug_logger(args.debug, args.debug_log_path)
        asyncio.run(ezviz_desktop(args.exe_path, args.open_video_monitor, args.observe, args.section, debug_logger))
    elif args.command == "ezviz-desktop-agent":
        debug_logger = create_debug_logger(args.debug, args.debug_log_path)
        run_desktop_ezviz_repl(
            exe_path=args.exe_path,
            qwen_model=args.qwen_model,
            qwen_base_url=args.qwen_base_url,
            verbose=args.verbose,
            debug_logger=debug_logger,
        )


if __name__ == "__main__":
    main()
