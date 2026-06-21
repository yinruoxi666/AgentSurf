from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.tools.desktop_ezviz import (
    DEFAULT_EZVIZ_CLIENT_EXE,
    DesktopControl,
    DesktopEzvizClientTools,
    DesktopToolResult,
    DesktopWindowSnapshot,
    PywinautoEzvizBackend,
    detect_ezviz_desktop_tool,
    is_ezviz_desktop_request,
)


class FakeDesktopBackend:
    def __init__(
        self,
        snapshot: DesktopWindowSnapshot | list[DesktopWindowSnapshot],
        *,
        matched_control: str | None = None,
    ) -> None:
        self.snapshots = snapshot if isinstance(snapshot, list) else [snapshot]
        self.snapshot_index = 0
        self.matched_control = matched_control
        self.connect_calls = 0
        self.clicked_labels: list[str] = []
        self.exe_paths: list[str] = []
        self.process_names: list[str] = []

    def connect_or_start(self, exe_path: str, process_name: str, timeout: float):
        self.connect_calls += 1
        self.exe_paths.append(exe_path)
        self.process_names.append(process_name)
        return {"window": "fake"}

    def snapshot(self, window) -> DesktopWindowSnapshot:
        snapshot = self.snapshots[min(self.snapshot_index, len(self.snapshots) - 1)]
        if self.snapshot_index < len(self.snapshots) - 1:
            self.snapshot_index += 1
        return snapshot

    def click_first_text(self, window, labels: list[str]) -> str | None:
        self.clicked_labels = labels
        return self.matched_control


class FailingDesktopBackend:
    def connect_or_start(self, exe_path: str, process_name: str, timeout: float):
        raise RuntimeError("CreateProcess failed: 740 request requires elevation")

    def snapshot(self, window) -> DesktopWindowSnapshot:
        return DesktopWindowSnapshot()

    def click_first_text(self, window, labels: list[str]) -> str | None:
        return None


class FakeDebugLogger:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def log(self, event: str, data=None) -> None:
        self.records.append({"event": event, "data": data if data is not None else {}})

    @property
    def events(self) -> list[str]:
        return [record["event"] for record in self.records]


class FakeRect:
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeWindow:
    def __init__(self, title: str, rect: FakeRect) -> None:
        self.title = title
        self.rect = rect

    def window_text(self) -> str:
        return self.title

    def rectangle(self) -> FakeRect:
        return self.rect


def video_monitor_page_snapshot() -> DesktopWindowSnapshot:
    return DesktopWindowSnapshot(
        title="ESEzvizClient",
        controls=[
            DesktopControl(text="\u9884\u89c8"),
            DesktopControl(text="\u56de\u653e"),
            DesktopControl(text="\u6d88\u606f"),
            DesktopControl(text="\u7ec8\u7aef\u914d\u7f6e"),
            DesktopControl(text="\u6279\u91cf\u6293\u56fe"),
            DesktopControl(text="\u5168\u5c4f\u663e\u793a"),
        ],
    )


def compact_video_monitor_page_snapshot() -> DesktopWindowSnapshot:
    return DesktopWindowSnapshot(
        title="ESEzvizClient",
        controls=[
            DesktopControl(text="\u9884\u89c8"),
            DesktopControl(text="\u56de\u653e"),
        ],
    )


