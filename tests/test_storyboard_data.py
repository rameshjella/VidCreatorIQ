"""Verify the Storyboard data path: project list + project-level artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def main() -> int:
    client = TestClient(app)
    ok = True

    print("GET /projects")
    response = client.get("/projects")
    if not response.is_success:
        print(f"  FAIL {response.status_code}")
        return 1
    projects = response.json()
    print(f"  OK   {len(projects)} projects")

    rendered = [p for p in projects if p["scenes"]]
    if not rendered:
        print("  (no projects with scenes yet - run scripts/smoketest_api.py first)")
        return 0

    # Prefer the newest project that actually produced a video, so the test
    # exercises the full media path rather than an old failed run.
    target = None
    for candidate in reversed(rendered):
        probe = client.get(f"/projects/{candidate['id']}/artifacts")
        if probe.is_success and probe.json().get("video_url"):
            target = candidate
            break
    if target is None:
        target = rendered[-1]
        print("  (no completed renders found; falling back to newest project with scenes)")
    print(f"\nGET /projects/{target['id']}/artifacts   ({target['title']!r})")
    response = client.get(f"/projects/{target['id']}/artifacts")
    if not response.is_success:
        print(f"  FAIL {response.status_code} {response.text[:200]}")
        return 1

    art = response.json()
    print(f"  OK   job={art['job_id']} status={art['status']} "
          f"duration={art['duration_seconds']:.2f}s scenes={len(art['scenes'])}")
    print(f"       video  : {art['video_url'] or '(none)'}")
    print(f"       audio  : {art['audio_url'] or '(none)'}")
    print(f"       poster : {art['poster_url'] or '(none)'}")

    for scene in art["scenes"]:
        has_text = bool(scene.get("script_chunk"))
        has_img = bool(scene.get("image_url"))
        if not has_text or not has_img:
            ok = False
        print(
            f"       scene {scene['scene_index']}: "
            f"{scene['duration_seconds']:.2f}s image={'Y' if has_img else 'N'} "
            f"text={'Y' if has_text else 'N'} voice={scene['tts_provider'] or '-'}"
        )

    # Every media URL the storyboard renders must actually resolve.
    print("\nFetching scene media")
    for scene in art["scenes"]:
        for key in ("image_url", "narration_url"):
            url = scene.get(key)
            if not url:
                continue
            path = url.split("/static", 1)[-1]
            head = client.head(f"/static{path}")
            status = "OK " if head.is_success else "BAD"
            if not head.is_success:
                ok = False
            print(f"  {status}  scene {scene['scene_index']} {key}")

    print("\nPASS - storyboard has everything it needs." if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

