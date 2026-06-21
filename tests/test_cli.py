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
                "--observe",
            ]
        )

        self.assertEqual(args.command, "ezviz-desktop")
        self.assertTrue(args.debug)
        self.assertEqual(args.debug_log_path, ".runtime/debug/custom.jsonl")

    def test_ezviz_desktop_agent_debug_flags_parse(self) -> None:
        args = build_parser().parse_args(
            [
                "ezviz-desktop-agent",
                "--debug",
                "--debug-log-path",
                ".runtime/debug/agent.jsonl",
                "--verbose",
            ]
        )

        self.assertEqual(args.command, "ezviz-desktop-agent")
        self.assertTrue(args.debug)
        self.assertEqual(args.debug_log_path, ".runtime/debug/agent.jsonl")
        self.assertTrue(args.verbose)


if __name__ == "__main__":
    unittest.main()
