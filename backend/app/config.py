from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cases_dir: Path = Path("cases")

    # On-device models
    lfm_model_path: Path | None = None
    lfm_audio_model_path: Path | None = None

    # External services
    nimble_api_key: str = ""
    nimble_api_base: str = "https://sdk.nimbleway.com/v2"
    nimble_timeout_seconds: float = 30.0
    nimble_max_calls_per_run: int = 3  # one text + one image + one video search
    nimble_results_per_call: int = 8
    bfl_api_key: str = ""

    # Harness budgets
    max_rounds: int = 30
    max_research_iterations: int = 3
    executor_token_budget: int = 4000


settings = Settings()
