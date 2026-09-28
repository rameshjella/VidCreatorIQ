import sys
import time
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
    print("submit_status", response.status_code)
    created = response.json()
    generation_id = created.get("id")
    print("generation_id", generation_id)

    if not generation_id:
        print(str(created)[:1500])
        return

    for _ in range(120):
        poll = client.get(f"/music/generations/{generation_id}")
        payload_out = poll.json()
        status = payload_out.get("status")
        print("poll_status", status)
        if status in {"completed", "failed"}:
            print(str(payload_out)[:1500])
            return
        time.sleep(1.5)

    print("Timed out waiting for generation completion")


if __name__ == "__main__":
    main()

