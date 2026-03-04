from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuditLogger:
    log_path: Path

    def __post_init__(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, payload: dict) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.log_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
