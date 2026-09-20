from pydantic_settings import BaseSettings,SettingsConfigDict
from pathlib import Path
base_dir = Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=base_dir / ".env",
        env_file_encoding="utf-8",
    )
    db_url : str
settings = Settings()

