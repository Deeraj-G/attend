from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cases_dir: Path = Path("cases")

    # On-device models
    lfm_model_path: Path | None = None
    lfm_audio_model_path: Path | None = None  # local checkout; falls back to the HF repo below
    lfm_audio_repo: str = "LiquidAI/LFM2.5-Audio-1.5B"
    lfm_audio_device: str = "auto"  # auto | mps | cuda | cpu

    # Recorder
    max_recording_seconds: int = 300

    # External services
    nimble_api_key: str = ""
    bfl_api_key: str = ""

    # Harness budgets
    max_rounds: int = 30
    max_research_iterations: int = 3
    executor_token_budget: int = 4000


settings = Settings()
