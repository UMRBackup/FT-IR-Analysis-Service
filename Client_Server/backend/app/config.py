from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "FT-IR Client Server"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"

    code_root: Path = Path("../Code")
    storage_root: Path = Path("./storage")
    shared_storage_root: Path = Path("./storage")

    database_url: str = "mysql+pymysql://ftir:ftir@localhost:3307/ftir"
    celery_broker_url: str = "sqla+mysql+pymysql://ftir:ftir@localhost:3307/ftir"
    celery_result_backend: str = "db+mysql+pymysql://ftir:ftir@localhost:3307/ftir"

    rpa_queue_concurrency: int = 1

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
