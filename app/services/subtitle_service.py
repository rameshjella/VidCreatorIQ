from pathlib import Path


def _format_timestamp(total_seconds: float) -> str:
    millis = int(round(total_seconds * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    seconds = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


class SubtitleService:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def create_scene_subtitle(self, text: str, duration: float, scene_index: int) -> Path:
        path = self.out_dir / f"scene_{scene_index:03d}.srt"
        content = (
            "1\n"
            f"{_format_timestamp(0)} --> {_format_timestamp(duration)}\n"
            f"{text.strip()}\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    def merge_scene_subtitles(self, texts: list[str], durations: list[float], output_name: str = "movie.srt") -> Path:
        path = self.out_dir / output_name
        current = 0.0
        lines: list[str] = []
        for i, (text, duration) in enumerate(zip(texts, durations), start=1):
            start = _format_timestamp(current)
            end = _format_timestamp(current + duration)
            lines.extend([str(i), f"{start} --> {end}", text.strip(), ""])
            current += duration
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

