from __future__ import annotations

import json
from pathlib import Path

from src.api import app


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "n8n-migration" / "openapi.json"


def main() -> int:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(SNAPSHOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
