from pydantic import SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict
from pathlib import Path
base_dir = Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=base_dir / ".env",
        env_file_encoding="utf-8",
    )
    db_url : str
    pw_max_length : int
    pw_min_length : int
    # The local initializer writes this ring to .env; production injects it as an environment secret.
    api_key_keks: SecretStr | None = None
    api_key_active_kek_version: str | None = None
    cookie_secure: bool = False
    captcha_key : str
settings = Settings()
