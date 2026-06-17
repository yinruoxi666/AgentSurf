from __future__ import annotations

from typing import Any

from .agent import Planner
from .browser import BrowserSession, execute_browser_action
from .schemas import ActionType, AgentState, AgentStep, BrowserAction
from .vision import VisionAnalyzer


def build_langgraph_workflow(
    browser: BrowserSession,
    vision: VisionAnalyzer,
    planner: Planner,
) -> Any:
    try:
        from langgraph.graph import END, StateGraph
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Install with `python -m pip install -e .[graph]`."
        ) from exc

    async def observe_node(state: dict[str, Any]) -> dict[str, Any]:
        observation = await execute_browser_action(
            browser,
            BrowserAction(type=ActionType.OBSERVE, reason="Observe current screen"),
        )
        vision_result = await vision.analyze_screenshot(observation, state["task"])
        return {"observation": observation, "vision": vision_result}

    async def plan_node(state: dict[str, Any]) -> dict[str, Any]:
        agent_state = state.get("agent_state") or AgentState(task=state["task"])
        action = await planner.next_action(state["task"], agent_state, state["vision"])
        return {"agent_state": agent_state, "action": action, "done": action.type == ActionType.DONE}

    async def act_node(state: dict[str, Any]) -> dict[str, Any]:
        agent_state = state["agent_state"]
        action = state["action"]
        if action.type == ActionType.DONE:
            agent_state.done = True
            agent_state.steps.append(
                AgentStep(action=action, observation=state["observation"], vision=state["vision"])
            )
            return {"agent_state": agent_state}

        observation = await execute_browser_action(browser, action)
        agent_state.current_observation = observation
        agent_state.last_vision = state["vision"]
        agent_state.steps.append(AgentStep(action=action, observation=observation, vision=state["vision"]))
        return {"agent_state": agent_state, "observation": observation}

    def should_continue(state: dict[str, Any]) -> str:
        return "done" if state.get("done") else "act"

    graph = StateGraph(dict)
    graph.add_node("observe", observe_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.set_entry_point("observe")
    graph.add_edge("observe", "plan")
    graph.add_conditional_edges("plan", should_continue, {"done": END, "act": "act"})
    graph.add_edge("act", "observe")
    return graph.compile()
