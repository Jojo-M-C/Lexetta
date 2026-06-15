from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    upload_dir: str = "./uploads"
    openai_api_key: str | None = None
    # Local path or Hugging Face Hub repo id of the trained LCP model.
    lcp_model_dir: str
    # Hugging Face token for loading a private Hub repo (optional).
    lcp_model_token: str | None = None
    # Branch, tag, or commit hash to load from the Hub (optional).
    lcp_model_revision: str | None = None
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()