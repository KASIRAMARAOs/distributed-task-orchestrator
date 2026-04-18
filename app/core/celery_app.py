from celery import Celery
from celery.utils.log import get_task_logger
from app.core.config import get_settings
import logging

logger = get_task_logger(__name__)
settings = get_settings()


def create_celery_app() -> Celery:
    app = Celery(
        "task_orchestrator",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )

    app.conf.update(
        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Timezone
        timezone="UTC",
        enable_utc=True,
        # Task behavior
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_soft_time_limit=settings.TASK_SOFT_TIME_LIMIT,
        task_time_limit=settings.TASK_TIME_LIMIT,
        # Results
        result_expires=86400,  # 24 hours
        result_persistent=True,
        # Workers
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=100,
        worker_send_task_events=True,
        task_send_sent_event=True,
        # Retry
        task_default_retry_delay=settings.CELERY_RETRY_BACKOFF,
        task_max_retries=settings.CELERY_MAX_RETRIES,
        # Queues
        task_default_queue="default",
        task_queues={
            "default": {"exchange": "default", "routing_key": "default"},
            "high_priority": {"exchange": "high_priority", "routing_key": "high_priority"},
            "low_priority": {"exchange": "low_priority", "routing_key": "low_priority"},
            "critical": {"exchange": "critical", "routing_key": "critical"},
        },
        task_routes={
            "app.tasks.worker.*": {"queue": "default"},
        },
        # Beat schedule (optional periodic tasks)
        beat_schedule={
            "cleanup-old-tasks": {
                "task": "app.tasks.worker.cleanup_old_tasks",
                "schedule": 3600.0,  # every hour
            },
        },
    )

    # Auto-discover tasks
    app.autodiscover_tasks(["app.tasks"])
    return app


celery_app = create_celery_app()
