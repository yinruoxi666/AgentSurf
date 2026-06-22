from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.cli import build_parser


class CliParserTest(unittest.TestCase):
    def test_ezviz_desktop_debug_flags_parse(self) -> None:
        args = build_parser().parse_args(
            [
                "ezviz-desktop",
                "--debug",
                "--debug-log-path",
                ".runtime/debug/custom.jsonl",
                "--visual-config-path",
                "config/ezviz_desktop/custom.json",
                "--observe",
            ]
        )

        self.assertEqual(args.command, "ezviz-desktop")
        self.assertTrue(args.debug)
        self.assertEqual(args.debug_log_path, ".runtime/debug/custom.jsonl")
        self.assertEqual(args.visual_config_path, "config/ezviz_desktop/custom.json")

    def test_ezviz_desktop_agent_debug_flags_parse(self) -> None:
        args = build_parser().parse_args(
            [
                "ezviz-desktop-agent",
                "--debug",
                "--debug-log-path",
                ".runtime/debug/agent.jsonl",
                "--visual-config-path",
                "config/ezviz_desktop/agent.json",
                "--verbose",
            ]
        )

        self.assertEqual(args.command, "ezviz-desktop-agent")
        self.assertTrue(args.debug)
        self.assertEqual(args.debug_log_path, ".runtime/debug/agent.jsonl")
        self.assertEqual(args.visual_config_path, "config/ezviz_desktop/agent.json")
        self.assertTrue(args.verbose)


if __name__ == "__main__":
    unittest.main()
