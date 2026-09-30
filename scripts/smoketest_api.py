"""Full-stack test: drive the real HTTP API and assert a playable movie comes back."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"

SCRIPT = """The lighthouse had stood for a hundred years, and it had never once gone dark.

Tonight the storm came in fast, swallowing the horizon whole.

Far below, a single fishing boat fought the swell, guided home by that one steady light."""


def main() -> int:
    print("1. Creating project...")
    project = requests.post(
        f"{BASE}/projects",
        json={"title": "API Smoke Test", "script_text": SCRIPT, "language": "en"},
        timeout=30,
    ).json()
    print(f"   project id={project['id']}")

    print("2. Starting render...")
    run = requests.post(
        f"{BASE}/projects/{project['id']}/run",
        json={"visual_mode": "basic"},
        timeout=30,
    ).json()
    job_id = run["job_id"]
    print(f"   job id={job_id}")

    print("3. Polling...")
    deadline = time.time() + 600
    last = ""
    while time.time() < deadline:
        job = requests.get(f"{BASE}/jobs/{job_id}", timeout=30).json()
        line = f"   [{job['progress'] * 100:5.1f}%] {job['stage']:<16} {job['message']}"
        if line != last:
            print(line)
            last = line
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(2)
    else:
        print("TIMEOUT")
        return 1

    if job["status"] != "completed":
        print(f"\nFAIL: {job['last_error']}")
        return 1

    print("\n4. Fetching artifacts...")
    art = requests.get(f"{BASE}/jobs/{job_id}/artifacts", timeout=30).json()

    checks = [
        ("final MP4", art["video_url"]),
        ("narration MP3", art["audio_url"]),
        ("subtitles SRT", art["subtitle_url"]),
        ("captions VTT", art["captions_vtt_url"]),
        ("poster JPG", art["poster_url"]),
    ]

    ok = True
    for label, url in checks:
        if not url:
            print(f"   MISSING  {label}")
            ok = False
            continue
        head = requests.head(url, timeout=30)
        size = int(head.headers.get("content-length", 0))
        status = "OK " if head.ok and size > 0 else "BAD"
        if status == "BAD":
            ok = False
        print(f"   {status}      {label:<16} {size / 1024:8.0f} KB  {head.headers.get('content-type', '')}")

    print(f"\n   duration : {art['duration_seconds']:.2f}s")
    print(f"   scenes   : {len(art['scenes'])}")
    for scene in art["scenes"]:
        print(
            f"     scene {scene['scene_index']}: {scene['duration_seconds']:.2f}s "
            f"voice={scene['tts_provider']} image={'Y' if scene['image_url'] else 'N'}"
        )

    print("\nPASS - full stack produced a real, downloadable movie." if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

