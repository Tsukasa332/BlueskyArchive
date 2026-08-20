from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    media_root: str = "/app/media"
    app_timezone: str = "Asia/Tokyo"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
