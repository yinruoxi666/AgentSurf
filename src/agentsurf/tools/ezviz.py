from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from agentsurf.browser import PlaywrightBrowserSession
from agentsurf.llm import DANGEROUS_ENGLISH_KEYWORDS, DANGEROUS_KEYWORDS, normalize_ezviz_section
from agentsurf.schemas import Observation


DEFAULT_EZVIZ_CONSOLE_URL = "https://open.ys7.com/console/home.html"
DEFAULT_EZVIZ_DEVICE_URL = "https://open.ys7.com/console/device.html"

SECTION_ALIASES = {
    "devices": ["\u8bbe\u5907", "\u8bbe\u5907\u7ba1\u7406", "\u6211\u7684\u6444\u50cf\u673a"],
    "cloud_recording": ["\u4e91\u5f55\u50cf", "\u4e91\u5f55\u5236", "\u4e91\u5b58\u50a8"],
}

LOGIN_URL_HINTS = ["/login", "passport", "returnurl"]

STRONG_LOGIN_TEXT_HINTS = [
    "\u8bf7\u767b\u5f55",
    "\u626b\u7801\u767b\u5f55",
    "\u8d26\u53f7\u767b\u5f55",
    "\u77ed\u4fe1\u767b\u5f55",
    "\u9a8c\u8bc1\u7801\u767b\u5f55",
    "\u767b\u5f55\u5bc6\u7801",
    "\u5fd8\u8bb0\u5bc6\u7801",
]

LOGIN_INPUT_HINTS = [
    "\u5bc6\u7801",
    "\u9a8c\u8bc1\u7801",
    "\u77ed\u4fe1",
    "password",
    "captcha",
    "sms",
]

LOGIN_QR_HINTS = [
    "\u626b\u7801",
    "\u4e8c\u7ef4\u7801",
    "qr",
]


@dataclass
class ToolResult:
    status: str
    message: str
    observation: Observation | None = None
    requires_user_action: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "requires_user_action": self.requires_user_action,
            "url": self.observation.url if self.observation else None,
            "title": self.observation.title if self.observation else None,
            "data": self.data,
        }