class DesktopEzvizClientToolsTest(unittest.TestCase):
    def test_open_client_connects_or_starts_default_exe(self) -> None:
        backend = FakeDesktopBackend(DesktopWindowSnapshot(title="EZVIZ", controls=[]))
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_client()

        self.assertEqual(result.status, "ok")
        self.assertEqual(backend.exe_paths, [DEFAULT_EZVIZ_CLIENT_EXE])
        self.assertEqual(backend.connect_calls, 1)

    def test_open_video_monitor_clicks_visible_control(self) -> None:
        backend = FakeDesktopBackend(
            [
                DesktopWindowSnapshot(
                    title="EZVIZ",
                    controls=[DesktopControl(text="\u89c6\u9891\u76d1\u63a7", control_type="Button")],
                ),
                video_monitor_page_snapshot(),
            ],
            matched_control="\u89c6\u9891\u76d1\u63a7",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.matched_control, "\u89c6\u9891\u76d1\u63a7")
        self.assertIn("\u89c6\u9891\u76d1\u63a7", backend.clicked_labels)

    def test_login_prompt_requires_user_action(self) -> None:
        backend = FakeDesktopBackend(
            DesktopWindowSnapshot(
                title="EZVIZ",
                controls=[
                    DesktopControl(text="\u8bf7\u767b\u5f55"),
                    DesktopControl(text="", control_type="Edit", automation_id="password"),
                ],
            )
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "requires_user_action")
        self.assertTrue(result.requires_user_action)
        self.assertIn("blocking_hint", result.data)

    def test_qr_login_prompt_requires_user_action(self) -> None:
        backend = FakeDesktopBackend(
            DesktopWindowSnapshot(
                title="ESEzvizClient",
                controls=[
                    DesktopControl(text="\u8bf7\u4f7f\u7528\u8424\u77f3\u5546\u4e1a\u667a\u5c45app\u626b\u63cf\u767b\u5f55"),
                    DesktopControl(text="\u626b\u7801\u767b\u5f55"),
                    DesktopControl(text="\u65b0\u7528\u6237\u6ce8\u518c"),
                ],
            )
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "requires_user_action")
        self.assertTrue(result.requires_user_action)
        self.assertIn("blocking_hint", result.data)

    def test_elevation_error_requires_user_action(self) -> None:
        tools = DesktopEzvizClientTools(backend=FailingDesktopBackend())

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "requires_user_action")
        self.assertTrue(result.requires_user_action)
        self.assertIn("740", result.data["error"])

    def test_not_found_returns_visible_summary(self) -> None:
        backend = FakeDesktopBackend(
            DesktopWindowSnapshot(
                title="EZVIZ",
                controls=[DesktopControl(text="\u8bbe\u7f6e"), DesktopControl(text="\u6d88\u606f")],
            )
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "not_found")
        self.assertIn("\u8bbe\u7f6e", result.visible_text_excerpt)
        self.assertIn("target_labels", result.data)

    def test_inaccessible_window_requires_manual_handoff(self) -> None:
        backend = FakeDesktopBackend(
            DesktopWindowSnapshot(
                title="ESEzvizClient",
                controls=[],
                metadata={"automation_accessible": False, "backend": "win32"},
            )
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "requires_user_action")
        self.assertTrue(result.requires_user_action)
        self.assertEqual(result.data["handoff_target"], "\u89c6\u9891\u76d1\u63a7")
        self.assertEqual(result.data["reason"], "window_controls_unavailable")

    def test_existing_video_monitor_page_returns_ok(self) -> None:
        backend = FakeDesktopBackend(video_monitor_page_snapshot())
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.matched_control, "\u89c6\u9891\u76d1\u63a7")
        self.assertEqual(backend.clicked_labels, [])

    def test_compact_video_monitor_page_returns_ok(self) -> None:
        backend = FakeDesktopBackend(compact_video_monitor_page_snapshot())
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.matched_control, "\u89c6\u9891\u76d1\u63a7")
        self.assertEqual(backend.clicked_labels, [])

    def test_workbench_video_monitor_card_is_not_treated_as_open_page(self) -> None:
        backend = FakeDesktopBackend(
            [
                DesktopWindowSnapshot(
                    title="ESEzvizClient",
                    controls=[
                        DesktopControl(text="\u4f01\u4e1a\u7ba1\u7406"),
                        DesktopControl(text="\u529f\u80fd\u7ba1\u7406"),
                        DesktopControl(text="\u89c6\u9891\u76d1\u63a7"),
                        DesktopControl(text="\u89c6\u9891\u9884\u89c8\u3001\u56de\u653e\u3001\u544a\u8b66\u6d88\u606f\u67e5\u770b\u3001\u6210\u5458\u6743\u9650\u914d\u7f6e"),
                        DesktopControl(text="\u5de5\u4f5c\u53f0"),
                    ],
                ),
                video_monitor_page_snapshot(),
            ],
            matched_control="\u89c6\u9891\u76d1\u63a7",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.message, "Opened ESEzvizClient video monitor.")
        self.assertIn("\u89c6\u9891\u76d1\u63a7", backend.clicked_labels)

    def test_clicked_video_monitor_without_page_confirmation_returns_not_confirmed(self) -> None:
        backend = FakeDesktopBackend(
            [
                DesktopWindowSnapshot(
                    title="ESEzvizClient",
                    controls=[DesktopControl(text="\u89c6\u9891\u76d1\u63a7")],
                ),
                DesktopWindowSnapshot(
                    title="ESEzvizClient",
                    controls=[DesktopControl(text="\u4f01\u4e1a\u7ba1\u7406")],
                ),
            ],
            matched_control="\u89c6\u9891\u76d1\u63a7",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "not_confirmed")
        self.assertFalse(result.data["page_confirmed"])

    def test_open_video_monitor_section_clicks_target_nav(self) -> None:
        backend = FakeDesktopBackend(
            [video_monitor_page_snapshot(), video_monitor_page_snapshot(), video_monitor_page_snapshot()],
            matched_control="\u56de\u653e",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor_section("playback")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["tool_name"], "open_video_monitor_section")
        self.assertEqual(result.data["section"], "playback")
        self.assertTrue(result.data["page_confirmed"])
        self.assertTrue(result.data["section_confirmed"])
        self.assertIn("\u56de\u653e", backend.clicked_labels)

    def test_open_video_monitor_section_uses_existing_compact_page_nav(self) -> None:
        backend = FakeDesktopBackend(
            [compact_video_monitor_page_snapshot(), compact_video_monitor_page_snapshot()],
            matched_control="\u56de\u653e",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor_section("playback")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["section"], "playback")
        self.assertEqual(backend.connect_calls, 1)
        self.assertIn("\u56de\u653e", backend.clicked_labels)

    def test_open_video_monitor_section_can_click_visible_target_before_monitor_entry(self) -> None:
        backend = FakeDesktopBackend(
            [
                DesktopWindowSnapshot(
                    title="ESEzvizClient",
                    controls=[DesktopControl(text="\u56de\u653e")],
                ),
                compact_video_monitor_page_snapshot(),
            ],
            matched_control="\u56de\u653e",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor_section("playback")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["section"], "playback")
        self.assertIn("\u56de\u653e", backend.clicked_labels)

    def test_open_video_monitor_section_rejects_unknown_section(self) -> None:
        backend = FakeDesktopBackend(video_monitor_page_snapshot())
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor_section("unknown")

        self.assertEqual(result.status, "error")
        self.assertIn("supported_sections", result.data)

    def test_debug_logs_one_shot_tool_input_snapshot_and_result(self) -> None:
        debug = FakeDebugLogger()
        backend = FakeDesktopBackend(
            [compact_video_monitor_page_snapshot(), compact_video_monitor_page_snapshot()],
            matched_control="\u56de\u653e",
        )
        tools = DesktopEzvizClientTools(backend=backend, debug_logger=debug)

        result = tools.open_video_monitor_section("playback")

        self.assertEqual(result.status, "ok")
        self.assertIn("desktop_tools.open_video_monitor_section.start", debug.events)
        self.assertIn("desktop_tools.open_video_monitor_section.normalized", debug.events)
        self.assertIn("desktop_tools.result", debug.events)
        start_record = next(
            record for record in debug.records if record["event"] == "desktop_tools.open_video_monitor_section.start"
        )
        self.assertEqual(start_record["data"]["section"], "playback")
        result_record = next(record for record in debug.records if record["event"] == "desktop_tools.result")
        self.assertEqual(result_record["data"]["snapshot"]["control_count"], 2)
        self.assertIn("visible_text_excerpt", result_record["data"]["snapshot"])

    def test_backend_prefers_main_window_over_form_child(self) -> None:
        backend = object.__new__(PywinautoEzvizBackend)
        form = FakeWindow("Form", FakeRect(100, 100, 500, 300))
        main = FakeWindow("ESEzvizClient", FakeRect(0, 0, 1200, 800))

        selected = backend._select_best_window([form, main])

        self.assertIs(selected, main)

    def test_reuses_existing_window_after_open(self) -> None:
        backend = FakeDesktopBackend(
            [
                DesktopWindowSnapshot(
                    title="EZVIZ",
                    controls=[DesktopControl(text="\u89c6\u9891\u76d1\u63a7")],
                ),
                video_monitor_page_snapshot(),
                video_monitor_page_snapshot(),
            ],
            matched_control="\u89c6\u9891\u76d1\u63a7",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        tools.open_client()
        tools.open_video_monitor()

        self.assertEqual(backend.connect_calls, 1)

    def test_desktop_prompt_detection(self) -> None:
        self.assertTrue(is_ezviz_desktop_request("\u6253\u5f00\u8424\u77f3\u5de5\u4f5c\u5ba4\u8fdb\u5165\u89c6\u9891\u76d1\u63a7"))
        self.assertTrue(is_ezviz_desktop_request("open ESEzvizClient video monitor"))
        self.assertTrue(is_ezviz_desktop_request("\u6253\u5f00\u56de\u653e"))
        self.assertFalse(is_ezviz_desktop_request("open https://example.com"))

    def test_natural_language_detects_video_monitor_sections(self) -> None:
        cases = {
            "\u6253\u5f00\u9884\u89c8": "preview",
            "\u770b\u5b9e\u65f6\u753b\u9762": "preview",
            "\u6253\u5f00\u56de\u653e": "playback",
            "\u770b\u5f55\u50cf": "playback",
            "\u770b\u544a\u8b66\u6d88\u606f": "messages",
            "\u67e5\u770b\u62a5\u8b66": "messages",
            "\u8fdb\u5165\u7ec8\u7aef\u914d\u7f6e": "terminal_config",
            "\u914d\u7f6e\u6444\u50cf\u5934": "terminal_config",
        }
        for prompt, section in cases.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    detect_ezviz_desktop_tool(prompt),
                    {"tool_name": "open_video_monitor_section", "section": section},
                )


class FakeDesktopTools:
    def open_video_monitor(self) -> DesktopToolResult:
        return DesktopToolResult(
            status="ok",
            message="Opened fake video monitor.",
            window_title="EZVIZ",
            matched_control="\u89c6\u9891\u76d1\u63a7",
            visible_text_excerpt="\u89c6\u9891\u76d1\u63a7",
        )


if __name__ == "__main__":
    unittest.main()
