"""End-to-end smoke test: a real, playable MP4 must come out of the pipeline."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services import ffmpeg_runner as ff  # noqa: E402
from app.services.image_service import ImageService  # noqa: E402
from app.services.narration_service import TTSService  # noqa: E402
from app.services.render_service import RenderService  # noqa: E402
from app.services.subtitle_service import SubtitleService  # noqa: E402

SCENES = [
    ("A lone lighthouse cuts through the storm, its beam sweeping the black water.",
     "cinematic lighthouse in a storm, dramatic lighting"),
    ("Far below, a small boat fights the waves, guided home by that single light.",
     "small fishing boat on stormy sea at night"),
]


def main() -> int:
    root = Path(settings.workspace_dir) / "smoketest"
    root.mkdir(parents=True, exist_ok=True)

    print(f"ffmpeg : {ff.ffmpeg_bin()}")
    print(f"ffprobe: {ff.ffprobe_bin()}")

    images = ImageService(root / "images")
    tts = TTSService(root / "audio")
    subs = SubtitleService(root / "subs")
    render = RenderService(root / "video")
    render.ensure_ffmpeg_available()

    clips, audios, texts, durations = [], [], [], []

    for i, (narration_text, prompt) in enumerate(SCENES, start=1):
        print(f"\n--- Scene {i} ---")
        result = tts.synthesize_detailed(narration_text, i)
        print(f"  narration : {result.path.name} ({result.duration:.2f}s via {result.provider})")

        duration = max(settings.render_min_scene_seconds, result.duration)
        img = images.generate(prompt, i)
        print(f"  image     : {img.name}")

        clip = render.image_to_clip(img, duration, i)
        info = ff.probe(clip)
        print(f"  clip      : {clip.name} ({info.duration:.2f}s {info.width}x{info.height})")

        clips.append(clip)
        audios.append(result.path)
        texts.append(narration_text)
        durations.append(duration)

    print("\n--- Assembly ---")
    video = render.concat_videos(clips)
    print(f"  picture   : {video.name} ({ff.probe_duration(video):.2f}s)")

    audio = render.concat_audio(audios)
    mp3 = render.to_mp3(audio)
    print(f"  narration : {mp3.name} ({ff.probe_duration(mp3):.2f}s)")

    srt = subs.merge_scene_subtitles(texts, durations)
    print(f"  captions  : {srt.name}")

    final = render.mux(video, audio, srt)
    info = ff.validate_output(final, expect_video=True, expect_audio=True)
    poster = render.extract_poster(final)

    print("\n=== RESULT ===")
    print(f"  {final}")
    print(f"  {info.duration:.2f}s  {info.width}x{info.height}  "
          f"video={info.has_video} audio={info.has_audio}")
    print(f"  size: {final.stat().st_size / 1024:.0f} KB")
    print(f"  poster: {poster.name}")
    print("\nPASS - a real, playable movie was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

