from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..debug_logging import DebugLogger


DEFAULT_EZVIZ_CLIENT_EXE = r"C:\Program Files (x86)\ESEzvizClient\ESEzvizClient.exe"
DEFAULT_PROCESS_NAME = "ESEzvizClient.exe"

VIDEO_MONITOR_LABELS = [
    "\u89c6\u9891\u76d1\u63a7",
    "\u76d1\u63a7",
    "\u5b9e\u65f6\u9884\u89c8",
    "\u672c\u5730\u8bbe\u5907",
    "\u6211\u7684\u6444\u50cf\u673a",
]

BLOCKING_TEXT_HINTS = [
    "\u8bf7\u767b\u5f55",
    "\u8d26\u53f7\u767b\u5f55",
    "\u767b\u5f55\u5bc6\u7801",
    "\u626b\u7801\u767b\u5f55",
    "\u626b\u63cf\u767b\u5f55",
    "\u8bf7\u4f7f\u7528\u8424\u77f3\u5546\u4e1a\u667a\u5c45app\u626b\u63cf\u767b\u5f55",
    "\u5237\u65b0\u4e8c\u7ef4\u7801",
    "\u65b0\u7528\u6237\u6ce8\u518c",
    "\u9a8c\u8bc1\u7801",
    "\u77ed\u4fe1",
    "\u5bc6\u7801",
    "\u7ec8\u7aef\u7ed1\u5b9a",
    "\u5b89\u5168\u63d0\u793a",
]

BLOCKING_INPUT_HINTS = [
    "password",
    "captcha",
    "sms",
    "\u5bc6\u7801",
    "\u9a8c\u8bc1\u7801",
    "\u77ed\u4fe1",
]

VIDEO_MONITOR_PAGE_HINTS = [
    "\u9884\u89c8",
    "\u56de\u653e",
    "\u6d88\u606f",
    "\u7ec8\u7aef\u914d\u7f6e",
]

VIDEO_MONITOR_ACTION_HINTS = [
    "\u6279\u91cf\u6293\u56fe",
    "\u6279\u91cf\u5173\u95ed",
    "\u5168\u5c4f\u663e\u793a",
]

VIDEO_MONITOR_SECTION_LABELS = {
    "preview": ["\u9884\u89c8", "\u5b9e\u65f6\u9884\u89c8", "\u89c6\u9891\u9884\u89c8", "\u5b9e\u65f6\u753b\u9762"],
    "playback": ["\u56de\u653e", "\u5f55\u50cf\u56de\u653e", "\u5386\u53f2\u89c6\u9891", "\u5f55\u50cf"],
    "messages": ["\u6d88\u606f", "\u544a\u8b66\u6d88\u606f", "\u544a\u8b66", "\u62a5\u8b66", "\u901a\u77e5"],
    "terminal_config": [
        "\u7ec8\u7aef\u914d\u7f6e",
        "\u8bbe\u5907\u914d\u7f6e",
        "\u6444\u50cf\u5934\u914d\u7f6e",
        "\u914d\u7f6e\u6444\u50cf\u5934",
        "\u914d\u7f6e\u7ec8\u7aef",
    ],
}

VIDEO_MONITOR_SECTION_NAMES = {
    "preview": "\u9884\u89c8",
    "playback": "\u56de\u653e",
    "messages": "\u6d88\u606f",
    "terminal_config": "\u7ec8\u7aef\u914d\u7f6e",
}

EZVIZ_DESKTOP_CONTEXT_HINTS = [
    "\u8424\u77f3",
    "\u5de5\u4f5c\u5ba4",
    "\u5ba2\u6237\u7aef",
    "\u89c6\u9891\u76d1\u63a7",
    "\u76d1\u63a7",
    "esezvizclient",
    "ezviz studio",
    "video monitor",
]

DESKTOP_ACTION_HINTS = [
    "\u6253\u5f00",
    "\u8fdb\u5165",
    "\u67e5\u770b",
    "\u770b",
    "\u5207\u6362",
    "\u914d\u7f6e",
    "\u8df3\u8f6c",
    "\u53bb",
    "open",
    "show",
    "view",
    "switch",
]


@dataclass
class DesktopControl:
    text: str = ""
    control_type: str = ""
    automation_id: str = ""

    @property
    def searchable_text(self) -> str:
        return "\n".join([self.text, self.control_type, self.automation_id])


@dataclass
class DesktopWindowSnapshot:
    title: str = ""
    controls: list[DesktopControl] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def visible_text(self) -> str:
        lines = [control.text for control in self.controls if control.text]
        return "\n".join(lines)


