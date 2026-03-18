import os

from celery import Celery

from .config import settings

celery_app = Celery(
    "ftir_client_server",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
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
