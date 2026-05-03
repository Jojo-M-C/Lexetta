from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    upload_dir: str = "./uploads"
    openai_api_key: str | None = None
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()