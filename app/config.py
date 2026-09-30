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
    # ---------------- Render / FFmpeg ----------------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    public_asset_base_url: str = "http://127.0.0.1:8000/static"
    render_width: int = 1920
    render_height: int = 1080
    render_fps: int = 30
    render_crf: int = 20
    render_preset: str = "medium"
    render_audio_bitrate: str = "192k"
    render_audio_sample_rate: int = 44100
    render_loudness_lufs: float = -16.0
    render_transition: str = "fade"
    render_transition_seconds: float = 0.5
    render_ken_burns: bool = True
    render_burn_subtitles: bool = True
    render_music_bed_gain_db: float = -18.0
    render_min_scene_seconds: float = 2.0

    # ---------------- TTS ----------------
    tts_provider: str = "edge"
    tts_fallback_chain: str = "edge,openai,elevenlabs,azure,google,piper,pyttsx3"
    tts_mp3_bitrate: str = "192k"
    tts_sample_rate: int = 44100
    tts_normalize: bool = True
    tts_target_lufs: float = -16.0
    tts_speaking_rate: float = 1.0
    tts_pitch: float = 0.0
    tts_sentence_pause_ms: int = 350
    tts_max_retries: int = 3

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_stability: float = 0.45
    elevenlabs_similarity_boost: float = 0.8

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"

    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_voice: str = "en-US-AvaMultilingualNeural"

    google_application_credentials: str = ""
    google_tts_voice: str = "en-US-Neural2-F"
    google_tts_language_code: str = "en-US"

    edge_tts_voice: str = "en-US-AriaNeural"

    piper_executable: str = ""
    piper_model_path: str = ""
    piper_length_scale: float = 1.0
    piper_noise_scale: float = 0.667

    redis_url: str = ""
    queue_name: str = "ai_movie_maker"
    rq_retry_max: int = 3
    rq_retry_intervals: str = "20,60,180"
    music_model_id: str = "facebook/musicgen-small"
    music_output_dir: str = "./workspace/music"
    music_max_duration_seconds: int = 16
    music_default_duration_seconds: int = 8
    music_allowed_durations: str = "4,8,12,16"
    music_debug_metrics: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
settings.workspace_dir.mkdir(parents=True, exist_ok=True)

