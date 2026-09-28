from __future__ import annotations


def compose_music_prompt(
    user_prompt: str,
    *,
    mood: str,
    style: str,
    energy: str,
    instrumentation: str,
) -> str:
    """Build a coherent deterministic generation prompt from user intent + controls."""
    base = user_prompt.strip().rstrip(".")
    mood_part = mood.strip().lower()
    style_part = style.strip().lower()
    energy_part = energy.strip().lower()
    instrumentation_part = instrumentation.strip().strip(".")

    composed = (
        f"{mood_part} {style_part} instrumental inspired by {base}, "
        f"{instrumentation_part}, {energy_part} energy, studio-quality arrangement, no vocals"
    )
    return " ".join(composed.split())

