from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.desktop_runtime import DesktopEzvizAgentRuntime
from agentsurf.llm import QwenClient
from agentsurf.tools.desktop_ezviz import DesktopToolResult


class FakeQwen:
    def __init__(self, tool_name: str | None = None, reply: str = "已完成。") -> None:
        self.tool_name = tool_name
        self.reply = reply
        self.is_configured = True
        self.tool_messages: list[dict] = []
        self.tool_schemas: list[list[dict]] = []
        self.summary_calls: list[dict] = []

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.tool_messages.append({"messages": messages, "tool_choice": tool_choice})
        self.tool_schemas.append(tools)
        if self.tool_name is None:
            return {"content": "普通聊天回复", "tool_calls": []}
        return {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": self.tool_name,
                        "arguments": "{}",
                    }
                }
            ],
        }

    def summarize_tool_result(self, **kwargs):
        self.summary_calls.append(kwargs)
        return self.reply


class FakeDesktopTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def observe_window(self) -> DesktopToolResult:
        self.calls.append(("observe_window", None))
        return DesktopToolResult(status="ok", message="Observed fake window.")

    def open_video_monitor(self) -> DesktopToolResult:
        self.calls.append(("open_video_monitor", None))
        return DesktopToolResult(
            status="ok",
            message="Opened fake video monitor.",
            matched_control="\u89c6\u9891\u76d1\u63a7",
            data={"tool_name": "open_video_monitor", "page_confirmed": True},
        )

    def open_video_monitor_section(self, section: str) -> DesktopToolResult:
        self.calls.append(("open_video_monitor_section", section))
        return DesktopToolResult(
            status="ok",
            message=f"Opened fake section: {section}.",
            matched_control=section,
            data={
                "tool_name": "open_video_monitor_section",
                "section": section,
                "page_confirmed": True,
                "section_confirmed": True,
            },
        )


class FailingDesktopTools(FakeDesktopTools):
    def open_video_monitor_section(self, section: str) -> DesktopToolResult:
        self.calls.append(("open_video_monitor_section", section))
        return DesktopToolResult(
            status="error",
            message=f"Failed fake section: {section}.",
            data={"tool_name": "open_video_monitor_section", "section": section},
        )


class FakeDebugLogger:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def log(self, event: str, data=None) -> None:
        self.records.append({"event": event, "data": data if data is not None else {}})

    @property
    def events(self) -> list[str]:
        return [record["event"] for record in self.records]


