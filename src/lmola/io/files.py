from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid


def create_run_dir(base: str = "outputs") -> Path:
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    path = Path(base) / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path
