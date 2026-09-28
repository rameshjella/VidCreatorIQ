import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    client = TestClient(app)
    payload = {
        "prompt": "A peaceful cinematic piano piece inspired by rain at night.",
        "title": "Rain at Night",
        "mood": "Calm",
        "style": "Cinematic",
        "energy": "Low",
        "instrumentation": "Piano and warm strings",
        "duration_seconds": 4,
    }
    response = client.post("/music/generate", json=payload)
    print("status", response.status_code)
    print(response.text[:1500])


if __name__ == "__main__":
    main()

