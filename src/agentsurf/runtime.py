from __future__ import annotations

import json
from typing import Any

from .browser import PlaywrightBrowserSession
from .llm import (
    LocalIntentRouter,
    QwenClient,
    QwenConfigError,
    RouteDecision,
    is_device_list_request,
    is_login_continue_request,
    normalize_ezviz_section,
)
from .tools.ezviz import EzvizConsoleTools, ToolResult


HELP_TEXT = """Commands:
  /help        Show this help
  /status      Observe current browser page
  /login-done  Continue after you finish EZVIZ login
  /continue    Same as /login-done
  /exit        Close AgentSurf

Examples:
  打开萤石云控制台
  查看设备列表
  打开云录像页面
  看一下当前页面有什么设备"""


class EzvizAgentRuntime:
    def __init__(
        self,
        *,
        browser: PlaywrightBrowserSession,
        tools: EzvizConsoleTools,
        qwen: QwenClient,
        verbose: bool = False,
    ) -> None:
        self.browser = browser
        self.tools = tools
        self.qwen = qwen
        self.verbose = verbose
        self.local_router = LocalIntentRouter()
        self.history: list[dict[str, str]] = []
        self.last_result: ToolResult | None = None
        self.waiting_for_login = False
        self.logged_in: bool | None = None
        self.pending_tool_call: dict[str, Any] | None = None

    async def handle_message(self, user_input: str) -> str:
        text = user_input.strip()
        if not text:
            return ""
        if text == "/help":
            return HELP_TEXT
        if text == "/status":
            result = await self.tools.observe_page()
            self._record_tool_result(result)
            return self._format_tool_result(result)
        if text in {"/login-done", "/continue"} or is_login_continue_request(text):
            return await self._check_login_and_retry_pending()
        if text == "/exit":
            return "EXIT"

        decision = self._route(text)
        if decision.mode == "chat":
            return self._chat(text)

        result = await self._dispatch_decision(decision, original_request=text)
        return self._format_tool_result(result)

    def _route(self, text: str) -> RouteDecision:
        if is_device_list_request(text):
            return RouteDecision(mode="tool", tool_name="ezviz_open_section", tool_args={"section": "devices"})
        if self.qwen.is_configured:
            try:
                return self._normalize_decision(self.qwen.route(text, context=self._context()))
            except QwenConfigError:
                pass
        return self._normalize_decision(self.local_router.route(text))

    async def _check_login_and_retry_pending(self) -> str:
        result = await self.tools.check_login()
        self._record_tool_result(result)
        if result.requires_user_action or not self.pending_tool_call:
            return self._format_tool_result(result)

        pending = self.pending_tool_call
        decision = RouteDecision(
            mode="tool",
            tool_name=pending.get("tool_name"),
            tool_args=dict(pending.get("tool_args") or {}),
        )
        retry_result = await self._dispatch_decision(decision, original_request="")
        retry_result.message = f"Login verified; retried pending action. {retry_result.message}"
        return self._format_tool_result(retry_result)

    async def _dispatch_decision(self, decision: RouteDecision, original_request: str) -> ToolResult:
        result = await self.tools.dispatch(decision.tool_name or "", decision.tool_args, original_request=original_request)
        self._record_tool_result(result, decision)
        return result

    def _record_tool_result(self, result: ToolResult, decision: RouteDecision | None = None) -> None:
        self.last_result = result
        login_required = result.data.get("login_required")
        logged_in = result.data.get("logged_in")
        if login_required is True:
            self.logged_in = False
            self.waiting_for_login = True
        elif logged_in is True:
            self.logged_in = True
            self.waiting_for_login = False
        elif logged_in is False:
            self.logged_in = False
            self.waiting_for_login = result.requires_user_action
        else:
            self.waiting_for_login = result.requires_user_action

        if decision is None:
            return
        if self._should_retry_after_login(decision, result):
            self.pending_tool_call = {
                "tool_name": decision.tool_name,
                "tool_args": dict(decision.tool_args),
            }
        elif self._matches_pending(decision) and not result.requires_user_action:
            self.pending_tool_call = None

    def _should_retry_after_login(self, decision: RouteDecision, result: ToolResult) -> bool:
        return (
            decision.tool_name == "ezviz_open_section"
            and result.requires_user_action
            and result.data.get("login_required") is True
        )

    def _matches_pending(self, decision: RouteDecision) -> bool:
        if not self.pending_tool_call:
            return False
        return (
            self.pending_tool_call.get("tool_name") == decision.tool_name
            and self.pending_tool_call.get("tool_args") == dict(decision.tool_args)
        )

    def _normalize_decision(self, decision: RouteDecision) -> RouteDecision:
        if decision.tool_name != "ezviz_open_section":
            return decision
        tool_args = dict(decision.tool_args)
        tool_args["section"] = normalize_ezviz_section(tool_args.get("section"))
        return RouteDecision(
            mode=decision.mode,
            tool_name=decision.tool_name,
            tool_args=tool_args,
            reply=decision.reply,
        )

    def _chat(self, text: str) -> str:
        if not self.qwen.is_configured:
            return (
                "Qwen is not configured. Set DASHSCOPE_API_KEY for normal chat; "
                "EZVIZ tool commands still work through local routing."
            )
        try:
            reply = self.qwen.chat(text, context=self._context())
        except QwenConfigError as exc:
            return str(exc)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def _context(self) -> str:
        payload: dict[str, Any] = {
            "waiting_for_login": self.waiting_for_login,
            "logged_in": self.logged_in,
            "pending_tool_call": self.pending_tool_call,
        }
        if self.last_result is not None:
            payload["last_tool_result"] = self.last_result.to_dict()
        return json.dumps(payload, ensure_ascii=False)

    def _format_tool_result(self, result: ToolResult) -> str:
        payload = result.to_dict()
        payload["data"] = dict(payload.get("data") or {})
        payload["data"]["logged_in"] = self.logged_in
        payload["data"]["pending_tool_call"] = self.pending_tool_call
        if not self.verbose:
            payload.get("data", {}).pop("visible_text_excerpt", None)
        return json.dumps(payload, indent=2, ensure_ascii=False)


async def run_ezviz_repl(
    *,
    chrome_path: str | None,
    profile_dir: str,
    console_url: str | None,
    qwen_model: str | None,
    qwen_base_url: str | None,
    headless: bool,
    verbose: bool,
) -> None:
    browser = PlaywrightBrowserSession(
        headless=headless,
        executable_path=chrome_path,
        channel=None if chrome_path else "chrome",
        user_data_dir=profile_dir,
    )
    await browser.start()
    try:
        qwen = QwenClient(model=qwen_model, base_url=qwen_base_url)
        tools = EzvizConsoleTools(browser, console_url=console_url)
        runtime = EzvizAgentRuntime(browser=browser, tools=tools, qwen=qwen, verbose=verbose)
        print(HELP_TEXT)
        while True:
            user_input = input("AgentSurf> ")
            output = await runtime.handle_message(user_input)
            if output == "EXIT":
                break
            if output:
                print(output)
    finally:
        await browser.close()
