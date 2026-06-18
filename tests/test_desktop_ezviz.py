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
    is_ezviz_desktop_request,
)


class FakeDesktopBackend:
    def __init__(
        self,
        snapshot: DesktopWindowSnapshot,
        *,
        matched_control: str | None = None,
    ) -> None:
        self.snapshot_value = snapshot
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
        return self.snapshot_value

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
            DesktopWindowSnapshot(
                title="EZVIZ",
                controls=[DesktopControl(text="\u89c6\u9891\u76d1\u63a7", control_type="Button")],
            ),
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
        self.assertIn("tried_labels", result.data)

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
        backend = FakeDesktopBackend(
            DesktopWindowSnapshot(
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
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.matched_control, "\u89c6\u9891\u76d1\u63a7")
        self.assertEqual(backend.clicked_labels, [])

    def test_workbench_video_monitor_card_is_not_treated_as_open_page(self) -> None:
        backend = FakeDesktopBackend(
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
            matched_control="\u89c6\u9891\u76d1\u63a7",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        result = tools.open_video_monitor()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.message, "Opened ESEzvizClient video monitor.")
        self.assertIn("\u89c6\u9891\u76d1\u63a7", backend.clicked_labels)

    def test_backend_prefers_main_window_over_form_child(self) -> None:
        backend = object.__new__(PywinautoEzvizBackend)
        form = FakeWindow("Form", FakeRect(100, 100, 500, 300))
        main = FakeWindow("ESEzvizClient", FakeRect(0, 0, 1200, 800))

        selected = backend._select_best_window([form, main])

        self.assertIs(selected, main)

    def test_reuses_existing_window_after_open(self) -> None:
        backend = FakeDesktopBackend(
            DesktopWindowSnapshot(
                title="EZVIZ",
                controls=[DesktopControl(text="\u89c6\u9891\u76d1\u63a7")],
            ),
            matched_control="\u89c6\u9891\u76d1\u63a7",
        )
        tools = DesktopEzvizClientTools(backend=backend)

        tools.open_client()
        tools.open_video_monitor()

        self.assertEqual(backend.connect_calls, 1)

    def test_desktop_prompt_detection(self) -> None:
        self.assertTrue(is_ezviz_desktop_request("\u6253\u5f00\u8424\u77f3\u5de5\u4f5c\u5ba4\u8fdb\u5165\u89c6\u9891\u76d1\u63a7"))
        self.assertTrue(is_ezviz_desktop_request("open ESEzvizClient video monitor"))
        self.assertFalse(is_ezviz_desktop_request("open https://example.com"))


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
