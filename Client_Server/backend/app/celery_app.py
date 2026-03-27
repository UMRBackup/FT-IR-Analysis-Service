import os
import logging

from celery import Celery
from celery.signals import worker_init

from .config import settings
from .shared_paths import ensure_shared_root_ready


logger = logging.getLogger(__name__)

celery_app = Celery(
    "ftir_client_server",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    enable_utc=settings.celery_enable_utc,
    timezone=settings.celery_timezone,
)
celery_app.conf.task_default_queue = "preprocess_queue"
celery_app.conf.task_routes = {
    "app.tasks.preprocess_task": {"queue": "preprocess_queue"},
    "app.tasks.rpa_task": {"queue": "rpa_queue"},
    "app.tasks.postprocess_task": {"queue": "postprocess_queue"},
}

# On Windows, prefork/billiard can fail with fast_trace_task unpack errors.
# Force solo pool to keep worker startup and task execution stable.
if os.name == "nt":
    celery_app.conf.worker_pool = "solo"
    celery_app.conf.worker_concurrency = 1


@worker_init.connect
def _worker_shared_root_precheck(**kwargs: object) -> None:
    root = ensure_shared_root_ready("celery-worker-startup")
    logger.info("Storage root precheck passed for worker: %s", root)
