from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.agent import BrowserAgent, RuleBasedPlanner
from agentsurf.browser import InMemoryBrowserSession, PlaywrightBrowserSession, execute_browser_action
from agentsurf.schemas import ActionType, BrowserAction
from agentsurf.vision import HeuristicVisionAnalyzer, analyze_screenshot, extract_ui_elements, suggest_next_action


class BrowserToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_in_memory_browser_executes_required_tools(self) -> None:
        browser = InMemoryBrowserSession()

        opened = await execute_browser_action(
            browser,
            BrowserAction(type=ActionType.OPEN_URL, url="https://example.com"),
        )
        clicked = await execute_browser_action(browser, BrowserAction(type=ActionType.CLICK, selector="#submit"))
        typed = await execute_browser_action(
            browser,
            BrowserAction(type=ActionType.TYPE, selector="#email", text="name@example.com"),
        )
        screenshot = await execute_browser_action(browser, BrowserAction(type=ActionType.SCREENSHOT))

        self.assertEqual(opened.url, "https://example.com")
        self.assertEqual(clicked.ui_state["last_clicked"], "#submit")
        self.assertEqual(typed.ui_state["typed_values"]["#email"], "name@example.com")
        self.assertIsNotNone(screenshot.screenshot_base64)


class PlaywrightBrowserSessionTest(unittest.TestCase):
    def test_desktop_chrome_options_use_visible_system_browser_profile(self) -> None:
        session = PlaywrightBrowserSession(
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            user_data_dir=".runtime/chrome-profile",
        )

        options = session.launch_options()

        self.assertFalse(options["headless"])
        self.assertEqual(options["executable_path"], r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        self.assertIn("--no-first-run", options["args"])
        self.assertEqual(session.user_data_dir, ".runtime/chrome-profile")


class AgentLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_opens_url_observes_and_finishes(self) -> None:
        browser = InMemoryBrowserSession()
        agent = BrowserAgent(browser, HeuristicVisionAnalyzer(), RuleBasedPlanner())

        state = await agent.run("open https://example.com and observe it", max_steps=4)

        self.assertTrue(state.done)
        self.assertEqual(state.current_observation.url, "https://example.com")
        self.assertTrue(any(step.action.type == ActionType.OPEN_URL for step in state.steps))
        self.assertEqual(state.steps[-1].action.type, ActionType.DONE)

    async def test_agent_opens_bilibili_from_chinese_task(self) -> None:
        browser = InMemoryBrowserSession()
        agent = BrowserAgent(browser, HeuristicVisionAnalyzer(), RuleBasedPlanner())

        state = await agent.run("\u5e2e\u6211\u6253\u5f00\u54d4\u54e9\u54d4\u54e9\uff0c", max_steps=4)

        self.assertTrue(state.done)
        self.assertEqual(state.current_observation.url, "https://www.bilibili.com")
        self.assertTrue(any(step.action.type == ActionType.OPEN_URL for step in state.steps))

    async def test_agent_opens_bare_bilibili_domain(self) -> None:
        browser = InMemoryBrowserSession()
        agent = BrowserAgent(browser, HeuristicVisionAnalyzer(), RuleBasedPlanner())

        state = await agent.run("\u6253\u5f00www.bilibili.com\u7f51\u5740", max_steps=4)

        self.assertTrue(state.done)
        self.assertEqual(state.current_observation.url, "https://www.bilibili.com")


class VisionToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_named_vision_tools_match_requirement_api(self) -> None:
        browser = InMemoryBrowserSession("https://example.com")
        observation = await browser.screenshot()

        vision = await analyze_screenshot(HeuristicVisionAnalyzer(), observation, "observe the page")

        self.assertIn("https://example.com", vision.summary)
        self.assertEqual(extract_ui_elements(vision), [])
        self.assertIsNone(suggest_next_action(vision))


if __name__ == "__main__":
    unittest.main()
