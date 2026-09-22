from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Movie Maker"
    database_url: str = "sqlite:///./ai_movie_maker.db"
    workspace_dir: Path = Path("./workspace")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    comfyui_url: str = ""
    comfyui_start_command: str = ""
    comfyui_workdir: str = ""
    comfyui_auto_workdirs: str = ""
    comfyui_model_paths: str = ""
    comfyui_extra_model_paths_config: str = ""
    comfyui_startup_timeout: int = 180
    comfyui_sd_workflow: str = "./app/workflows/comfyui_sdxl_image.json"
    comfyui_animatediff_workflow: str = "./app/workflows/comfyui_animatediff_video.json"
    comfyui_sd_prompt_node_id: str = ""
    comfyui_sd_seed_node_id: str = ""
    comfyui_sd_checkpoint_node_id: str = ""
    comfyui_sd_output_node_id: str = ""
    comfyui_sd_checkpoint_name: str = "sd_xl_base_1.0.safetensors"
    comfyui_ad_prompt_node_id: str = ""
    comfyui_ad_seed_node_id: str = ""
    comfyui_ad_checkpoint_node_id: str = ""
    comfyui_ad_output_node_id: str = ""
    comfyui_ad_checkpoint_name: str = "sd_xl_base_1.0.safetensors"
    piper_executable: str = ""
    piper_model_path: str = ""
    ffmpeg_bin: str = "ffmpeg"
    redis_url: str = ""
    queue_name: str = "ai_movie_maker"
    rq_retry_max: int = 3
    rq_retry_intervals: str = "20,60,180"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
settings.workspace_dir.mkdir(parents=True, exist_ok=True)