class DesktopEzvizAgentRuntimeTest(unittest.TestCase):
    def test_qwen_function_call_opens_playback_and_summarizes(self) -> None:
        qwen = FakeQwen(tool_name="open_video_playback", reply="\u5df2\u8fdb\u5165\u56de\u653e\u9875\u9762\u3002")
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=qwen)

        output = runtime.handle_message("\u6253\u5f00\u56de\u653e")

        self.assertEqual(output, "\u5df2\u8fdb\u5165\u56de\u653e\u9875\u9762\u3002")
        self.assertEqual(tools.calls, [("open_video_monitor_section", "playback")])
        self.assertEqual(qwen.summary_calls[0]["tool_name"], "open_video_playback")
        self.assertEqual(qwen.summary_calls[0]["tool_result"]["status"], "ok")

    def test_qwen_function_names_map_to_desktop_sections(self) -> None:
        cases = {
            "open_video_preview": "preview",
            "open_video_playback": "playback",
            "open_video_messages": "messages",
            "open_terminal_config": "terminal_config",
        }
        for function_name, section in cases.items():
            with self.subTest(function_name=function_name):
                qwen = FakeQwen(tool_name=function_name)
                tools = FakeDesktopTools()
                runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=qwen)

                runtime.handle_message("test")

                self.assertEqual(tools.calls, [("open_video_monitor_section", section)])

    def test_qwen_function_call_opens_video_monitor(self) -> None:
        qwen = FakeQwen(tool_name="open_video_monitor")
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=qwen)

        runtime.handle_message("\u6253\u5f00\u89c6\u9891\u76d1\u63a7")

        self.assertEqual(tools.calls, [("open_video_monitor", None)])

    def test_qwen_chat_without_tool_returns_natural_reply(self) -> None:
        qwen = FakeQwen(tool_name=None)
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=qwen)

        output = runtime.handle_message("\u4f60\u597d")

        self.assertEqual(output, "\u666e\u901a\u804a\u5929\u56de\u590d")
        self.assertEqual(tools.calls, [])

    def test_missing_qwen_uses_local_fallback(self) -> None:
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=QwenClient(api_key=""))

        output = runtime.handle_message("\u6253\u5f00\u56de\u653e")

        self.assertIn("\u5343\u95ee\u672a\u914d\u7f6e", output)
        self.assertEqual(tools.calls, [("open_video_monitor_section", "playback")])

    def test_invalid_qwen_key_self_intro_uses_local_reply(self) -> None:
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(
            tools=tools,
            qwen=QwenClient(api_key="\u4f60\u7684\u5343\u95eeKey"),
        )

        output = runtime.handle_message("\u4f60\u53eb\u4ec0\u4e48\u540d\u5b57\uff1f")

        self.assertIn("AgentSurf", output)
        self.assertIn("DASHSCOPE_API_KEY", output)
        self.assertEqual(tools.calls, [])

    def test_invalid_qwen_key_still_routes_ezviz_tool_locally(self) -> None:
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(
            tools=tools,
            qwen=QwenClient(api_key="\u4f60\u7684\u5343\u95eeKey"),
        )

        output = runtime.handle_message("\u6253\u5f00\u56de\u653e")

        self.assertIn("\u5343\u95ee\u6682\u65f6\u4e0d\u53ef\u7528", output)
        self.assertEqual(tools.calls, [("open_video_monitor_section", "playback")])

    def test_debug_logs_qwen_tool_call_path(self) -> None:
        debug = FakeDebugLogger()
        qwen = FakeQwen(tool_name="open_video_playback", reply="done")
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=qwen, debug_logger=debug)

        output = runtime.handle_message("\u6253\u5f00\u56de\u653e")

        self.assertEqual(output, "done")
        self.assertIn("desktop_agent.input", debug.events)
        self.assertIn("desktop_agent.qwen.request", debug.events)
        self.assertIn("desktop_agent.qwen.tool_call", debug.events)
        self.assertIn("desktop_agent.tool_dispatch", debug.events)
        self.assertIn("desktop_agent.tool_result", debug.events)
        self.assertIn("desktop_agent.qwen.summarize_reply", debug.events)

    def test_debug_logs_local_fallback_path(self) -> None:
        debug = FakeDebugLogger()
        tools = FakeDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=QwenClient(api_key=""), debug_logger=debug)

        runtime.handle_message("\u6253\u5f00\u56de\u653e")

        self.assertEqual(tools.calls, [("open_video_monitor_section", "playback")])
        self.assertIn("desktop_agent.local_route", debug.events)
        self.assertIn("desktop_agent.tool_dispatch", debug.events)
        self.assertIn("desktop_agent.tool_result", debug.events)

    def test_debug_logs_tool_failure_result(self) -> None:
        debug = FakeDebugLogger()
        qwen = FakeQwen(tool_name="open_video_playback", reply="done")
        tools = FailingDesktopTools()
        runtime = DesktopEzvizAgentRuntime(tools=tools, qwen=qwen, debug_logger=debug)

        runtime.handle_message("\u6253\u5f00\u56de\u653e")

        tool_result_records = [
            record for record in debug.records if record["event"] == "desktop_agent.tool_result"
        ]
        self.assertTrue(tool_result_records)
        self.assertEqual(tool_result_records[0]["data"]["result"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
