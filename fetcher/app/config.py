from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    blsky_identifier: str
    blsky_app_password: str
    save_own_media: bool = False
    media_root: str = "/app/media"
    media_min_free_bytes: int = Field(default=5368709120, ge=0)
    media_max_file_bytes: int = Field(default=157286400, ge=0)
    media_max_total_bytes: int = Field(default=53687091200, ge=0)
    media_total_scan_interval_seconds: int = Field(default=300, ge=0)
    fetch_interval_seconds: int = 900
    fetch_page_limit: int = 100
    full_reconcile_interval_seconds: int = 86400
    error_backoff_seconds: int = 60
    request_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