@dataclass
class DesktopToolResult:
    status: str
    message: str
    requires_user_action: bool = False
    window_title: str = ""
    matched_control: str | None = None
    visible_text_excerpt: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "requires_user_action": self.requires_user_action,
            "window_title": self.window_title,
            "matched_control": self.matched_control,
            "visible_text_excerpt": self.visible_text_excerpt,
            "data": self.data,
        }


def snapshot_debug_summary(snapshot: DesktopWindowSnapshot, max_controls: int = 30) -> dict[str, Any]:
    return {
        "title": snapshot.title,
        "metadata": snapshot.metadata,
        "control_count": len(snapshot.controls),
        "controls": [
            {
                "text": control.text,
                "control_type": control.control_type,
                "automation_id": control.automation_id,
            }
            for control in snapshot.controls[:max_controls]
        ],
        "visible_text_excerpt": snapshot.visible_text[:1200],
    }


class DesktopEzvizBackend(Protocol):
    def connect_or_start(self, exe_path: str, process_name: str, timeout: float) -> Any:
        ...

    def snapshot(self, window: Any) -> DesktopWindowSnapshot:
        ...

    def click_first_text(self, window: Any, labels: list[str]) -> str | None:
        ...


class PywinautoEzvizBackend:
    def __init__(self, debug_logger: DebugLogger | None = None) -> None:
        self.debug_logger = debug_logger
        try:
            from pywinauto import Application, Desktop
            from pywinauto.findwindows import ElementNotFoundError
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "pywinauto is required for desktop EZVIZ automation. "
                "Install with `python -m pip install -e .[desktop]`."
            ) from exc
        self.Application = Application
        self.Desktop = Desktop
        self.ElementNotFoundError = ElementNotFoundError
        self.app: Any | None = None
        self.window: Any | None = None
        self.window_backend = "uia"

    def connect_or_start(self, exe_path: str, process_name: str, timeout: float) -> Any:
        self._debug(
            "desktop_backend.connect_or_start.start",
            {"exe_path": exe_path, "process_name": process_name, "timeout": timeout},
        )
        connect_error: Exception | None = None
        try:
            self.app = self.Application(backend="uia").connect(path=process_name, timeout=3)
            window = self._wait_for_window(timeout=5)
            if window is not None:
                self.window_backend = "uia"
                self._debug("desktop_backend.connect_or_start.connected_uia", self._window_debug_summary(window))
                return window
        except Exception as exc:
            connect_error = exc
            self._debug(
                "desktop_backend.connect_or_start.uia_failed",
                {"error_type": type(exc).__name__, "error": str(exc)},
            )

        window = self._find_existing_win32_window(process_name)
        if window is not None:
            self.window_backend = "win32"
            self.window = window
            self._debug("desktop_backend.connect_or_start.connected_win32", self._window_debug_summary(window))
            return window

        try:
            self._debug("desktop_backend.connect_or_start.starting_process", {"exe_path": exe_path})
            self.app = self.Application(backend="uia").start(exe_path)
        except Exception as exc:
            window = self._find_existing_win32_window(process_name)
            if window is not None:
                self.window_backend = "win32"
                self.window = window
                self._debug("desktop_backend.connect_or_start.connected_win32_after_start_error", self._window_debug_summary(window))
                return window
            self._debug(
                "desktop_backend.connect_or_start.start_process_failed",
                {"exe_path": exe_path, "error_type": type(exc).__name__, "error": str(exc)},
            )
            raise
        window = self._wait_for_window(timeout=timeout)
        if window is not None:
            self.window_backend = "uia"
            self._debug("desktop_backend.connect_or_start.started_uia", self._window_debug_summary(window))
            return window
        self._debug(
            "desktop_backend.connect_or_start.window_timeout",
            {"timeout": timeout, "connect_error": str(connect_error) if connect_error else None},
        )
        raise RuntimeError(
            f"ESEzvizClient window did not appear within {timeout} seconds after launch. "
            f"Connect error: {connect_error}"
        )

    def _wait_for_window(self, timeout: float) -> Any | None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                windows = self.app.windows()
                if windows:
                    self.window = self._select_best_window(windows)
                    return self.window
                window = self.app.top_window()
                if window.exists(timeout=1):
                    self.window = window
                    return window
            except Exception as exc:
                last_error = exc
            time.sleep(0.5)
        return None

    def _find_existing_win32_window(self, process_name: str) -> Any | None:
        try:
            import psutil
        except ModuleNotFoundError:
            psutil = None

        candidates: list[Any] = []
        try:
            windows = self.Desktop(backend="win32").windows()
        except Exception:
            return None

        for window in windows:
            try:
                title = window.window_text() or ""
                process_id = window.process_id()
                process_matches = False
                if psutil is not None:
                    try:
                        process_matches = psutil.Process(process_id).name().lower() == process_name.lower()
                    except Exception:
                        process_matches = False
                title_matches = "esezvizclient" in title.lower()
                if process_matches or title_matches:
                    candidates.append(window)
            except Exception:
                continue

        if not candidates:
            return None

        return self._select_best_window(candidates)

    def _select_best_window(self, windows: list[Any]) -> Any | None:
        if not windows:
            return None
        return max(windows, key=self._window_score)

    def _window_score(self, window: Any) -> int:
        title = ""
        try:
            title = (window.window_text() or "").lower()
        except Exception:
            pass

        area = 0
        try:
            rect = window.rectangle()
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        except Exception:
            pass

        score = area
        if "esezvizclient" in title:
            score += 5_000_000
        if title == "form":
            score -= 2_000_000
        if title in {"m", "default ime", "activemovie window"}:
            score -= 2_000_000
        if area == 0:
            score -= 1_000_000
        return score

    def snapshot(self, window: Any) -> DesktopWindowSnapshot:
        controls: list[DesktopControl] = []
        for control in window.descendants():
            try:
                text = control.window_text() or ""
                info = control.element_info
                controls.append(
                    DesktopControl(
                        text=text,
                        control_type=getattr(info, "control_type", "") or "",
                        automation_id=getattr(info, "automation_id", "") or "",
                    )
                )
            except Exception:
                continue
        try:
            title = window.window_text() or ""
        except Exception:
            title = ""
        metadata: dict[str, Any] = {
            "backend": self.window_backend,
            "automation_accessible": bool(controls) or self.window_backend == "uia",
        }
        try:
            rect = window.rectangle()
            metadata["window_rect"] = {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
            }
        except Exception:
            pass
        if self.window_backend != "uia" and not controls:
            metadata["accessibility_note"] = (
                "The ESEzvizClient window is visible, but its controls are not exposed "
                "to the current automation backend."
            )
        snapshot = DesktopWindowSnapshot(title=title, controls=controls, metadata=metadata)
        self._debug("desktop_backend.snapshot", snapshot_debug_summary(snapshot))
        return snapshot

    def click_first_text(self, window: Any, labels: list[str]) -> str | None:
        controls = list(window.descendants())
        self._debug(
            "desktop_backend.click_first_text.start",
            {"labels": labels, "control_count": len(controls)},
        )
        for label in labels:
            for control in controls:
                try:
                    text = control.window_text() or ""
                    if label and label == text.strip():
                        control.click_input()
                        self._debug(
                            "desktop_backend.click_first_text.matched",
                            {"label": label, "text": text, "match_type": "exact"},
                        )
                        return text or label
                except Exception:
                    continue
        for label in labels:
            for control in controls:
                try:
                    text = control.window_text() or ""
                    if label and label in text:
                        control.click_input()
                        self._debug(
                            "desktop_backend.click_first_text.matched",
                            {"label": label, "text": text, "match_type": "contains"},
                        )
                        return text or label
                except Exception:
                    continue
        self._debug("desktop_backend.click_first_text.not_found", {"labels": labels})
        return None

    def _debug(self, event: str, data: Any | None = None) -> None:
        if self.debug_logger is not None:
            self.debug_logger.log(event, data)

    def _window_debug_summary(self, window: Any) -> dict[str, Any]:
        data: dict[str, Any] = {"backend": self.window_backend}
        try:
            data["title"] = window.window_text() or ""
        except Exception:
            data["title"] = ""
        try:
            rect = window.rectangle()
            data["window_rect"] = {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
            }
        except Exception:
            pass
        return data


