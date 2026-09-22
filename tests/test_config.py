from pathlib import Path

from app.config import Settings


def test_settings_ignore_unknown_env_keys(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_NAME=AI Movie Maker",
                "DATABASE_URL=sqlite:///./ai_movie_maker.db",
                "COMFYUI_MODEL_PATHS=C:/models/checkpoints",
                "SOME_UNKNOWN_KEY=will_be_ignored",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.comfyui_model_paths == "C:/models/checkpoints"


