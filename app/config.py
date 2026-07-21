from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    upload_dir: str = "./uploads"
    # Level-matched texts assigned to study participants at onboarding, one file
    # per CEFR level (A1.txt … C2.txt). See POST /study/assign.
    study_texts_dir: str = "./study_texts"
    openai_api_key: str | None = None
    # The LCP model runs on Modal, not in this process (see app/lib/lcp_modal.py).
    # These are read from .env by modal_deploy.py when it pushes the Modal secret;
    # the web process never uses them, so it must not require them to boot.
    lcp_model_dir: str | None = None
    lcp_model_token: str | None = None
    lcp_model_revision: str | None = None
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()