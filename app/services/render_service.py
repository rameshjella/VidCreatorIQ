"""Video rendering service.

Design notes
------------
The previous implementation stream-copied (``-c copy``) heterogeneous clips
during concatenation, which silently produced corrupt or zero-length MP4s.
Every clip is now normalised to a single canonical profile (size, fps, pixel
format, timebase, SAR and a silent audio track) before it ever reaches the
concatenation stage, and every produced file is validated with ffprobe.
"""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import settings
from app.services import ffmpeg_runner as ff
from app.services.ffmpeg_runner import FFmpegError
from app.services.comfyui_workflow_client import ComfyUIWorkflowClient
from app.services.sfx_semantic_service import SFXSemanticMatcher


def _escape_filter_path(path: Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filtergraph.

    Windows paths contain a drive colon which ffmpeg treats as an option
    separator, so it must be escaped as ``C\\:/...``.
    """
    text = Path(path).resolve().as_posix()
    text = text.replace("\\", "/")
    text = text.replace(":", r"\:")
    text = text.replace("'", r"\'")
    text = text.replace("[", r"\[").replace("]", r"\]")
    return text


class RenderService:
    def __init__(
        self,
        out_dir: Path,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        burn_subtitles: bool | None = None,
    ):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.width = int(width or settings.render_width)
        self.height = int(height or settings.render_height)
        self.fps = int(fps or settings.render_fps)
        self.sample_rate = int(settings.render_audio_sample_rate)
        self.burn_subtitles = settings.render_burn_subtitles if burn_subtitles is None else bool(burn_subtitles)
        self.ffmpeg_cmd = ff.ffmpeg_bin()
        self._comfy_video_temporal_ready: bool | None = None

    # ------------------------------------------------------------------
    # Dependency checks
    # ------------------------------------------------------------------
    def ensure_ffmpeg_available(self) -> None:
        """Validate that both ffmpeg and ffprobe are usable before rendering."""
        ff.ffmpeg_bin()
        ff.ffprobe_bin()

    # ------------------------------------------------------------------
    # Encoding profile
    # ------------------------------------------------------------------
    def _video_encode_args(self) -> list[str]:
        return [
            "-c:v", "libx264",
            "-preset", settings.render_preset,
            "-crf", str(settings.render_crf),
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            "-g", str(self.fps * 2),
            "-video_track_timescale", "90000",
            "-movflags", "+faststart",
        ]

    def _audio_encode_args(self) -> list[str]:
        return [
            "-c:a", "aac",
            "-b:a", settings.render_audio_bitrate,
            "-ar", str(self.sample_rate),
            "-ac", "2",
        ]

    def _fit_filter(self) -> str:
        w, h = self.width, self.height
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={self.fps},format=yuv420p"
        )

    def _ken_burns_filter(self, duration: float) -> str:
        """Slow zoom so still images feel like real cinematography."""
        w, h = self.width, self.height
        total_frames = max(2, int(round(duration * self.fps)))
        zoom_span = 0.16
        per_frame = zoom_span / total_frames
        # Supersample first so the zoom stays sharp, then zoompan one frame at a time.
        return (
            f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
            f"crop={w * 2}:{h * 2},"
            f"zoompan=z='min(1+{per_frame:.8f}*on\\,{1 + zoom_span:.4f})'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={w}x{h}:fps={self.fps},"
            f"setsar=1,format=yuv420p"
        )

    # ------------------------------------------------------------------
    # Scene clips
    # ------------------------------------------------------------------
    def image_to_clip(self, image_path: Path, duration: float, scene_index: int) -> Path:
        """Turn a still image into a normalised clip with a silent audio track."""
        duration = max(float(settings.render_min_scene_seconds), float(duration or 0))
        clip_path = self.out_dir / f"scene_{scene_index:03d}.mp4"

        video_filter = (
            self._ken_burns_filter(duration) if settings.render_ken_burns else self._fit_filter()
        )

        cmd = [
            self.ffmpeg_cmd, "-y",
            "-loop", "1", "-framerate", str(self.fps), "-i", str(image_path),
            # A silent stereo bed guarantees every clip has an audio stream, so the
            # concat stage never has to reconcile mismatched stream layouts.
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={self.sample_rate}",
            "-t", f"{duration:.3f}",
            "-vf", video_filter,
            *self._video_encode_args(),
            *self._audio_encode_args(),
            "-shortest",
            str(clip_path),
        ]
        ff.run(cmd)
        ff.validate_output(clip_path, expect_video=True, expect_audio=True)
        return clip_path

    def normalize_clip(self, clip_path: Path, scene_index: int, duration: float | None = None) -> Path:
        """Re-encode an externally produced clip into the canonical profile."""
        clip_path = Path(clip_path)
        info = ff.probe(clip_path)
        normalized = self.out_dir / f"scene_{scene_index:03d}_norm.mp4"

        cmd = [self.ffmpeg_cmd, "-y", "-i", str(clip_path)]
        if not info.has_audio:
            cmd += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={self.sample_rate}"]

        cmd += ["-vf", self._fit_filter()]
        if duration and duration > 0:
            cmd += ["-t", f"{float(duration):.3f}"]
        cmd += [*self._video_encode_args(), *self._audio_encode_args()]
        if not info.has_audio:
            cmd += ["-shortest"]
        cmd += [str(normalized)]

        ff.run(cmd)
        ff.validate_output(normalized, expect_video=True, expect_audio=True)

        final_path = self.out_dir / f"scene_{scene_index:03d}.mp4"
        normalized.replace(final_path)
        return final_path

    def generate_clip_with_comfyui(
        self,
        prompt: str,
        scene_index: int,
        duration: float | None = None,
        loras: list[dict] | None = None,
    ) -> Path:
        if not self._is_temporal_video_workflow(Path(settings.comfyui_animatediff_workflow)):
            raise FFmpegError(
                "ComfyUI cinematic workflow has no temporal motion nodes; "
                "falling back to cinematic still-image motion clips."
            )

        raw_path = self.out_dir / f"scene_{scene_index:03d}_raw.mp4"
        client = ComfyUIWorkflowClient(settings.comfyui_url)
        history = client.run_workflow(
            workflow_path=Path(settings.comfyui_animatediff_workflow),
            prompt=prompt,
            scene_index=scene_index,
            checkpoint=settings.comfyui_ad_checkpoint_name,
            node_map={
                "prompt": settings.comfyui_ad_prompt_node_id,
                "seed": settings.comfyui_ad_seed_node_id,
                "checkpoint": settings.comfyui_ad_checkpoint_node_id,
                "lora": settings.comfyui_ad_lora_node_ids,
                "output": settings.comfyui_ad_output_node_id,
            },
            loras=loras or [],
        )
        client.download_first_video(history, raw_path)
        return self.normalize_clip(raw_path, scene_index, duration)

    def _is_temporal_video_workflow(self, workflow_path: Path) -> bool:
        """Best-effort check that the configured ComfyUI graph can render moving video.

        The default fallback graph may emit a tiny handful of frames (or effectively
        stills) while taking several minutes. Detect this early and let the pipeline
        use the fast cinematic image-motion path instead.
        """
        if self._comfy_video_temporal_ready is not None:
            return self._comfy_video_temporal_ready

        try:
            payload = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
        except Exception:
            self._comfy_video_temporal_ready = False
            return False

        markers = ("animatediff", "ade_", "motionmodel", "svd", "videolinear")
        class_types = [
            str((node or {}).get("class_type", "")).lower()
            for node in payload.values()
            if isinstance(node, dict)
        ]
        self._comfy_video_temporal_ready = any(any(marker in ct for marker in markers) for ct in class_types)
        return self._comfy_video_temporal_ready

    # ------------------------------------------------------------------
    # Concatenation
    # ------------------------------------------------------------------
    @staticmethod
    def _concat_line(path: Path) -> str:
        absolute = Path(path).resolve().as_posix()
        escaped = absolute.replace("'", "'\\''")
        return f"file '{escaped}'"

    def _write_concat_list(self, entries: list[Path], list_file: Path) -> None:
        list_file.write_text("\n".join(self._concat_line(e) for e in entries) + "\n", encoding="utf-8")

    def concat_videos(self, clips: list[Path], output_name: str = "movie_silent.mp4") -> Path:
        """Join normalised clips, optionally crossfading between scenes."""
        if not clips:
            raise FFmpegError("No scene clips were produced, cannot assemble the movie.")

        for clip in clips:
            ff.validate_output(Path(clip), expect_video=True)

        out_path = self.out_dir / output_name

        transition = (settings.render_transition or "none").strip().lower()
        if len(clips) > 1 and transition not in ("", "none") and settings.render_transition_seconds > 0:
            try:
                return self._concat_with_transitions([Path(c) for c in clips], out_path, transition)
            except FFmpegError:
                # Crossfading is a nicety; never let it block delivery of the movie.
                pass

        list_file = self.out_dir / "concat.txt"
        self._write_concat_list([Path(c) for c in clips], list_file)
        cmd = [
            self.ffmpeg_cmd, "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            # Re-encode rather than stream-copy: copying across clips with even
            # slightly different timebases yields unplayable output.
            *self._video_encode_args(),
            *self._audio_encode_args(),
            str(out_path),
        ]
        ff.run(cmd)
        ff.validate_output(out_path, expect_video=True)
        return out_path

    def _concat_with_transitions(self, clips: list[Path], out_path: Path, transition: str) -> Path:
        fade = float(settings.render_transition_seconds)
        durations = [ff.probe_duration(c) for c in clips]
        if any(d <= fade * 2 for d in durations):
            raise FFmpegError("Clips are too short for transitions")

        cmd = [self.ffmpeg_cmd, "-y"]
        for clip in clips:
            cmd += ["-i", str(clip)]

        filters: list[str] = []
        for i in range(len(clips)):
            filters.append(f"[{i}:v]setpts=PTS-STARTPTS,fps={self.fps},setsar=1[v{i}]")

        current = "v0"
        offset = durations[0] - fade
        for i in range(1, len(clips)):
            label = f"vx{i}"
            filters.append(
                f"[{current}][v{i}]xfade=transition={transition}:duration={fade}:offset={offset:.3f}[{label}]"
            )
            current = label
            offset += durations[i] - fade

        total = sum(durations) - fade * (len(clips) - 1)
        filters.append(
            f"anullsrc=channel_layout=stereo:sample_rate={self.sample_rate}:d={total:.3f}[aout]"
        )

        cmd += [
            "-filter_complex", ";".join(filters),
            "-map", f"[{current}]", "-map", "[aout]",
            *self._video_encode_args(),
            *self._audio_encode_args(),
            "-shortest",
            str(out_path),
        ]
        ff.run(cmd)
        ff.validate_output(out_path, expect_video=True)
        return out_path

    def concat_audio(self, audios: list[Path], output_name: str = "movie.wav") -> Path:
        """Join narration tracks, resampling every input to a common format."""
        if not audios:
            raise FFmpegError("No narration audio was produced.")

        out_path = self.out_dir / output_name
        cmd = [self.ffmpeg_cmd, "-y"]
        for audio in audios:
            cmd += ["-i", str(audio)]

        parts = []
        for i in range(len(audios)):
            parts.append(
                f"[{i}:a]aformat=sample_fmts=fltp:sample_rates={self.sample_rate}:channel_layouts=stereo[a{i}]"
            )
        joined = "".join(f"[a{i}]" for i in range(len(audios)))
        parts.append(f"{joined}concat=n={len(audios)}:v=0:a=1[aout]")

        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", "[aout]",
            "-c:a", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", "2",
            str(out_path),
        ]
        ff.run(cmd)
        ff.validate_output(out_path, expect_video=False, expect_audio=True)
        return out_path

    def auto_sfx_track(self, scene_texts: list[str], scene_durations: list[float], output_name: str = "sfx.wav") -> Path | None:
        """Create an SFX bed using semantic retrieval from the local SFX library."""
        sfx_dir = Path(settings.sfx_library_dir)
        if not sfx_dir.exists():
            return None

        matcher = SFXSemanticMatcher(dims=256)
        assets = matcher.index_library(sfx_dir)
        if not assets:
            return None

        segments: list[Path] = []
        seg_dir = self.out_dir / "sfx_segments"
        seg_dir.mkdir(parents=True, exist_ok=True)

        for i, (text, duration) in enumerate(zip(scene_texts, scene_durations), start=1):
            best = matcher.search(text or "", top_k=1)
            chosen: Path | None = best[0].path if best else None

            seg = seg_dir / f"sfx_{i:03d}.wav"
            seg_len = max(0.2, float(duration))
            if chosen:
                ff.run(
                    [
                        self.ffmpeg_cmd,
                        "-y",
                        "-stream_loop",
                        "-1",
                        "-i",
                        str(chosen),
                        "-t",
                        f"{seg_len:.3f}",
                        "-af",
                        (
                            f"aformat=sample_rates={self.sample_rate}:channel_layouts=stereo,"
                            f"volume={settings.render_sfx_gain_db}dB"
                        ),
                        "-c:a",
                        "pcm_s16le",
                        "-ar",
                        str(self.sample_rate),
                        "-ac",
                        "2",
                        str(seg),
                    ]
                )
            else:
                ff.run(
                    [
                        self.ffmpeg_cmd,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"anullsrc=channel_layout=stereo:sample_rate={self.sample_rate}",
                        "-t",
                        f"{seg_len:.3f}",
                        "-c:a",
                        "pcm_s16le",
                        "-ar",
                        str(self.sample_rate),
                        "-ac",
                        "2",
                        str(seg),
                    ]
                )
            segments.append(seg)

        if not segments:
            return None
        return self.concat_audio(segments, output_name=output_name)

    def to_mp3(self, source: Path, output_name: str = "narration.mp3") -> Path:
        """Export a broadcast-ready MP3 of the full narration mix."""
        out_path = self.out_dir / output_name
        cmd = [
            self.ffmpeg_cmd, "-y",
            "-i", str(source),
            "-af", f"loudnorm=I={settings.render_loudness_lufs}:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame",
            "-b:a", settings.tts_mp3_bitrate,
            "-ar", str(self.sample_rate),
            "-ac", "2",
            str(out_path),
        ]
        ff.run(cmd)
        ff.validate_output(out_path, expect_video=False, expect_audio=True)
        return out_path

    def export_stems(
        self,
        narration_path: Path,
        music_path: Path | None = None,
        sfx_path: Path | None = None,
        output_dir_name: str = "stems",
    ) -> dict[str, Path]:
        """Export WAV stems + a small manifest for external NLE finishing."""
        stems_dir = self.out_dir / output_dir_name
        stems_dir.mkdir(parents=True, exist_ok=True)

        narration_stem = stems_dir / "narration.wav"
        ff.run(
            [
                self.ffmpeg_cmd,
                "-y",
                "-i",
                str(narration_path),
                "-c:a",
                "pcm_s16le",
                "-ar",
                str(self.sample_rate),
                "-ac",
                "2",
                str(narration_stem),
            ]
        )
        ff.validate_output(narration_stem, expect_video=False, expect_audio=True)

        tracks: dict[str, Path] = {"narration": narration_stem}
        if music_path and Path(music_path).exists():
            music_stem = stems_dir / "music.wav"
            # Loop and trim so the DAW/NLE timeline stays aligned with narration.
            ff.run(
                [
                    self.ffmpeg_cmd,
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(music_path),
                    "-af",
                    (
                        f"aformat=sample_rates={self.sample_rate}:channel_layouts=stereo,"
                        f"volume={settings.render_music_bed_gain_db}dB"
                    ),
                    "-map",
                    "0:a",
                    "-t",
                    f"{ff.probe_duration(Path(narration_path)):.3f}",
                    "-c:a",
                    "pcm_s16le",
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    "2",
                    str(music_stem),
                ]
            )
            ff.validate_output(music_stem, expect_video=False, expect_audio=True)
            tracks["music"] = music_stem

        if sfx_path and Path(sfx_path).exists():
            sfx_stem = stems_dir / "sfx.wav"
            ff.run(
                [
                    self.ffmpeg_cmd,
                    "-y",
                    "-i",
                    str(sfx_path),
                    "-c:a",
                    "pcm_s16le",
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    "2",
                    str(sfx_stem),
                ]
            )
            ff.validate_output(sfx_stem, expect_video=False, expect_audio=True)
            tracks["sfx"] = sfx_stem

        manifest = stems_dir / "stems_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "sample_rate": self.sample_rate,
                    "channels": 2,
                    "tracks": {name: path.name for name, path in tracks.items()},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        tracks["manifest"] = manifest
        return tracks

    def export_stems_zip(self, tracks: dict[str, Path], output_name: str = "stems_package.zip") -> Path:
        """Package stem assets into a single ZIP for external NLE workflows."""
        stems_dir = self.out_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)
        zip_path = stems_dir / output_name
        with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as bundle:
            for _, path in tracks.items():
                candidate = Path(path)
                if not candidate.exists():
                    continue
                bundle.write(candidate, arcname=f"stems/{candidate.name}")
        return zip_path

    # ------------------------------------------------------------------
    # Final mux
    # ------------------------------------------------------------------
    def mux(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path | None = None,
        output_name: str = "final_movie.mp4",
        music_path: Path | None = None,
        sfx_path: Path | None = None,
    ) -> Path:
        """Produce the deliverable MP4: burned subtitles, mixed + normalised audio."""
        out_path = self.out_dir / output_name

        cmd = [self.ffmpeg_cmd, "-y", "-i", str(video_path), "-i", str(audio_path)]
        music_index = None
        sfx_index = None
        if music_path and Path(music_path).exists():
            cmd += ["-i", str(music_path)]
            music_index = 2
        if sfx_path and Path(sfx_path).exists():
            cmd += ["-i", str(sfx_path)]
            sfx_index = 3 if music_index is not None else 2

        filters: list[str] = []

        if self.burn_subtitles and subtitle_path and Path(subtitle_path).exists():
            style = (
                "FontName=Arial,Fontsize=22,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H90000000,BorderStyle=3,Outline=1,Shadow=0,"
                "MarginV=48,Alignment=2"
            )
            filters.append(
                f"[0:v]subtitles='{_escape_filter_path(Path(subtitle_path))}'"
                f":force_style='{style}'[vout]"
            )
        else:
            filters.append("[0:v]null[vout]")
        video_map = "[vout]"

        loudnorm = f"loudnorm=I={settings.render_loudness_lufs}:TP=-1.5:LRA=11"
        filters.append(f"[1:a]aformat=sample_rates={self.sample_rate}:channel_layouts=stereo[narr]")
        mix_inputs = ["[narr]"]
        if music_index is not None:
            gain = settings.render_music_bed_gain_db
            filters.append(
                f"[{music_index}:a]aformat=sample_rates={self.sample_rate}:channel_layouts=stereo,"
                f"volume={gain}dB,aloop=loop=-1:size=2000000000[bed]"
            )
            # Duck the music under narration so speech stays intelligible.
            filters.append("[bed][narr]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[ducked]")
            mix_inputs.append("[ducked]")
        if sfx_index is not None:
            filters.append(
                f"[{sfx_index}:a]aformat=sample_rates={self.sample_rate}:channel_layouts=stereo,"
                f"volume={settings.render_sfx_gain_db}dB[sfx]"
            )
            mix_inputs.append("[sfx]")

        if len(mix_inputs) == 1:
            filters.append(f"{mix_inputs[0]}{loudnorm}[aout]")
        else:
            filters.append(
                f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0,{loudnorm}[aout]"
            )

        cmd += [
            "-filter_complex", ";".join(filters),
            "-map", video_map,
            "-map", "[aout]",
            *self._video_encode_args(),
            *self._audio_encode_args(),
            str(out_path),
        ]

        try:
            ff.run(cmd)
        except FFmpegError:
            if self.burn_subtitles and subtitle_path:
                # Subtitle burn-in is the most fragile step (font/path issues);
                # retry without it rather than failing the whole render.
                return self.mux_without_subtitles(video_path, audio_path, output_name, music_path, sfx_path)
            raise

        ff.validate_output(out_path, expect_video=True, expect_audio=True)
        return out_path

    def mux_without_subtitles(
        self,
        video_path: Path,
        audio_path: Path,
        output_name: str = "final_movie.mp4",
        music_path: Path | None = None,
        sfx_path: Path | None = None,
    ) -> Path:
        out_path = self.out_dir / output_name
        loudnorm = f"loudnorm=I={settings.render_loudness_lufs}:TP=-1.5:LRA=11"
        cmd = [self.ffmpeg_cmd, "-y", "-i", str(video_path), "-i", str(audio_path)]
        filters = [f"[1:a]aformat=sample_rates={self.sample_rate}:channel_layouts=stereo[narr]"]
        mix_inputs = ["[narr]"]

        if music_path and Path(music_path).exists():
            cmd += ["-i", str(music_path)]
            filters.append(
                f"[2:a]aformat=sample_rates={self.sample_rate}:channel_layouts=stereo,"
                f"volume={settings.render_music_bed_gain_db}dB,aloop=loop=-1:size=2000000000[bed]"
            )
            filters.append("[bed][narr]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[ducked]")
            mix_inputs.append("[ducked]")

        if sfx_path and Path(sfx_path).exists():
            cmd += ["-i", str(sfx_path)]
            sfx_input = 3 if music_path and Path(music_path).exists() else 2
            filters.append(
                f"[{sfx_input}:a]aformat=sample_rates={self.sample_rate}:channel_layouts=stereo,"
                f"volume={settings.render_sfx_gain_db}dB[sfx]"
            )
            mix_inputs.append("[sfx]")

        if len(mix_inputs) == 1:
            filters.append(f"{mix_inputs[0]}{loudnorm}[aout]")
        else:
            filters.append(
                f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0,{loudnorm}[aout]"
            )

        cmd += [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            *self._video_encode_args(),
            *self._audio_encode_args(),
            str(out_path),
        ]
        ff.run(cmd)
        ff.validate_output(out_path, expect_video=True, expect_audio=True)
        return out_path

    def extract_poster(self, video_path: Path, output_name: str = "poster.jpg") -> Path:
        """Grab a representative frame for use as a thumbnail in the UI."""
        out_path = self.out_dir / output_name
        duration = ff.probe_duration(Path(video_path))
        timestamp = max(0.5, min(duration * 0.15, max(0.5, duration - 0.5)))
        cmd = [
            self.ffmpeg_cmd, "-y",
            "-ss", f"{timestamp:.2f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "3",
            str(out_path),
        ]
        ff.run(cmd)
        return out_path


# Backwards-compatible alias: the service was previously called VideoService.
VideoService = RenderService

