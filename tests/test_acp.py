from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.acp import AcpAgentServer
from agentsurf.tools.desktop_ezviz import DesktopToolResult


class FakeDesktopTools:
    def open_video_monitor(self) -> DesktopToolResult:
        return DesktopToolResult(
            status="ok",
            message="Opened fake video monitor.",
            window_title="EZVIZ",
            matched_control="\u89c6\u9891\u76d1\u63a7",
            visible_text_excerpt="\u89c6\u9891\u76d1\u63a7",
            data={"tool_name": "open_video_monitor"},
        )

    def open_video_monitor_section(self, section: str) -> DesktopToolResult:
        return DesktopToolResult(
            status="ok",
            message=f"Opened fake section: {section}.",
            window_title="EZVIZ",
            matched_control=section,
            visible_text_excerpt="\u9884\u89c8\n\u56de\u653e\n\u6d88\u606f\n\u7ec8\u7aef\u914d\u7f6e",
            data={"tool_name": "open_video_monitor_section", "section": section},
        )


class FakeQwen:
    def __init__(self, tool_name: str, reply: str) -> None:
        self.tool_name = tool_name
        self.reply = reply
        self.is_configured = True

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
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
        return self.reply


class AcpAgentServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_returns_agent_metadata(self) -> None:
        server = AcpAgentServer()

        messages = await server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        self.assertEqual(messages[0]["id"], 1)
        self.assertEqual(messages[0]["result"]["agent"]["name"], "AgentSurf")
        self.assertTrue(messages[0]["result"]["capabilities"]["prompts"])

    async def test_session_prompt_runs_browser_agent(self) -> None:
        server = AcpAgentServer(max_steps=4)
        session_response = await server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {}})
        session_id = session_response[0]["result"]["sessionId"]

        messages = await server.handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "open https://example.com and observe it"}],
                },
            }
        )

        update, response = messages
        text = update["params"]["update"]["content"]["text"]
        self.assertEqual(update["method"], "session/update")
        self.assertIn("https://example.com", text)
        self.assertEqual(response["result"]["stopReason"], "end_turn")

    async def test_prompt_accepts_content_shape(self) -> None:
        server = AcpAgentServer(max_steps=4)
        session_response = await server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {}})
        session_id = session_response[0]["result"]["sessionId"]

        messages = await server.handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "content": {"type": "text", "text": "打开www.bilibili.com网址"},
                },
            }
        )

        self.assertIn("https://www.bilibili.com", messages[0]["params"]["update"]["content"]["text"])

    async def test_rpc_line_reports_parse_error(self) -> None:
        server = AcpAgentServer()

        messages = await server.handle_rpc_line("{not-json")

        self.assertEqual(messages[0]["error"]["code"], -32700)

    async def test_stdio_json_serializes_response(self) -> None:
        server = AcpAgentServer()

        messages = await server.handle_rpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        )

        self.assertEqual(messages[0]["result"]["protocolVersion"], 1)

    async def test_ezviz_desktop_prompt_routes_to_desktop_tool(self) -> None:
        server = AcpAgentServer(
            desktop_tools_factory=FakeDesktopTools,
            desktop_qwen_factory=lambda: FakeQwen("open_video_monitor", "\u5df2\u6253\u5f00\u89c6\u9891\u76d1\u63a7\u3002"),
        )
        session_response = await server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {}})
        session_id = session_response[0]["result"]["sessionId"]

        messages = await server.handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [
                        {
                            "type": "text",
                            "text": "\u6253\u5f00\u8424\u77f3\u5de5\u4f5c\u5ba4\u8fdb\u5165\u89c6\u9891\u76d1\u63a7",
                        }
                    ],
                },
            }
        )

        text = messages[0]["params"]["update"]["content"]["text"]
        self.assertEqual(text, "\u5df2\u6253\u5f00\u89c6\u9891\u76d1\u63a7\u3002")

    async def test_ezviz_section_prompt_routes_to_section_tool(self) -> None:
        server = AcpAgentServer(
            desktop_tools_factory=FakeDesktopTools,
            desktop_qwen_factory=lambda: FakeQwen("open_video_playback", "\u5df2\u8fdb\u5165\u56de\u653e\u9875\u9762\u3002"),
        )
        session_response = await server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {}})
        session_id = session_response[0]["result"]["sessionId"]

        messages = await server.handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "content": {"type": "text", "text": "\u6253\u5f00\u56de\u653e"},
                },
            }
        )

        text = messages[0]["params"]["update"]["content"]["text"]
        self.assertEqual(text, "\u5df2\u8fdb\u5165\u56de\u653e\u9875\u9762\u3002")


if __name__ == "__main__":
    unittest.main()
