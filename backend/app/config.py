from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cases_dir: Path = Path("cases")

    # On-device models
    lfm_model_path: Path | None = None
    lfm_model: str = "LiquidAI/LFM2.5-2.6B"
    lfm_audio_model_path: Path | None = None  # local checkout; falls back to the HF repo below
    lfm_audio_repo: str = "LiquidAI/LFM2.5-Audio-1.5B"
    lfm_audio_device: str = "auto"  # auto | mps | cuda | cpu
    hf_token: str = ""
    # When set, call the model servers from docker-compose instead of loading in-process.
    lfm_base_url: str = ""  # llama.cpp server, OpenAI-compatible
    lfm_audio_base_url: str = ""  # docker/lfm-audio/server.py
    model_timeout_seconds: float = 600.0  # CPU inference in a container is slow

    # Recorder
    max_recording_seconds: int = 300


    # External services
    nimble_api_key: str = ""
    nimble_api_base: str = "https://sdk.nimbleway.com/v2"
    nimble_timeout_seconds: float = 30.0
    nimble_max_calls_per_run: int = 3  # one text + one image + one video search
    nimble_results_per_call: int = 8
    bfl_api_key: str = ""

    # Harness budgets
    max_rounds: int = 30
    max_attempts: int = 2  # per subtask, before asking the doctor
    max_research_iterations: int = 3
    executor_token_budget: int = 4000


settings = Settings()
