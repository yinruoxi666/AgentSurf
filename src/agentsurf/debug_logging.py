from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO


SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "token",
    "secret",
    "password",
    "captcha",
    "sms",
    "cookie",
)


def default_debug_log_path(prefix: str = "agentsurf-ezviz-desktop") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(".runtime") / "debug" / f"{prefix}-{timestamp}.jsonl"


class DebugLogger:
    def __init__(self, path: str | Path | None = None, *, stream: TextIO | None = None) -> None:
        self.path = Path(path) if path is not None else default_debug_log_path()
        self.stream = stream if stream is not None else sys.stderr
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, data: Any | None = None) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            "data": self.redact(data if data is not None else {}),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        print(line, file=self.stream, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def redact(self, value: Any) -> Any:
        return _redact(value)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)
