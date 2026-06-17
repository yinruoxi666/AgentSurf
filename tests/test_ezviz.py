from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.llm import LocalIntentRouter, QwenClient, QwenConfigError
from agentsurf.runtime import EzvizAgentRuntime
from agentsurf.schemas import Observation
from agentsurf.tools.ezviz import EzvizConsoleTools


class FakeBrowser:
    def __init__(
        self,
        observation: Observation | None = None,
        open_observations: dict[str, Observation | list[Observation]] | None = None,
        screenshot_observations: list[Observation] | None = None,
    ) -> None:
        self.observation = observation or Observation(
            url="https://open.ys7.com/console/home.html",
            title="EZVIZ",
            ui_state={"visible_text": "console device list", "elements": []},
        )
        self.opened_urls: list[str] = []
        self.open_observations = {
            url: observations if isinstance(observations, list) else [observations]
            for url, observations in (open_observations or {}).items()
        }
        self.screenshot_observations = list(screenshot_observations or [])

    async def open_url(self, url: str) -> Observation:
        self.opened_urls.append(url)
        if url in self.open_observations:
            observations = self.open_observations[url]
            self.observation = observations.pop(0) if len(observations) > 1 else observations[0]
        return self.observation

    async def screenshot(self) -> Observation:
        if self.screenshot_observations:
            self.observation = self.screenshot_observations.pop(0)
        return self.observation


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.content)


class FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = FakeCompletions(content)


class FakeOpenAIClient:
    def __init__(self, content: str) -> None:
        self.chat = FakeChat(content)


class QwenClientTest(unittest.TestCase):
    def test_missing_api_key_raises_clear_error(self) -> None:
        client = QwenClient(api_key="", client=None)

        with self.assertRaises(QwenConfigError) as context:
            client.chat("hello")

        self.assertIn("DASHSCOPE_API_KEY", str(context.exception))

    def test_mock_client_routes_to_tool_json(self) -> None:
        client = QwenClient(
            client=FakeOpenAIClient(
                '{"mode":"tool","tool_name":"ezviz_open_console","tool_args":{},"reply":""}'
            )
        )

        decision = client.route("\u6253\u5f00\u8424\u77f3\u4e91\u63a7\u5236\u53f0")

        self.assertEqual(decision.mode, "tool")
        self.assertEqual(decision.tool_name, "ezviz_open_console")


class LocalIntentRouterTest(unittest.TestCase):
    def test_routes_ezviz_console_request(self) -> None:
        decision = LocalIntentRouter().route("\u6253\u5f00\u8424\u77f3\u4e91\u63a7\u5236\u53f0")

        self.assertEqual(decision.tool_name, "ezviz_open_console")

    def test_routes_english_ezviz_console_request(self) -> None:
        decision = LocalIntentRouter().route("open ezviz console")

        self.assertEqual(decision.tool_name, "ezviz_open_console")

    def test_routes_device_list_request(self) -> None:
        decision = LocalIntentRouter().route("\u67e5\u770b\u8bbe\u5907\u5217\u8868")

        self.assertEqual(decision.tool_name, "ezviz_open_section")
        self.assertEqual(decision.tool_args["section"], "devices")

    def test_routes_device_list_variants(self) -> None:
        router = LocalIntentRouter()

        for prompt in [
            "\u770b\u770b\u8bbe\u5907\u5217\u8868",
            "\u770b\u4e00\u4e0b\u5f53\u524d\u9875\u9762\u6709\u4ec0\u4e48\u8bbe\u5907",
        ]:
            decision = router.route(prompt)
            self.assertEqual(decision.tool_name, "ezviz_open_section")
            self.assertEqual(decision.tool_args["section"], "devices")

    def test_routes_cloud_recording_request(self) -> None:
        decision = LocalIntentRouter().route("\u6253\u5f00\u4e91\u5f55\u50cf\u9875\u9762")

        self.assertEqual(decision.tool_name, "ezviz_open_section")
        self.assertEqual(decision.tool_args["section"], "cloud_recording")

    def test_normal_chat_does_not_call_tool(self) -> None:
        decision = LocalIntentRouter().route("hello")

        self.assertEqual(decision.mode, "chat")


class EzvizToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_open_console_requires_user_action_on_login_page(self) -> None:
        browser = FakeBrowser(
            Observation(
                url="https://open.ys7.com/login",
                title="\u767b\u5f55",
                ui_state={"visible_text": "\u8bf7\u767b\u5f55 \u9a8c\u8bc1\u7801", "elements": []},
            )
        )
        tools = EzvizConsoleTools(browser)

        result = await tools.open_console()

        self.assertEqual(result.status, "requires_user_action")
        self.assertTrue(result.requires_user_action)

    async def test_device_section_opens_device_page_url(self) -> None:
        browser = FakeBrowser()
        tools = EzvizConsoleTools(browser)

        result = await tools.dispatch("ezviz_open_section", {"section": "devices"})

        self.assertEqual(result.status, "ok")
        self.assertEqual(browser.opened_urls, ["https://open.ys7.com/console/device.html"])

    async def test_device_section_normalizes_qwen_section_alias(self) -> None:
        browser = FakeBrowser()
        tools = EzvizConsoleTools(browser)

        result = await tools.dispatch("ezviz_open_section", {"section": "device_list"})

        self.assertEqual(result.status, "ok")
        self.assertEqual(browser.opened_urls, ["https://open.ys7.com/console/device.html"])

    async def test_home_page_login_text_without_form_is_logged_in(self) -> None:
        browser = FakeBrowser(
            Observation(
                url="https://open.ys7.com/console/home.html",
                title="EZVIZ",
                ui_state={"visible_text": "\u767b\u5f55 \u8bbe\u5907\u5217\u8868", "elements": []},
            )
        )
        tools = EzvizConsoleTools(browser)

        result = await tools.check_login()

        self.assertEqual(result.status, "ok")
        self.assertFalse(result.data["login_required"])
        self.assertTrue(result.data["logged_in"])

    async def test_password_input_marks_page_as_login_required(self) -> None:
        browser = FakeBrowser(
            Observation(
                url="https://open.ys7.com/console/home.html",
                title="EZVIZ",
                ui_state={
                    "visible_text": "",
                    "elements": [{"role": "input", "type": "password", "placeholder": "\u5bc6\u7801"}],
                },
            )
        )
        tools = EzvizConsoleTools(browser)

        result = await tools.check_login()

        self.assertEqual(result.status, "requires_user_action")
        self.assertTrue(result.data["login_required"])
        self.assertFalse(result.data["logged_in"])

    async def test_dangerous_request_is_blocked(self) -> None:
        tools = EzvizConsoleTools(FakeBrowser())

        result = await tools.dispatch("ezviz_observe_page", {}, original_request="\u5220\u9664\u8bbe\u5907")

        self.assertEqual(result.status, "confirmation_required")
        self.assertTrue(result.requires_user_action)

    async def test_english_dangerous_request_is_blocked(self) -> None:
        tools = EzvizConsoleTools(FakeBrowser())

        result = await tools.dispatch("ezviz_observe_page", {}, original_request="delete device")

        self.assertEqual(result.status, "confirmation_required")
        self.assertTrue(result.requires_user_action)


class EzvizRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_uses_local_tool_routing_without_qwen_key(self) -> None:
        browser = FakeBrowser()
        tools = EzvizConsoleTools(browser)
        runtime = EzvizAgentRuntime(browser=browser, tools=tools, qwen=QwenClient(api_key=""))

        output = await runtime.handle_message("\u6253\u5f00\u8424\u77f3\u4e91\u63a7\u5236\u53f0")

        self.assertIn("https://open.ys7.com/console/home.html", output)

    async def test_runtime_forces_device_request_even_when_qwen_observes(self) -> None:
        browser = FakeBrowser()
        tools = EzvizConsoleTools(browser)
        qwen = QwenClient(
            client=FakeOpenAIClient(
                '{"mode":"tool","tool_name":"ezviz_observe_page","tool_args":{"query":"devices"},"reply":""}'
            )
        )
        runtime = EzvizAgentRuntime(browser=browser, tools=tools, qwen=qwen)

        await runtime.handle_message("\u770b\u4e00\u4e0b\u5f53\u524d\u9875\u9762\u6709\u4ec0\u4e48\u8bbe\u5907")

        self.assertEqual(browser.opened_urls, ["https://open.ys7.com/console/device.html"])

    async def test_runtime_retries_pending_device_page_after_login_done(self) -> None:
        login_observation = Observation(
            url="https://open.ys7.com/console/login.html?returnUrl=%2Fconsole%2Fdevice.html",
            title="EZVIZ",
            ui_state={"visible_text": "\u8bf7\u767b\u5f55", "elements": []},
        )
        logged_in_observation = Observation(
            url="https://open.ys7.com/console/home.html",
            title="EZVIZ",
            ui_state={"visible_text": "\u8bbe\u5907\u5217\u8868", "elements": []},
        )
        device_observation = Observation(
            url="https://open.ys7.com/console/device.html",
            title="EZVIZ",
            ui_state={"visible_text": "\u8bbe\u5907\u5217\u8868", "elements": []},
        )
        browser = FakeBrowser(
            open_observations={
                "https://open.ys7.com/console/device.html": [login_observation, device_observation]
            },
            screenshot_observations=[logged_in_observation],
        )
        tools = EzvizConsoleTools(browser)
        runtime = EzvizAgentRuntime(browser=browser, tools=tools, qwen=QwenClient(api_key=""))

        first_output = await runtime.handle_message("\u67e5\u770b\u8bbe\u5907\u5217\u8868")
        first_payload = json.loads(first_output)
        second_output = await runtime.handle_message("/login-done")
        second_payload = json.loads(second_output)

        self.assertEqual(first_payload["status"], "requires_user_action")
        self.assertEqual(first_payload["data"]["logged_in"], False)
        self.assertEqual(first_payload["data"]["pending_tool_call"]["tool_args"]["section"], "devices")
        self.assertEqual(second_payload["status"], "ok")
        self.assertEqual(second_payload["url"], "https://open.ys7.com/console/device.html")
        self.assertEqual(second_payload["data"]["logged_in"], True)
        self.assertIsNone(second_payload["data"]["pending_tool_call"])
        self.assertEqual(
            browser.opened_urls,
            [
                "https://open.ys7.com/console/device.html",
                "https://open.ys7.com/console/device.html",
            ],
        )


if __name__ == "__main__":
    unittest.main()
