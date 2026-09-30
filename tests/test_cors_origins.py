"""CORS preflight regression test (in-process, no server required).

Reproduces the production bug: the launcher serves the UI on port 8501, but
``UI_ALLOWED_ORIGINS`` in .env only listed 5173. Because the configured value
*replaced* the defaults, every preflight from 8501 returned 400 and the UI
could not create projects.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ORIGINS = [
    "http://127.0.0.1:8501",
    "http://localhost:8501",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:3000",
]

ENDPOINTS = [("POST", "/projects"), ("POST", "/tts/preview"), ("PATCH", "/projects/1/scenes")]


def run_case(label: str, env_value: str | None) -> bool:
    # Rebuild the app fresh so the middleware picks up this env value.
    for module in [m for m in list(sys.modules) if m.startswith("app.")]:
        del sys.modules[module]
    if "app" in sys.modules:
        del sys.modules["app"]

    if env_value is None:
        os.environ.pop("UI_ALLOWED_ORIGINS", None)
    else:
        os.environ["UI_ALLOWED_ORIGINS"] = env_value

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    print(f"\n{label}")
    print(f"  UI_ALLOWED_ORIGINS = {env_value!r}")

    ok = True
    for origin in ORIGINS:
        for method, path in ENDPOINTS:
            response = client.options(
                path,
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            allowed = response.headers.get("access-control-allow-origin", "")
            passed = response.status_code == 200 and bool(allowed)
            ok = ok and passed
            print(
                f"    {'OK  ' if passed else 'FAIL'} {response.status_code} "
                f"{method:<6} {path:<24} origin={origin}"
            )
    return ok


def main() -> int:
    results = [
        # The exact value that was breaking the launcher UI.
        run_case("Case 1: only Vite's port configured (the original bug)",
                 "http://127.0.0.1:5173,http://localhost:5173"),
        run_case("Case 2: nothing configured", None),
        run_case("Case 3: current .env value",
                 "http://127.0.0.1:8501,http://localhost:8501,"
                 "http://127.0.0.1:5173,http://localhost:5173"),
    ]

    if all(results):
        print("\nPASS - every UI origin is accepted in all configurations.")
        return 0
    print("\nFAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

