from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import BrowserAgent, RuleBasedPlanner
from .browser import BrowserSession, InMemoryBrowserSession, PlaywrightBrowserSession
from .schemas import AgentState
from .tools.desktop_ezviz import DEFAULT_EZVIZ_CLIENT_EXE, DesktopEzvizClientTools, is_ezviz_desktop_request
from .vision import HeuristicVisionAnalyzer


JSONRPC_VERSION = "2.0"
ACP_PROTOCOL_VERSION = 1


@dataclass
class AcpSession:
    session_id: str
    browser: BrowserSession
    agent: BrowserAgent


class AcpAgentServer:
    def __init__(
        self,
        *,
        desktop_chrome: bool = False,
        chrome_path: str | None = None,
        profile_dir: str = ".runtime/acp-profile",
        headless: bool = True,
        max_steps: int = 8,
        ezviz_exe_path: str = DEFAULT_EZVIZ_CLIENT_EXE,
        desktop_tools_factory: Any | None = None,
    ) -> None:
        self.desktop_chrome = desktop_chrome
        self.chrome_path = chrome_path
        self.profile_dir = profile_dir
        self.headless = headless
        self.max_steps = max_steps
        self.ezviz_exe_path = ezviz_exe_path
        self.desktop_tools_factory = desktop_tools_factory
        self.sessions: dict[str, AcpSession] = {}

    async def run_stdio(self) -> None:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            for message in await self.handle_rpc_line(line):
                print(json.dumps(message, ensure_ascii=False), flush=True)
        await self.close_all()

    async def handle_rpc_line(self, line: str) -> list[dict[str, Any]]:
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            return [self._error_response(None, -32700, f"Parse error: {exc}")]
        return await self.handle_rpc(envelope)

    async def handle_rpc(self, envelope: dict[str, Any]) -> list[dict[str, Any]]:
        request_id = envelope.get("id")
        method = envelope.get("method")
        params = envelope.get("params") or {}
        if not method:
            return [self._error_response(request_id, -32600, "Invalid request: missing method")]

        try:
            if method == "initialize":
                return [self._response(request_id, self._initialize_result())]
            if method == "session/new":
                return [self._response(request_id, await self._new_session(params))]
            if method == "session/prompt":
                updates, result = await self._prompt(params)
                return [*updates, self._response(request_id, result)]
            if method == "session/cancel":
                return [self._response(request_id, {"ok": True})]
            if method == "session/close":
                return [self._response(request_id, await self._close_session(params))]
        except Exception as exc:
            return [self._error_response(request_id, -32000, str(exc))]
        return [self._error_response(request_id, -32601, f"Method not found: {method}")]

    async def close_all(self) -> None:
        for session_id in list(self.sessions):
            await self._close_session({"sessionId": session_id})

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "agent": {
                "name": "AgentSurf",
                "version": "0.1.0",
                "description": "Playwright-backed browser agent for AgentSurf tasks.",
            },
            "capabilities": {
                "prompts": True,
                "sessions": True,
                "cancellation": True,
            },
            "authMethods": [],
        }

    async def _new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = str(params.get("sessionId") or params.get("session_id") or uuid.uuid4())
        browser = await self._create_browser(session_id)
        self.sessions[session_id] = AcpSession(
            session_id=session_id,
            browser=browser,
            agent=BrowserAgent(browser, HeuristicVisionAnalyzer(), RuleBasedPlanner()),
        )
        return {"sessionId": session_id}

    async def _prompt(self, params: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        session_id = str(params.get("sessionId") or params.get("session_id") or "")
        if not session_id:
            raise ValueError("session/prompt requires sessionId")
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError(f"Unknown ACP session: {session_id}")

        prompt = self._extract_prompt_text(params)
        if not prompt:
            raise ValueError("session/prompt requires text content")

        if is_ezviz_desktop_request(prompt):
            result = await asyncio.to_thread(self._run_desktop_ezviz_prompt)
            return [self._agent_message_update(session_id, self._summarize_desktop_result(result))], {
                "stopReason": "end_turn"
            }

        state = await session.agent.run(prompt, max_steps=self.max_steps)
        summary = self._summarize_state(state)
        return [self._agent_message_update(session_id, summary)], {"stopReason": "end_turn"}

    async def _close_session(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = str(params.get("sessionId") or params.get("session_id") or "")
        session = self.sessions.pop(session_id, None)
        if session is not None:
            close = getattr(session.browser, "close", None)
            if close is not None:
                await close()
        return {"ok": True}

    async def _create_browser(self, session_id: str) -> BrowserSession:
        if not (self.desktop_chrome or self.chrome_path):
            return InMemoryBrowserSession()

        profile_dir = Path(self.profile_dir)
        if len(self.sessions) > 0:
            profile_dir = profile_dir / session_id
        browser = PlaywrightBrowserSession(
            headless=self.headless,
            executable_path=self.chrome_path,
            channel=None if self.chrome_path else "chrome",
            user_data_dir=str(profile_dir),
        )
        await browser.start()
        return browser

    def _extract_prompt_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(part for part in (self._extract_prompt_text(item) for item in value) if part)
        if not isinstance(value, dict):
            return ""

        for key in ("text", "input", "prompt"):
            if key in value:
                text = self._extract_prompt_text(value[key])
                if text:
                    return text
        for key in ("content", "message", "messages"):
            if key in value:
                text = self._extract_prompt_text(value[key])
                if text:
                    return text
        return ""

    def _summarize_state(self, state: AgentState) -> str:
        observation = state.current_observation
        lines = [
            f"AgentSurf finished: {state.done}",
            f"Task: {state.task}",
        ]
        if observation is not None:
            lines.extend(
                [
                    f"URL: {observation.url}",
                    f"Title: {observation.title}",
                    f"Interactive elements: {len(observation.ui_state.get('elements', []))}",
                ]
            )
        if state.steps:
            actions = ", ".join(step.action.type.value for step in state.steps)
            lines.append(f"Actions: {actions}")
        return "\n".join(lines)

    def _run_desktop_ezviz_prompt(self) -> dict[str, Any]:
        if self.desktop_tools_factory is not None:
            tools = self.desktop_tools_factory()
        else:
            tools = DesktopEzvizClientTools(exe_path=self.ezviz_exe_path)
        return tools.open_video_monitor().to_dict()

    def _summarize_desktop_result(self, result: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"Desktop EZVIZ status: {result.get('status')}",
                f"Message: {result.get('message')}",
                f"Requires user action: {result.get('requires_user_action')}",
                f"Window title: {result.get('window_title')}",
                f"Matched control: {result.get('matched_control')}",
                f"Visible text: {result.get('visible_text_excerpt')}",
            ]
        )

    def _agent_message_update(self, session_id: str, text: str) -> dict[str, Any]:
        return self._notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        )

    def _response(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def _notification(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params}

    def _error_response(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }


async def run_acp_stdio(
    *,
    desktop_chrome: bool,
    chrome_path: str | None,
    profile_dir: str,
    headless: bool,
    max_steps: int,
    ezviz_exe_path: str,
) -> None:
    server = AcpAgentServer(
        desktop_chrome=desktop_chrome,
        chrome_path=chrome_path,
        profile_dir=profile_dir,
        headless=headless,
        max_steps=max_steps,
        ezviz_exe_path=ezviz_exe_path,
    )
    await server.run_stdio()
