from pydantic_settings import BaseSettings,SettingsConfigDict
from pathlib import Path
base_dir = Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=base_dir / ".env",
        env_file_encoding="utf-8",
        extra="ignore",   # .env 里的多余键不报错（如已废弃的 API_KEY_KEKS）
    )
    db_url : str
    pw_max_length : int
    pw_min_length : int
    cookie_secure: bool = False
    captcha_key : str
    bocha_api_key : str|None = None
    api_key_kek : str|None = None
settings = Settings()
