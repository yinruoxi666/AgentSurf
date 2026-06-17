from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field


DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"


class QwenConfigError(RuntimeError):
    pass


class RouteDecision(BaseModel):
    mode: str = Field(pattern="^(chat|tool)$")
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    reply: str = ""


DEVICE_SECTION_ALIASES = {
    "device": "devices",
    "devices": "devices",
    "device_list": "devices",
    "camera": "devices",
    "camera_list": "devices",
    "\u8bbe\u5907": "devices",
    "\u8bbe\u5907\u5217\u8868": "devices",
    "\u6444\u50cf\u673a": "devices",
}

DEVICE_INTENT_KEYWORDS = [
    "\u8bbe\u5907\u5217\u8868",
    "\u67e5\u770b\u8bbe\u5907",
    "\u770b\u770b\u8bbe\u5907",
    "\u5f53\u524d\u9875\u9762\u6709\u4ec0\u4e48\u8bbe\u5907",
    "\u6709\u4ec0\u4e48\u8bbe\u5907",
    "\u8bbe\u5907",
    "\u6444\u50cf\u673a",
]

DEVICE_INTENT_ENGLISH_KEYWORDS = ["device", "devices", "camera", "cameras"]


def normalize_ezviz_section(section: Any) -> str:
    normalized = str(section or "").strip().lower().replace("-", "_").replace(" ", "_")
    return DEVICE_SECTION_ALIASES.get(normalized, normalized)


def is_device_list_request(user_input: str) -> bool:
    lowered = user_input.lower()
    if any(keyword in user_input for keyword in DANGEROUS_KEYWORDS) or any(
        keyword in lowered for keyword in DANGEROUS_ENGLISH_KEYWORDS
    ):
        return False
    return any(keyword in user_input for keyword in DEVICE_INTENT_KEYWORDS) or any(
        keyword in lowered for keyword in DEVICE_INTENT_ENGLISH_KEYWORDS
    )


def is_login_continue_request(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(
        keyword in user_input
        for keyword in [
            "\u6211\u767b\u5f55\u597d\u4e86",
            "\u767b\u5f55\u597d\u4e86",
            "\u5df2\u767b\u5f55",
            "\u7ee7\u7eed",
            "login-done",
        ]
    ) or any(keyword in lowered for keyword in ["login done", "continue"])


class QwenClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url or os.getenv("QWEN_BASE_URL") or DEFAULT_QWEN_BASE_URL
        self.model = model or os.getenv("QWEN_MODEL") or DEFAULT_QWEN_MODEL
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or self._client)

    def route(self, user_input: str, context: str = "") -> RouteDecision:
        response = self._completion(
            [
                {"role": "system", "content": self._routing_prompt()},
                {"role": "user", "content": f"Context:\n{context}\n\nUser:\n{user_input}"},
            ]
        )
        return self._parse_route(response)

    def chat(self, user_input: str, context: str = "") -> str:
        return self._completion(
            [
                {
                    "role": "system",
                    "content": "You are AgentSurf, a concise Chinese assistant. Answer normally unless a tool is needed.",
                },
                {"role": "user", "content": f"Context:\n{context}\n\nUser:\n{user_input}"},
            ]
        )

    def _completion(self, messages: list[dict[str, str]]) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        return response.choices[0].message.content or ""

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise QwenConfigError(
                "DASHSCOPE_API_KEY is required for Qwen. Set DASHSCOPE_API_KEY or pass a mock client."
            )
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise QwenConfigError("Install OpenAI SDK with `python -m pip install openai`.") from exc
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _parse_route(self, content: str) -> RouteDecision:
        try:
            payload = json.loads(content)
            return RouteDecision(**payload)
        except Exception as exc:
            raise QwenConfigError(f"Qwen routing response was not valid JSON: {content}") from exc

    def _routing_prompt(self) -> str:
        return (
            "Return only JSON with keys mode, tool_name, tool_args, reply. "
            "mode is chat or tool. Use tool only for EZVIZ console tasks. "
            "Allowed tools: ezviz_open_console, ezviz_check_login, ezviz_wait_user_login, "
            "ezviz_observe_page, ezviz_open_section, ezviz_search_visible_text. "
            "For device list or camera list requests, use ezviz_open_section with "
            'tool_args {"section":"devices"}. '
            "For normal conversation use mode=chat. For dangerous modification requests, "
            "choose tool ezviz_observe_page and put original_request in tool_args."
        )


class LocalIntentRouter:
    def route(self, user_input: str) -> RouteDecision:
        lowered = user_input.lower()
        if any(keyword in user_input for keyword in DANGEROUS_KEYWORDS) or any(
            keyword in lowered for keyword in DANGEROUS_ENGLISH_KEYWORDS
        ):
            return RouteDecision(mode="tool", tool_name="ezviz_observe_page", tool_args={"query": user_input})
        if is_login_continue_request(user_input):
            return RouteDecision(mode="tool", tool_name="ezviz_check_login")
        if is_device_list_request(user_input):
            return RouteDecision(mode="tool", tool_name="ezviz_open_section", tool_args={"section": "devices"})
        if any(keyword in user_input for keyword in ["\u4e91\u5f55\u50cf", "\u4e91\u5f55\u5236", "\u4e91\u5b58\u50a8"]) or any(
            keyword in lowered for keyword in ["cloud recording", "cloud storage", "cloud video"]
        ):
            return RouteDecision(mode="tool", tool_name="ezviz_open_section", tool_args={"section": "cloud_recording"})
        if any(keyword in user_input for keyword in ["\u8424\u77f3", "\u63a7\u5236\u53f0", "\u5f00\u653e\u5e73\u53f0"]) or any(
            keyword in lowered for keyword in ["ezviz", "ys7", "console"]
        ):
            return RouteDecision(mode="tool", tool_name="ezviz_open_console")
        if any(keyword in user_input for keyword in ["\u9875\u9762", "\u72b6\u6001", "\u6709\u4ec0\u4e48", "\u67e5\u770b\u8bbe\u5907"]) or any(
            keyword in lowered for keyword in ["page", "status", "observe"]
        ):
            return RouteDecision(mode="tool", tool_name="ezviz_observe_page")
        return RouteDecision(mode="chat", reply="")


DANGEROUS_KEYWORDS = [
    "\u5220\u9664",
    "\u8d2d\u4e70",
    "\u7eed\u8d39",
    "\u8f6c\u79fb",
    "\u4fdd\u5b58",
    "\u63d0\u4ea4",
    "\u89e3\u7ed1",
    "\u4fee\u6539\u5bc6\u7801",
    "\u5f00\u901a",
    "\u5173\u95ed\u63d0\u9192",
]

DANGEROUS_ENGLISH_KEYWORDS = [
    "delete",
    "buy",
    "purchase",
    "renew",
    "transfer",
    "save",
    "submit",
    "unbind",
    "change password",
    "enable service",
    "disable reminder",
]