class DesktopEzvizClientTools:
    def __init__(
        self,
        *,
        exe_path: str = DEFAULT_EZVIZ_CLIENT_EXE,
        process_name: str = DEFAULT_PROCESS_NAME,
        backend: DesktopEzvizBackend | None = None,
        timeout: float = 20,
        debug_logger: DebugLogger | None = None,
    ) -> None:
        self.exe_path = exe_path
        self.process_name = process_name
        self.debug_logger = debug_logger
        self.backend = backend or PywinautoEzvizBackend(debug_logger=debug_logger)
        self.timeout = timeout
        self.window: Any | None = None

    def open_client(self) -> DesktopToolResult:
        self._debug("desktop_tools.open_client.start", {"exe_path": self.exe_path, "process_name": self.process_name})
        try:
            self.window = self.backend.connect_or_start(self.exe_path, self.process_name, self.timeout)
            snapshot = self.backend.snapshot(self.window)
            return self._result_from_snapshot("ok", "Opened ESEzvizClient.", snapshot)
        except Exception as exc:
            return self._result_from_exception(exc)

    def observe_window(self) -> DesktopToolResult:
        self._debug("desktop_tools.observe_window.start", {})
        try:
            window = self._ensure_window()
            snapshot = self.backend.snapshot(window)
            return self._result_from_snapshot("ok", "Observed ESEzvizClient window.", snapshot)
        except Exception as exc:
            return self._result_from_exception(exc)

    def check_login_or_blocking_modal(self) -> DesktopToolResult:
        self._debug("desktop_tools.check_login_or_blocking_modal.start", {})
        try:
            window = self._ensure_window()
            snapshot = self.backend.snapshot(window)
            blocker = self._blocking_hint(snapshot)
            if blocker:
                return self._result_from_snapshot(
                    "requires_user_action",
                    "ESEzvizClient needs manual login or confirmation before automation can continue.",
                    snapshot,
                    requires_user_action=True,
                    data={"blocking_hint": blocker},
                )
            return self._result_from_snapshot("ok", "No blocking login or modal was detected.", snapshot)
        except Exception as exc:
            return self._result_from_exception(exc)

    def open_video_monitor(self) -> DesktopToolResult:
        self._debug("desktop_tools.open_video_monitor.start", {})
        try:
            window = self._ensure_window()
            snapshot = self.backend.snapshot(window)
            blocker = self._blocking_hint(snapshot)
            if blocker:
                return self._result_from_snapshot(
                    "requires_user_action",
                    "Please complete login or close the blocking prompt in ESEzvizClient, then retry.",
                    snapshot,
                    requires_user_action=True,
                    data={"blocking_hint": blocker, "tool_name": "open_video_monitor"},
                )

            if snapshot.metadata.get("automation_accessible") is False:
                return self._result_from_snapshot(
                    "requires_user_action",
                    "ESEzvizClient is open, but this Agent cannot access its controls at the current permission level. "
                    "Please click the video monitor entry in the visible client window, "
                    "or restart AgentSurf/Codex as Administrator and retry.",
                    snapshot,
                    requires_user_action=True,
                    data={
                        "handoff_target": "\u89c6\u9891\u76d1\u63a7",
                        "reason": "window_controls_unavailable",
                        "tool_name": "open_video_monitor",
                        **snapshot.metadata,
                    },
                )

            page_hint = self._video_monitor_page_hint(snapshot)
            if page_hint:
                return self._result_from_snapshot(
                    "ok",
                    "ESEzvizClient is already showing the video monitor page.",
                    snapshot,
                    matched_control=page_hint,
                    data={"tool_name": "open_video_monitor", "page_confirmed": True},
                )

            matched = self.backend.click_first_text(window, VIDEO_MONITOR_LABELS)
            if matched:
                snapshot = self.backend.snapshot(window)
                page_confirmed = self._video_monitor_page_hint(snapshot) is not None
                if not page_confirmed:
                    return self._result_from_snapshot(
                        "not_confirmed",
                        "Clicked the ESEzvizClient video monitor entry, but could not confirm the video monitor page.",
                        snapshot,
                        matched_control=matched,
                        data={
                            "tool_name": "open_video_monitor",
                            "target_labels": VIDEO_MONITOR_LABELS,
                            "page_confirmed": False,
                        },
                    )
                return self._result_from_snapshot(
                    "ok",
                    "Opened ESEzvizClient video monitor.",
                    snapshot,
                    matched_control=matched,
                    data={
                        "tool_name": "open_video_monitor",
                        "target_labels": VIDEO_MONITOR_LABELS,
                        "page_confirmed": True,
                    },
                )

            return self._result_from_snapshot(
                "not_found",
                "Could not find a visible ESEzvizClient video monitor entry.",
                snapshot,
                data={"tool_name": "open_video_monitor", "target_labels": VIDEO_MONITOR_LABELS},
            )
        except Exception as exc:
            return self._result_from_exception(exc)

    def open_video_monitor_section(self, section: str) -> DesktopToolResult:
        self._debug("desktop_tools.open_video_monitor_section.start", {"section": section})
        normalized_section = normalize_video_monitor_section(section)
        self._debug(
            "desktop_tools.open_video_monitor_section.normalized",
            {"section": section, "normalized_section": normalized_section},
        )
        if normalized_section is None:
            result = DesktopToolResult(
                status="error",
                message=f"Unsupported ESEzvizClient video monitor section: {section}",
                data={
                    "tool_name": "open_video_monitor_section",
                    "section": section,
                    "supported_sections": sorted(VIDEO_MONITOR_SECTION_LABELS),
                },
            )
            self._debug("desktop_tools.result", result.to_dict())
            return result

        try:
            window = self._ensure_window()
            snapshot = self.backend.snapshot(window)
            blocker = self._blocking_hint(snapshot)
            if blocker:
                return self._result_from_snapshot(
                    "requires_user_action",
                    "Please complete login or close the blocking prompt in ESEzvizClient, then retry.",
                    snapshot,
                    requires_user_action=True,
                    data={
                        "blocking_hint": blocker,
                        "tool_name": "open_video_monitor_section",
                        "section": normalized_section,
                    },
                )

            if snapshot.metadata.get("automation_accessible") is False:
                return self._result_from_snapshot(
                    "requires_user_action",
                    "ESEzvizClient is open, but this Agent cannot access its controls at the current permission level. "
                    "Please click the requested video monitor section manually, "
                    "or restart AgentSurf/Codex as Administrator and retry.",
                    snapshot,
                    requires_user_action=True,
                    data={
                        "handoff_target": VIDEO_MONITOR_SECTION_NAMES[normalized_section],
                        "reason": "window_controls_unavailable",
                        "tool_name": "open_video_monitor_section",
                        "section": normalized_section,
                        **snapshot.metadata,
                    },
                )

            if self._video_monitor_page_hint(snapshot) or self._section_target_visible(snapshot, normalized_section):
                direct_result = self._click_video_monitor_section(window, normalized_section)
                if direct_result.status != "not_found":
                    return direct_result

            monitor_result = self.open_video_monitor()
            if monitor_result.status != "ok":
                monitor_result.data = {
                    **monitor_result.data,
                    "tool_name": "open_video_monitor_section",
                    "section": normalized_section,
                }
                return monitor_result

            return self._click_video_monitor_section(window, normalized_section)
        except Exception as exc:
            return self._result_from_exception(exc)

    def _ensure_window(self) -> Any:
        if self.window is None:
            self._debug(
                "desktop_tools.ensure_window.connect",
                {"exe_path": self.exe_path, "process_name": self.process_name, "timeout": self.timeout},
            )
            self.window = self.backend.connect_or_start(self.exe_path, self.process_name, self.timeout)
        return self.window

    def _debug(self, event: str, data: Any | None = None) -> None:
        if self.debug_logger is not None:
            self.debug_logger.log(event, data)

    def _blocking_hint(self, snapshot: DesktopWindowSnapshot) -> str | None:
        visible_text = snapshot.visible_text
        for hint in BLOCKING_TEXT_HINTS:
            if hint in visible_text:
                return hint
        for control in snapshot.controls:
            blob = control.searchable_text
            lowered = blob.lower()
            for hint in BLOCKING_INPUT_HINTS:
                if hint in blob or hint in lowered:
                    return hint
        return None

    def _video_monitor_page_hint(self, snapshot: DesktopWindowSnapshot) -> str | None:
        lines = {line.strip() for line in snapshot.visible_text.splitlines() if line.strip()}
        navigation_matches = [hint for hint in VIDEO_MONITOR_PAGE_HINTS if hint in lines]
        action_matches = [hint for hint in VIDEO_MONITOR_ACTION_HINTS if hint in lines]
        if len(navigation_matches) >= 2 or (navigation_matches and action_matches):
            return "\u89c6\u9891\u76d1\u63a7"
        return None

    def _video_monitor_section_hint(self, snapshot: DesktopWindowSnapshot, section: str) -> bool:
        if self._video_monitor_page_hint(snapshot) is None:
            return False
        return self._section_target_visible(snapshot, section)

    def _section_target_visible(self, snapshot: DesktopWindowSnapshot, section: str) -> bool:
        lines = {line.strip() for line in snapshot.visible_text.splitlines() if line.strip()}
        return any(label in lines for label in VIDEO_MONITOR_SECTION_LABELS[section])

    def _click_video_monitor_section(self, window: Any, section: str) -> DesktopToolResult:
        labels = VIDEO_MONITOR_SECTION_LABELS[section]
        self._debug("desktop_tools.click_video_monitor_section.start", {"section": section, "labels": labels})
        matched = self.backend.click_first_text(window, labels)
        if matched:
            snapshot = self.backend.snapshot(window)
            page_confirmed = self._video_monitor_page_hint(snapshot) is not None
            section_confirmed = self._video_monitor_section_hint(snapshot, section)
            if not (page_confirmed and section_confirmed):
                return self._result_from_snapshot(
                    "not_confirmed",
                    f"Clicked ESEzvizClient section {VIDEO_MONITOR_SECTION_NAMES[section]}, "
                    "but could not confirm the target video monitor section.",
                    snapshot,
                    matched_control=matched,
                    data={
                        "tool_name": "open_video_monitor_section",
                        "section": section,
                        "target_labels": labels,
                        "page_confirmed": page_confirmed,
                        "section_confirmed": section_confirmed,
                    },
                )
            return self._result_from_snapshot(
                "ok",
                f"Opened ESEzvizClient video monitor section: {VIDEO_MONITOR_SECTION_NAMES[section]}.",
                snapshot,
                matched_control=matched,
                data={
                    "tool_name": "open_video_monitor_section",
                    "section": section,
                    "target_labels": labels,
                    "page_confirmed": True,
                    "section_confirmed": True,
                },
            )

        snapshot = self.backend.snapshot(window)
        return self._result_from_snapshot(
            "not_found",
            f"Could not find visible ESEzvizClient section: {VIDEO_MONITOR_SECTION_NAMES[section]}.",
            snapshot,
            data={
                "tool_name": "open_video_monitor_section",
                "section": section,
                "target_labels": labels,
                "page_confirmed": self._video_monitor_page_hint(snapshot) is not None,
            },
        )

    def _result_from_snapshot(
        self,
        status: str,
        message: str,
        snapshot: DesktopWindowSnapshot,
        *,
        requires_user_action: bool = False,
        matched_control: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> DesktopToolResult:
        result = DesktopToolResult(
            status=status,
            message=message,
            requires_user_action=requires_user_action,
            window_title=snapshot.title,
            matched_control=matched_control,
            visible_text_excerpt=snapshot.visible_text[:1200],
            data=data or {},
        )
        self._debug(
            "desktop_tools.result",
            {
                **result.to_dict(),
                "snapshot": snapshot_debug_summary(snapshot),
            },
        )
        return result

    def _result_from_exception(self, exc: Exception) -> DesktopToolResult:
        message = str(exc)
        lowered = message.lower()
        requires_user_action = (
            "740" in message
            or "\u9700\u8981\u63d0\u5347" in message
            or "elevat" in lowered
            or "access is denied" in lowered
            or "\u62d2\u7edd\u8bbf\u95ee" in message
        )
        status = "requires_user_action" if requires_user_action else "error"
        handoff = (
            "ESEzvizClient needs to be opened or authorized manually, then retry this command."
            if requires_user_action
            else "ESEzvizClient desktop automation failed."
        )
        result = DesktopToolResult(
            status=status,
            message=handoff,
            requires_user_action=requires_user_action,
            data={"error": message, "exe_path": self.exe_path},
        )
        self._debug(
            "desktop_tools.exception",
            {"error_type": type(exc).__name__, "error": message, "result": result.to_dict()},
        )
        return result


def is_ezviz_desktop_request(prompt: str) -> bool:
    return detect_ezviz_desktop_tool(prompt) is not None


def normalize_video_monitor_section(value: str) -> str | None:
    lowered = value.lower()
    for section, labels in VIDEO_MONITOR_SECTION_LABELS.items():
        if lowered == section:
            return section
        if any(label in value for label in labels):
            return section
    return None


def detect_ezviz_desktop_tool(prompt: str) -> dict[str, Any] | None:
    lowered = prompt.lower()
    has_context = any(keyword in prompt for keyword in EZVIZ_DESKTOP_CONTEXT_HINTS) or any(
        keyword in lowered for keyword in EZVIZ_DESKTOP_CONTEXT_HINTS
    )
    has_action = any(keyword in prompt for keyword in DESKTOP_ACTION_HINTS) or any(
        keyword in lowered for keyword in DESKTOP_ACTION_HINTS
    )
    section = normalize_video_monitor_section(prompt)
    if section is not None and (has_context or has_action):
        return {"tool_name": "open_video_monitor_section", "section": section}
    if has_context:
        return {"tool_name": "open_video_monitor"}
    return None