class EzvizConsoleTools:
    def __init__(
        self,
        browser: PlaywrightBrowserSession,
        console_url: str | None = None,
    ) -> None:
        self.browser = browser
        self.console_url = console_url or os.getenv("AGENTSURF_EZVIZ_CONSOLE_URL") or DEFAULT_EZVIZ_CONSOLE_URL

    async def dispatch(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        original_request: str = "",
    ) -> ToolResult:
        args = tool_args or {}
        if self._is_dangerous(original_request):
            return ToolResult(
                status="confirmation_required",
                message="This request may change EZVIZ account, device, or paid-service state. V1 only supports navigation and reading.",
                requires_user_action=True,
                data={"original_request": original_request},
            )
        tools = {
            "ezviz_open_console": self.open_console,
            "ezviz_check_login": self.check_login,
            "ezviz_wait_user_login": self.wait_user_login,
            "ezviz_observe_page": self.observe_page,
            "ezviz_open_section": self.open_section,
            "ezviz_search_visible_text": self.search_visible_text,
        }
        if tool_name not in tools:
            return ToolResult(status="error", message=f"Unknown EZVIZ tool: {tool_name}")
        if tool_name == "ezviz_open_section":
            return await self.open_section(section=normalize_ezviz_section(args.get("section", "")))
        if tool_name == "ezviz_search_visible_text":
            return await self.search_visible_text(query=args.get("query", ""))
        if tool_name == "ezviz_observe_page":
            return await self.observe_page(query=args.get("query") or args.get("original_request"))
        return await tools[tool_name]()

    async def open_console(self) -> ToolResult:
        observation = await self.browser.open_url(self.console_url)
        return self._with_login_status(observation, "Opened EZVIZ console.")

    async def check_login(self) -> ToolResult:
        observation = await self.browser.screenshot()
        return self._with_login_status(observation, "Checked current EZVIZ login state.")

    async def wait_user_login(self) -> ToolResult:
        return ToolResult(
            status="requires_user_action",
            message="Please complete EZVIZ login in Chrome, then type /login-done or /continue.",
            requires_user_action=True,
            data={"login_required": True, "logged_in": False},
        )

    async def observe_page(self, query: str | None = None) -> ToolResult:
        observation = await self.browser.screenshot()
        visible_text = observation.ui_state.get("visible_text", "")
        login_required = self._login_required(observation)
        return ToolResult(
            status="ok",
            message="Observed current EZVIZ page.",
            observation=observation,
            data={
                "query": query,
                "visible_text_excerpt": visible_text[:1200],
                "element_count": len(observation.ui_state.get("elements", [])),
                "login_required": login_required,
                "logged_in": self._logged_in(observation),
            },
        )

    async def open_section(self, section: str) -> ToolResult:
        section = normalize_ezviz_section(section)
        if section == "devices":
            observation = await self.browser.open_url(DEFAULT_EZVIZ_DEVICE_URL)
            return self._with_login_status(observation, "Opened EZVIZ device list.")

        observation = await self.browser.screenshot()
        if self._login_required(observation):
            return self._with_login_status(observation, "Login is required before opening an EZVIZ section.")

        labels = SECTION_ALIASES.get(section, [section])
        page = await self.browser._ensure_page()
        for label in labels:
            locator = page.locator("a,button,[role=button],span,div").filter(has_text=label).first
            try:
                if await locator.count():
                    await locator.click(timeout=3000)
                    observation = await self.browser.screenshot()
                    return ToolResult(
                        status="ok",
                        message=f"Opened EZVIZ section: {section}",
                        observation=observation,
                        data={"matched_label": label},
                    )
            except Exception:
                continue
        return ToolResult(
            status="not_found",
            message=f"Could not find visible EZVIZ section: {section}",
            observation=observation,
            data={"tried_labels": labels},
        )

    async def search_visible_text(self, query: str) -> ToolResult:
        observation = await self.browser.screenshot()
        visible_text = observation.ui_state.get("visible_text", "")
        lines = [line.strip() for line in visible_text.splitlines() if query in line]
        return ToolResult(
            status="ok",
            message=f"Found {len(lines)} visible text match(es).",
            observation=observation,
            data={"query": query, "matches": lines[:20]},
        )

    def _with_login_status(self, observation: Observation, message: str) -> ToolResult:
        login_required = self._login_required(observation)
        logged_in = self._logged_in(observation)
        if login_required:
            return ToolResult(
                status="requires_user_action",
                message=f"{message} Please complete login in Chrome, then type /login-done or /continue.",
                observation=observation,
                requires_user_action=True,
                data={"login_required": True, "logged_in": False},
            )
        return ToolResult(
            status="ok",
            message=message,
            observation=observation,
            data={"login_required": False, "logged_in": logged_in},
        )

    def _login_required(self, observation: Observation) -> bool:
        url = (observation.url or "").lower()
        return any(hint in url for hint in LOGIN_URL_HINTS) or self._has_login_form(observation)

    def _logged_in(self, observation: Observation) -> bool:
        if self._login_required(observation):
            return False
        url = (observation.url or "").lower()
        return "open.ys7.com" in url and "/console/" in url

    def _has_login_form(self, observation: Observation) -> bool:
        visible_text = observation.ui_state.get("visible_text", "")
        if any(hint in visible_text for hint in STRONG_LOGIN_TEXT_HINTS):
            return True
        elements = observation.ui_state.get("elements", [])
        for element in elements:
            element_type = str(element.get("type", "")).lower()
            if element_type == "password":
                return True
            role = str(element.get("role", "")).lower()
            fields = [
                element.get("selector", ""),
                element.get("label", ""),
                element.get("text", ""),
                element.get("placeholder", ""),
                element_type,
            ]
            blob = "\n".join(str(field) for field in fields)
            lowered = blob.lower()
            if role in {"input", "textarea"} and (
                any(hint in blob for hint in LOGIN_INPUT_HINTS[:3])
                or any(hint in lowered for hint in LOGIN_INPUT_HINTS[3:])
            ):
                return True
            if any(hint in blob for hint in LOGIN_QR_HINTS[:2]) or any(
                hint in lowered for hint in LOGIN_QR_HINTS[2:]
            ):
                return True
        return False

    def _is_dangerous(self, request: str) -> bool:
        lowered = request.lower()
        return any(keyword in request for keyword in DANGEROUS_KEYWORDS) or any(
            keyword in lowered for keyword in DANGEROUS_ENGLISH_KEYWORDS
        )
