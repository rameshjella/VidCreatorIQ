from app.services.music_prompt_service import compose_music_prompt


def test_compose_music_prompt_is_deterministic() -> None:
    prompt = compose_music_prompt(
        "Rainy night in Hyderabad",
        mood="Nostalgic",
        style="Cinematic",
        energy="Low",
        instrumentation="Piano and strings",
    )
    assert "nostalgic cinematic" in prompt
    assert "Rainy night in Hyderabad" in prompt
    assert "Piano and strings" in prompt
    assert "low energy" in prompt

