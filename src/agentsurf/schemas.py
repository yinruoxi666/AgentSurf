from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    OPEN_URL = "open_url"
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    OBSERVE = "observe"
    DONE = "done"


class BrowserAction(BaseModel):
    type: ActionType
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    reason: str | None = None


class UiElement(BaseModel):
    selector: str | None = None
    role: str | None = None
    label: str | None = None
    text: str | None = None
    bounds: dict[str, float] | None = None


class Observation(BaseModel):
    url: str | None = None
    title: str | None = None
    screenshot_base64: str | None = None
    ui_state: dict[str, Any] = Field(default_factory=dict)
    action: BrowserAction | None = None


class VisionResult(BaseModel):
    summary: str
    elements: list[UiElement] = Field(default_factory=list)
    suggested_action: BrowserAction | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AgentStep(BaseModel):
    action: BrowserAction
    observation: Observation
    vision: VisionResult | None = None


class AgentState(BaseModel):
    task: str
    steps: list[AgentStep] = Field(default_factory=list)
    current_observation: Observation | None = None
    last_vision: VisionResult | None = None
    done: bool = False


class OpenUrlRequest(BaseModel):
    url: str


class ClickRequest(BaseModel):
    selector: str


class TypeRequest(BaseModel):
    selector: str
    text: str


class AgentRunRequest(BaseModel):
    task: str
    max_steps: int = 8
