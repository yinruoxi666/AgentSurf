from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentsurf.debug_logging import DebugLogger


class DebugLoggerTest(unittest.TestCase):
    def test_writes_jsonl_to_stream_and_file_with_redaction(self) -> None:
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "debug.jsonl"
            logger = DebugLogger(log_path, stream=stream)

            logger.log(
                "test.event",
                {
                    "api_key": "sk-secret",
                    "nested": {"password": "123456", "safe": "ok"},
                    "items": [{"token": "abc"}, {"value": "visible"}],
                },
            )

            file_record = json.loads(log_path.read_text(encoding="utf-8").strip())
            stream_record = json.loads(stream.getvalue().strip())

        self.assertEqual(file_record, stream_record)
        self.assertEqual(file_record["event"], "test.event")
        self.assertEqual(file_record["data"]["api_key"], "<redacted>")
        self.assertEqual(file_record["data"]["nested"]["password"], "<redacted>")
        self.assertEqual(file_record["data"]["nested"]["safe"], "ok")
        self.assertEqual(file_record["data"]["items"][0]["token"], "<redacted>")
        self.assertEqual(file_record["data"]["items"][1]["value"], "visible")


if __name__ == "__main__":
    unittest.main()
