"""Normalise and encode synthesised speech into a consistent MP3 profile."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.config import settings
from app.services import ffmpeg_runner as ff


def encode_to_mp3(audio: bytes, source_format: str, output_path: Path) -> Path:
    """Write raw provider bytes out as a normalised MP3.

    Applies EBU R128 loudness normalisation so clips from different providers
    (or different sessions of the same provider) sit at the same perceived
    level, then encodes CBR MP3 at the configured bitrate/sample rate.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = f".{source_format.lstrip('.')}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)
        tmp_path = Path(tmp.name)

    try:
        filters = [
            # Trim dead air the engines often leave at the head/tail.
            "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-50dB:"
            "detection=peak,areverse,"
            "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-50dB:"
            "detection=peak,areverse",
        ]
        if settings.tts_normalize:
            filters.append(f"loudnorm=I={settings.tts_target_lufs}:TP=-1.5:LRA=11")

        cmd = [
            ff.ffmpeg_bin(), "-y",
            "-i", str(tmp_path),
            "-af", ",".join(filters),
            "-c:a", "libmp3lame",
            "-b:a", settings.tts_mp3_bitrate,
            "-ar", str(settings.tts_sample_rate),
            "-ac", "1",
            str(output_path),
        ]
        ff.run(cmd, timeout=600)
        ff.validate_output(output_path, expect_video=False, expect_audio=True)
        return output_path
    finally:
        tmp_path.unlink(missing_ok=True)


def concat_segments(segments: list[Path], output_path: Path, pause_ms: int | None = None) -> Path:
    """Join per-sentence segments, inserting a natural pause between each."""
    if not segments:
        raise ValueError("No audio segments to concatenate")
    if len(segments) == 1:
        if Path(segments[0]).resolve() != Path(output_path).resolve():
            Path(output_path).write_bytes(Path(segments[0]).read_bytes())
        return Path(output_path)

    pause = (settings.tts_sentence_pause_ms if pause_ms is None else pause_ms) / 1000.0
    sample_rate = settings.tts_sample_rate

    cmd = [ff.ffmpeg_bin(), "-y"]
    for seg in segments:
        cmd += ["-i", str(seg)]

    parts: list[str] = []
    labels: list[str] = []
    for i in range(len(segments)):
        parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=mono[s{i}]")
        labels.append(f"[s{i}]")
        if i < len(segments) - 1 and pause > 0:
            parts.append(f"anullsrc=channel_layout=mono:sample_rate={sample_rate}:d={pause:.3f}[p{i}]")
            labels.append(f"[p{i}]")

    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[aout]")

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[aout]",
        "-c:a", "libmp3lame",
        "-b:a", settings.tts_mp3_bitrate,
        "-ar", str(sample_rate),
        "-ac", "1",
        str(output_path),
    ]
    ff.run(cmd, timeout=900)
    ff.validate_output(output_path, expect_video=False, expect_audio=True)
    return Path(output_path)


def split_sentences(text: str, max_chars: int = 600) -> list[str]:
    """Chunk text on sentence boundaries so long scripts stay within API limits."""
    import re

    text = " ".join((text or "").split())
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # A single sentence longer than the limit still has to be broken up.
            while len(sentence) > max_chars:
                cut = sentence.rfind(" ", 0, max_chars)
                cut = cut if cut > 0 else max_chars
                chunks.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            current = sentence
    if current:
        chunks.append(current)
    return chunks

