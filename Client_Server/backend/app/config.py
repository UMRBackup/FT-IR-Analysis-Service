from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "FT-IR Client Server"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"

    code_root: Path = Path("../Code")
    storage_root: Path = Path("./storage")

    database_url: str = "mysql+pymysql://ftir:ftir@localhost:3307/ftir"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_enable_utc: bool = False
    celery_timezone: str = "Asia/Shanghai"

    rpa_queue_concurrency: int = 1

    jwt_secret_key: str = "change-this-in-production"
    jwt_previous_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    jwt_current_kid: str = "v1"
    jwt_previous_kid: str = ""

    initial_admin_username: str = "admin"
    initial_admin_password: str = ""

    shared_file_retry_timeout_sec: float = 45.0
    shared_file_retry_initial_delay_sec: float = 1.0
    shared_file_retry_max_delay_sec: float = 8.0

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
