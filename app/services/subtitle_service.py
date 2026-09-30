from pathlib import Path


def _format_timestamp(total_seconds: float) -> str:
    millis = int(round(max(0.0, total_seconds) * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    seconds = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _wrap(text: str, max_chars: int = 42, max_lines: int = 2) -> str:
    """Wrap a caption to broadcast-style short lines."""
    words = (text or "").strip().split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines[:max_lines]) if lines else ""


def _split_into_cues(text: str, start: float, duration: float, max_chars: int = 84) -> list[tuple[float, float, str]]:
    """Break a scene's narration into readable, time-proportional cues.

    A single caption spanning an entire scene is unreadable; cue length is
    allocated proportionally to character count so timing tracks the speech.
    """
    clean = " ".join((text or "").split())
    if not clean or duration <= 0:
        return []

    words = clean.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)

    total_chars = sum(len(c) for c in chunks) or 1
    cues: list[tuple[float, float, str]] = []
    cursor = start
    for chunk in chunks:
        span = duration * (len(chunk) / total_chars)
        cues.append((cursor, cursor + span, _wrap(chunk)))
        cursor += span
    return cues


class SubtitleService:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def create_scene_subtitle(self, text: str, duration: float, scene_index: int) -> Path:
        path = self.out_dir / f"scene_{scene_index:03d}.srt"
        cues = _split_into_cues(text, 0.0, float(duration or 0))
        lines: list[str] = []
        for i, (start, end, content) in enumerate(cues, start=1):
            lines += [str(i), f"{_format_timestamp(start)} --> {_format_timestamp(end)}", content, ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def merge_scene_subtitles(
        self, texts: list[str], durations: list[float], output_name: str = "movie.srt"
    ) -> Path:
        """Build the master SRT from *measured* scene durations."""
        path = self.out_dir / output_name
        cursor = 0.0
        lines: list[str] = []
        index = 1
        for text, duration in zip(texts, durations):
            duration = float(duration or 0)
            for start, end, content in _split_into_cues(text, cursor, duration):
                lines += [str(index), f"{_format_timestamp(start)} --> {_format_timestamp(end)}", content, ""]
                index += 1
            cursor += duration
        path.write_text("\n".join(lines), encoding="utf-8")
        self._write_vtt(path)
        return path

    def _write_vtt(self, srt_path: Path) -> Path:
        """Emit a WebVTT sidecar so the browser player can show captions."""
        vtt_path = srt_path.with_suffix(".vtt")
        body = srt_path.read_text(encoding="utf-8").replace(",", ".")
        vtt_path.write_text("WEBVTT\n\n" + body, encoding="utf-8")
        return vtt_path
