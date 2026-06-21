from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .debug_logging import DebugLogger
from .llm import QwenClient, QwenConfigError
from .tools.desktop_ezviz import (
    DesktopEzvizClientTools,
    DesktopToolResult,
    detect_ezviz_desktop_tool,
)


DESKTOP_EZVIZ_FUNCTION_TO_SECTION = {
    "open_video_preview": "preview",
    "open_video_playback": "playback",
    "open_video_messages": "messages",
    "open_terminal_config": "terminal_config",
}

DESKTOP_EZVIZ_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_video_monitor",
            "description": "打开萤石工作室 ESEzvizClient 的视频监控页面。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_video_preview",
            "description": "打开视频监控下的预览页面，用于实时预览、看直播、看当前摄像头画面。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_video_playback",
            "description": "打开视频监控下的回放页面，用于录像回放、历史视频、看录像。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_video_messages",
            "description": "打开视频监控下的消息页面，用于告警消息、报警、通知查看。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_terminal_config",
            "description": "打开视频监控下的终端配置页面，用于设备配置、摄像头配置、配置终端。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]


DESKTOP_EZVIZ_HELP = """Commands:
  /help     Show this help
  /status   Observe ESEzvizClient window
  /exit     Close this desktop agent

Examples:
  打开萤石工作室，进入视频监控
  打开预览
  打开回放
  看告警消息
  进入终端配置
"""


@dataclass
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]


