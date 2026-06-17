from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from .schemas import BrowserAction, Observation, UiElement, VisionResult


class VisionAnalyzer(Protocol):
    async def analyze_screenshot(self, observation: Observation, task: str) -> VisionResult:
        ...


VisionCallback = Callable[[Observation, str], Awaitable[VisionResult | dict | str]]


class HeuristicVisionAnalyzer:
    async def analyze_screenshot(self, observation: Observation, task: str) -> VisionResult:
        elements = [
            UiElement(**element)
            for element in observation.ui_state.get("elements", [])
            if isinstance(element, dict)
        ]
        location = observation.url or "about:blank"
        summary = f"Observed {location} with {len(elements)} interactive element(s)."
        return VisionResult(summary=summary, elements=elements, raw={"task": task})


class CallbackVisionAnalyzer:
    def __init__(self, callback: VisionCallback) -> None:
        self.callback = callback

    async def analyze_screenshot(self, observation: Observation, task: str) -> VisionResult:
        result = await self.callback(observation, task)
        if isinstance(result, VisionResult):
            return result
        if isinstance(result, str):
            return VisionResult(summary=result)
        if isinstance(result, dict):
            suggested_action = result.get("suggested_action")
            if isinstance(suggested_action, dict):
                result = {**result, "suggested_action": BrowserAction(**suggested_action)}
            return VisionResult(**result)
        raise TypeError("Vision callback must return VisionResult, dict, or str")


async def analyze_screenshot(
    analyzer: VisionAnalyzer,
    observation: Observation,
    task: str,
) -> VisionResult:
    return await analyzer.analyze_screenshot(observation, task)


def extract_ui_elements(vision_result: VisionResult) -> list[UiElement]:
    return vision_result.elements


def suggest_next_action(vision_result: VisionResult) -> BrowserAction | None:
    return vision_result.suggested_action
