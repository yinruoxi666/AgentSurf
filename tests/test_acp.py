from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.acp import AcpAgentServer


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


if __name__ == "__main__":
    unittest.main()