class DesktopEzvizAgentRuntime:
    def __init__(
        self,
        *,
        tools: DesktopEzvizClientTools,
        qwen: QwenClient,
        verbose: bool = False,
        debug_logger: DebugLogger | None = None,
    ) -> None:
        self.tools = tools
        self.qwen = qwen
        self.verbose = verbose
        self.debug_logger = debug_logger
        self.history: list[dict[str, str]] = []
        self.last_tool_result: dict[str, Any] | None = None

    def handle_message(self, user_input: str) -> str:
        text = user_input.strip()
        if not text:
            return ""
        self._debug("desktop_agent.input", {"text": text})
        if text == "/help":
            self._debug("desktop_agent.command", {"command": "/help"})
            return DESKTOP_EZVIZ_HELP
        if text == "/status":
            self._debug("desktop_agent.command", {"command": "/status"})
            result = self.tools.observe_window()
            return self._finalize_tool_result(text, "observe_window", result, fallback_note="")
        if text == "/exit":
            self._debug("desktop_agent.command", {"command": "/exit"})
            return "EXIT"

        if self._is_qwen_configured():
            try:
                self._debug(
                    "desktop_agent.qwen.request",
                    {"is_configured": True, "tool_count": len(DESKTOP_EZVIZ_TOOL_SCHEMAS)},
                )
                message = self.qwen.chat_with_tools(
                    self._tool_selection_messages(text),
                    DESKTOP_EZVIZ_TOOL_SCHEMAS,
                    tool_choice="auto",
                )
                tool_call = self._first_tool_call(message)
                if tool_call is not None:
                    self._debug(
                        "desktop_agent.qwen.tool_call",
                        {"name": tool_call.name, "arguments": tool_call.arguments},
                    )
                    result = self._dispatch_function(tool_call.name)
                    return self._finalize_tool_result(text, tool_call.name, result, fallback_note="")

                content = self._message_content(message)
                if content:
                    self._debug("desktop_agent.qwen.chat_reply", {"content": content})
                    self._record_chat(text, content)
                    return content
            except (QwenConfigError, ValueError) as exc:
                self._debug(
                    "desktop_agent.qwen.error",
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
                fallback = self._fallback_tool_call(text)
                self._debug("desktop_agent.local_route", {"tool_call": fallback, "reason": "qwen_error"})
                if fallback is None:
                    return self._qwen_unavailable_reply(text, str(exc), prefix="千问调用失败")
                result = self._dispatch_local_tool_call(fallback)
                return self._fallback_reply(
                    result,
                    fallback_note=f"千问工具调用失败，已使用本地兜底路由。原因：{exc}",
                )

        fallback = self._fallback_tool_call(text)
        self._debug(
            "desktop_agent.local_route",
            {"tool_call": fallback, "reason": "qwen_not_configured" if not self._is_qwen_configured() else "no_qwen_tool"},
        )
        if fallback is not None:
            result = self._dispatch_local_tool_call(fallback)
            note = (
                self._local_fallback_note(self._qwen_config_error_message())
                if not self._is_qwen_configured()
                else ""
            )
            return self._fallback_reply(result, fallback_note=note)

        if not self._is_qwen_configured():
            self._debug("desktop_agent.qwen.unavailable", {"reason": self._qwen_config_error_message()})
            return self._qwen_unavailable_reply(text, self._qwen_config_error_message(), prefix="千问未配置")
        return "我暂时没有识别到需要调用萤石客户端工具的意图。"

    def _tool_selection_messages(self, user_input: str) -> list[dict[str, str]]:
        context = json.dumps(
            {
                "last_tool_result": self.last_tool_result,
                "available_pages": ["视频监控", "预览", "回放", "消息", "终端配置"],
                "safety": "只允许打开页面和读取状态，不执行新增、删除、保存、提交等修改操作。",
            },
            ensure_ascii=False,
        )
        return [
            {
                "role": "system",
                "content": (
                    "你是 AgentSurf 桌面智能体，负责理解中文自然语言并在需要时调用 ESEzvizClient 工具。"
                    "用户要打开萤石工作室、视频监控、预览、回放、消息、终端配置时必须调用工具。"
                    "普通聊天不要调用工具，直接自然回复。"
                ),
            },
            {"role": "user", "content": f"Context:\n{context}\n\nUser:\n{user_input}"},
        ]

    def _dispatch_function(self, function_name: str) -> DesktopToolResult:
        if function_name == "open_video_monitor":
            self._debug("desktop_agent.tool_dispatch", {"tool": "open_video_monitor", "source": "qwen"})
            return self.tools.open_video_monitor()
        section = DESKTOP_EZVIZ_FUNCTION_TO_SECTION.get(function_name)
        if section is None:
            self._debug("desktop_agent.tool_dispatch_error", {"function_name": function_name})
            raise ValueError(f"Unsupported desktop EZVIZ function call: {function_name}")
        self._debug(
            "desktop_agent.tool_dispatch",
            {"tool": "open_video_monitor_section", "section": section, "source": "qwen", "function_name": function_name},
        )
        return self.tools.open_video_monitor_section(section)

    def _dispatch_local_tool_call(self, tool_call: dict[str, Any]) -> DesktopToolResult:
        if tool_call.get("tool_name") == "open_video_monitor_section":
            section = str(tool_call.get("section") or "")
            self._debug(
                "desktop_agent.tool_dispatch",
                {"tool": "open_video_monitor_section", "section": section, "source": "local"},
            )
            return self.tools.open_video_monitor_section(section)
        self._debug("desktop_agent.tool_dispatch", {"tool": "open_video_monitor", "source": "local"})
        return self.tools.open_video_monitor()

    def _finalize_tool_result(
        self,
        user_input: str,
        tool_name: str,
        result: DesktopToolResult,
        *,
        fallback_note: str,
    ) -> str:
        payload = result.to_dict()
        self.last_tool_result = payload
        self._debug("desktop_agent.tool_result", {"tool_name": tool_name, "result": payload})
        if self._is_qwen_configured():
            try:
                self._debug("desktop_agent.qwen.summarize_request", {"tool_name": tool_name})
                reply = self.qwen.summarize_tool_result(
                    user_input=user_input,
                    tool_name=tool_name,
                    tool_result=payload,
                    context=json.dumps({"last_tool_result": self.last_tool_result}, ensure_ascii=False),
                )
                self._debug("desktop_agent.qwen.summarize_reply", {"reply": reply})
                self._record_chat(user_input, reply)
                return reply
            except QwenConfigError as exc:
                self._debug(
                    "desktop_agent.qwen.summarize_error",
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
                fallback_note = fallback_note or f"千问总结工具结果失败，已使用本地回复。原因：{exc}"
        return self._fallback_reply(result, fallback_note=fallback_note)

    def _fallback_reply(self, result: DesktopToolResult, *, fallback_note: str = "") -> str:
        payload = result.to_dict()
        self.last_tool_result = payload
        self._debug("desktop_agent.tool_result", {"result": payload, "fallback_note": fallback_note})
        pieces = []
        if fallback_note:
            pieces.append(fallback_note)
        if result.requires_user_action:
            pieces.append(result.message)
        elif result.status == "ok":
            pieces.append(result.message)
        elif result.status == "not_confirmed":
            pieces.append(result.message)
        elif result.status == "not_found":
            pieces.append(result.message)
        else:
            pieces.append(result.message or f"工具执行状态：{result.status}")
        if result.matched_control:
            pieces.append(f"匹配控件：{result.matched_control}")
        if self.verbose:
            pieces.append(json.dumps(payload, ensure_ascii=False, indent=2))
        return "\n".join(piece for piece in pieces if piece)

    def _fallback_tool_call(self, user_input: str) -> dict[str, Any] | None:
        return detect_ezviz_desktop_tool(user_input)

    def _is_qwen_configured(self) -> bool:
        return bool(getattr(self.qwen, "is_configured", False))

    def _qwen_config_error_message(self) -> str:
        config_error = getattr(self.qwen, "config_error", None)
        if config_error:
            return str(config_error)
        return "请设置真实可用的 DASHSCOPE_API_KEY。"

    def _local_fallback_note(self, reason: str | None = None) -> str:
        if reason:
            if "DASHSCOPE_API_KEY is required" in reason:
                return f"千问未配置，已使用本地兜底路由。原因：{reason}"
            return f"千问暂时不可用，已使用本地兜底路由。原因：{reason}"
        return "千问暂时不可用，已使用本地兜底路由。"

    def _qwen_unavailable_reply(self, user_input: str, reason: str, *, prefix: str) -> str:
        intro = self._local_identity_reply(user_input)
        capability_hint = (
            "我仍可以用本地规则帮你操作萤石客户端，例如："
            "打开视频监控、打开预览、打开回放、看告警消息、进入终端配置。"
        )
        if intro:
            return f"{intro}\n{prefix}：{reason}\n{capability_hint}"
        return f"{prefix}：{reason}\n{capability_hint}"

    def _local_identity_reply(self, user_input: str) -> str:
        lowered = user_input.lower()
        if any(keyword in user_input for keyword in ["你叫什么", "你是谁", "名字", "叫什么名字"]) or any(
            keyword in lowered for keyword in ["who are you", "your name"]
        ):
            return "我叫 AgentSurf，是这个桌面智能体，负责帮你用自然语言控制萤石工作室。"
        return ""

    def _record_chat(self, user_input: str, reply: str) -> None:
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})

    def _first_tool_call(self, message: Any) -> ParsedToolCall | None:
        tool_calls = self._get_value(message, "tool_calls") or []
        if not tool_calls:
            return None
        tool_call = tool_calls[0]
        function = self._get_value(tool_call, "function") or {}
        name = self._get_value(function, "name")
        raw_arguments = self._get_value(function, "arguments") or "{}"
        if not name:
            return None
        if isinstance(raw_arguments, str):
            arguments = json.loads(raw_arguments or "{}")
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            arguments = {}
        return ParsedToolCall(name=name, arguments=arguments)

    def _message_content(self, message: Any) -> str:
        return str(self._get_value(message, "content") or "")

    def _get_value(self, value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _debug(self, event: str, data: Any | None = None) -> None:
        if self.debug_logger is not None:
            self.debug_logger.log(event, data)


def run_desktop_ezviz_repl(
    *,
    exe_path: str,
    qwen_model: str | None,
    qwen_base_url: str | None,
    verbose: bool,
    debug_logger: DebugLogger | None = None,
) -> None:
    if debug_logger is not None:
        debug_logger.log(
            "desktop_agent.repl_start",
            {
                "exe_path": exe_path,
                "qwen_model": qwen_model,
                "qwen_base_url": qwen_base_url,
                "verbose": verbose,
            },
        )
    runtime = DesktopEzvizAgentRuntime(
        tools=DesktopEzvizClientTools(exe_path=exe_path, debug_logger=debug_logger),
        qwen=QwenClient(model=qwen_model, base_url=qwen_base_url),
        verbose=verbose,
        debug_logger=debug_logger,
    )
    print(DESKTOP_EZVIZ_HELP)
    while True:
        user_input = input("AgentSurf> ")
        output = runtime.handle_message(user_input)
        if output == "EXIT":
            break
        if output:
            print(output)
