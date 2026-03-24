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
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_enable_utc: bool = False
    celery_timezone: str = "Asia/Shanghai"

    rpa_queue_concurrency: int = 1

    shared_file_retry_timeout_sec: float = 45.0
    shared_file_retry_initial_delay_sec: float = 1.0
    shared_file_retry_max_delay_sec: float = 8.0

    # Optional credentials used by Windows host processes to establish UNC sessions.
    # These do not affect container-side CIFS mounts.
    unc_username: str = ""
    unc_password: str = ""
    nas_user: str = ""
    nas_pass: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
