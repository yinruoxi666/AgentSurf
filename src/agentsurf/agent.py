from __future__ import annotations

import re
from typing import Protocol

from .browser import BrowserSession, execute_browser_action
from .schemas import ActionType, AgentState, AgentStep, BrowserAction, VisionResult
from .vision import VisionAnalyzer


URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"(?<![@\w.-])(?:www\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
    r"(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
    re.IGNORECASE,
)
CLICK_RE = re.compile(r"click\s+([#.\[\]\w='\"-]+)", re.IGNORECASE)
TYPE_RE = re.compile(r"type\s+([#.\[\]\w='\"-]+)\s+(.+)$", re.IGNORECASE)
SITE_ALIASES = {
    "bilibili": "https://www.bilibili.com",
    "\u54d4\u54e9\u54d4\u54e9": "https://www.bilibili.com",
    "b\u7ad9": "https://www.bilibili.com",
}
TRAILING_URL_PUNCTUATION = ".,);\uff0c\u3002\uff1b\uff01"


class Planner(Protocol):
    async def next_action(
        self,
        task: str,
        state: AgentState,
        vision: VisionResult,
    ) -> BrowserAction:
        ...


class RuleBasedPlanner:
    async def next_action(
        self,
        task: str,
        state: AgentState,
        vision: VisionResult,
    ) -> BrowserAction:
        url = self._extract_url(task)
        if url and not self._has_action(state, ActionType.OPEN_URL, url=url):
            return BrowserAction(type=ActionType.OPEN_URL, url=url, reason="Open requested URL")

        type_match = TYPE_RE.search(task)
        if type_match and not self._has_action(state, ActionType.TYPE, selector=type_match.group(1)):
            return BrowserAction(
                type=ActionType.TYPE,
                selector=type_match.group(1),
                text=type_match.group(2).strip(),
                reason="Fill requested field",
            )

        click_match = CLICK_RE.search(task)
        if click_match and not self._has_action(state, ActionType.CLICK, selector=click_match.group(1)):
            return BrowserAction(
                type=ActionType.CLICK,
                selector=click_match.group(1),
                reason="Click requested element",
            )

        if vision.suggested_action is not None:
            return vision.suggested_action

        return BrowserAction(type=ActionType.DONE, reason="No further action required")

    def _extract_url(self, task: str) -> str | None:
        match = URL_RE.search(task)
        if match is not None:
            return match.group(0).rstrip(TRAILING_URL_PUNCTUATION)

        domain_match = DOMAIN_RE.search(task)
        if domain_match is not None:
            domain = domain_match.group(0).rstrip(TRAILING_URL_PUNCTUATION)
            return f"https://{domain}"

        normalized_task = task.lower()
        for alias, url in SITE_ALIASES.items():
            if alias in normalized_task:
                return url
        return None

    def _has_action(
        self,
        state: AgentState,
        action_type: ActionType,
        *,
        url: str | None = None,
        selector: str | None = None,
    ) -> bool:
        for step in state.steps:
            action = step.action
            if action.type != action_type:
                continue
            if url is not None and action.url != url:
                continue
            if selector is not None and action.selector != selector:
                continue
            return True
        return False


class BrowserAgent:
    def __init__(
        self,
        browser: BrowserSession,
        vision: VisionAnalyzer,
        planner: Planner,
    ) -> None:
        self.browser = browser
        self.vision = vision
        self.planner = planner

    async def run(self, task: str, max_steps: int = 8) -> AgentState:
        state = AgentState(task=task)
        for _ in range(max_steps):
            observed = await execute_browser_action(
                self.browser,
                BrowserAction(type=ActionType.OBSERVE, reason="Observe current screen"),
            )
            vision_result = await self.vision.analyze_screenshot(observed, task)
            state.current_observation = observed
            state.last_vision = vision_result

            action = await self.planner.next_action(task, state, vision_result)
            if action.type == ActionType.DONE:
                state.done = True
                state.steps.append(AgentStep(action=action, observation=observed, vision=vision_result))
                break

            observation = await execute_browser_action(self.browser, action)
            state.current_observation = observation
            state.steps.append(AgentStep(action=action, observation=observation, vision=vision_result))
        return state
