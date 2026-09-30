"""Print the dependency payload exactly as the System Health widgets receive it."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def main() -> int:
    payload = TestClient(app).get("/health/dependencies").json()

    for key, info in payload["dependencies"].items():
        label = info.get("label", key)
        state = "ready" if info["ready"] else ("optional" if info.get("optional") else "error")
        print(f"{label}  [{state}]")
        print(f"   detail : {info['detail']}  ({len(info['detail'])} chars)")
        if info.get("hint"):
            print(f"   hint   : {info['hint']}")
        if info.get("resolved_path"):
            print(f"   path   : {info['resolved_path']}")
        if info.get("raw_error"):
            print(f"   raw    : {len(info['raw_error'])} chars, behind a disclosure")
        print()

    print(f"ready_for_generation : {payload['ready_for_generation']}")
    print(f"ready_for_cinematic  : {payload['ready_for_cinematic']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

