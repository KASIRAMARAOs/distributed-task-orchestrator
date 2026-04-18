import time
import random
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict
from uuid import UUID

from celery import Task as CeleryTask
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.models import Task, TaskStatus, TaskLog
from app.db.session import sync_engine
from sqlalchemy.orm import sessionmaker

logger = get_task_logger(__name__)
settings = get_settings()

SyncSession = sessionmaker(bind=sync_engine)


def get_sync_db() -> Session:
    return SyncSession()


class BaseTask(CeleryTask):
    """Base task class with automatic DB status tracking."""
    abstract = True

    def on_success(self, retval, task_id, args, kwargs):
        db = get_sync_db()
        try:
            task = db.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.SUCCESS
                task.result = retval
                task.completed_at = datetime.utcnow()
                task.progress = 100
                task.progress_message = "Completed successfully"
                if task.started_at:
                    task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
                _log_task(db, task.id, "INFO", f"Task completed successfully: {task_id}")
                db.commit()
        except Exception as e:
            logger.error(f"on_success DB error: {e}")
            db.rollback()
        finally:
            db.close()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        db = get_sync_db()
        try:
            task = db.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.FAILURE
                task.error = str(exc)
                task.traceback = str(einfo)
                task.completed_at = datetime.utcnow()
                if task.started_at:
                    task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
                _log_task(db, task.id, "ERROR", f"Task failed: {str(exc)}", {"traceback": str(einfo)})
                db.commit()
        except Exception as e:
            logger.error(f"on_failure DB error: {e}")
            db.rollback()
        finally:
            db.close()

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        db = get_sync_db()
        try:
            task = db.query(Task).filter(Task.celery_task_id == task_id).first()
            if task:
                task.status = TaskStatus.RETRY
                task.retry_count += 1
                task.error = str(exc)
                task.retry_eta = datetime.utcnow() + timedelta(seconds=settings.CELERY_RETRY_BACKOFF * task.retry_count)
                _log_task(db, task.id, "WARN", f"Retrying task (attempt {task.retry_count}): {str(exc)}")
                db.commit()
        except Exception as e:
            logger.error(f"on_retry DB error: {e}")
            db.rollback()
        finally:
            db.close()


def _log_task(db: Session, task_id: UUID, level: str, message: str, data: Dict = None):
    log = TaskLog(task_id=task_id, level=level, message=message, data=data)
    db.add(log)


def update_task_progress(task_id_celery: str, progress: int, message: str = None):
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.celery_task_id == task_id_celery).first()
        if task:
            task.progress = min(max(progress, 0), 100)
            if message:
                task.progress_message = message
            db.commit()
    except Exception as e:
        logger.error(f"update_progress DB error: {e}")
        db.rollback()
    finally:
        db.close()


# ─────────────────────────────────────────────
# TASK IMPLEMENTATIONS
# ─────────────────────────────────────────────

@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.worker.generate_report",
    queue="default",
    max_retries=3,
    default_retry_delay=30,
)
def generate_report(self, task_db_id: str, payload: Dict[str, Any]) -> Dict:
    """Simulate report generation with progress updates."""
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.id == task_db_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.worker = self.request.hostname
            _log_task(db, task.id, "INFO", "Report generation started", payload)
            db.commit()

        report_id = payload.get("report_id", "unknown")
        report_type = payload.get("report_type", "summary")

        steps = ["Fetching data", "Aggregating results", "Formatting report", "Exporting PDF"]
        for i, step in enumerate(steps):
            time.sleep(random.uniform(0.5, 1.5))  # Simulate work
            progress = int((i + 1) / len(steps) * 90)
            update_task_progress(self.request.id, progress, step)
            logger.info(f"Report {report_id}: {step} ({progress}%)")

        result = {
            "report_id": report_id,
            "report_type": report_type,
            "rows": random.randint(100, 10000),
            "generated_at": datetime.utcnow().isoformat(),
            "url": f"/reports/{report_id}.pdf",
        }
        return result

    except SoftTimeLimitExceeded:
        raise self.retry(exc=SoftTimeLimitExceeded("Soft time limit exceeded"), countdown=60)
    except Exception as exc:
        logger.error(f"generate_report error: {exc}\n{traceback.format_exc()}")
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.worker.send_email",
    queue="default",
    max_retries=5,
    default_retry_delay=60,
)
def send_email(self, task_db_id: str, payload: Dict[str, Any]) -> Dict:
    """Simulate email sending."""
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.id == task_db_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.worker = self.request.hostname
            db.commit()

        to = payload.get("to", "unknown@example.com")
        subject = payload.get("subject", "No subject")

        update_task_progress(self.request.id, 30, "Connecting to SMTP")
        time.sleep(random.uniform(0.2, 0.5))

        update_task_progress(self.request.id, 70, "Sending email")
        time.sleep(random.uniform(0.1, 0.3))

        # Simulate occasional failure for retry demo
        if random.random() < 0.05:
            raise ConnectionError("SMTP connection failed (simulated)")

        update_task_progress(self.request.id, 100, "Email sent")
        return {"status": "sent", "to": to, "subject": subject, "message_id": f"msg-{int(time.time())}"}

    except ConnectionError as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.worker.process_data",
    queue="default",
    max_retries=3,
    default_retry_delay=30,
)
def process_data(self, task_db_id: str, payload: Dict[str, Any]) -> Dict:
    """Simulate data processing pipeline."""
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.id == task_db_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.worker = self.request.hostname
            db.commit()

        dataset = payload.get("dataset", "default")
        records = payload.get("records", 1000)

        stages = [
            ("Validating schema", 15),
            ("Loading data", 35),
            ("Transforming", 60),
            ("Enriching", 80),
            ("Persisting results", 95),
        ]

        for step_name, progress in stages:
            time.sleep(random.uniform(0.3, 1.0))
            update_task_progress(self.request.id, progress, step_name)

        return {
            "dataset": dataset,
            "records_processed": records,
            "records_failed": random.randint(0, 5),
            "duration_seconds": round(random.uniform(1.5, 8.0), 2),
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.worker.web_scrape",
    queue="low_priority",
    max_retries=3,
)
def web_scrape(self, task_db_id: str, payload: Dict[str, Any]) -> Dict:
    """Simulate web scraping task."""
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.id == task_db_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.worker = self.request.hostname
            db.commit()

        url = payload.get("url", "https://example.com")
        update_task_progress(self.request.id, 20, "Fetching page")
        time.sleep(random.uniform(0.5, 2.0))

        update_task_progress(self.request.id, 60, "Parsing content")
        time.sleep(random.uniform(0.2, 0.8))

        update_task_progress(self.request.id, 90, "Extracting data")
        time.sleep(random.uniform(0.1, 0.3))

        return {
            "url": url,
            "items_found": random.randint(5, 100),
            "pages_scraped": random.randint(1, 10),
            "scraped_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.worker.critical_payment",
    queue="critical",
    max_retries=5,
    default_retry_delay=10,
)
def critical_payment(self, task_db_id: str, payload: Dict[str, Any]) -> Dict:
    """Simulate a critical high-priority payment task."""
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.id == task_db_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.worker = self.request.hostname
            db.commit()

        amount = payload.get("amount", 0)
        currency = payload.get("currency", "USD")

        update_task_progress(self.request.id, 25, "Verifying payment details")
        time.sleep(0.1)
        update_task_progress(self.request.id, 50, "Processing with payment gateway")
        time.sleep(random.uniform(0.2, 0.5))
        update_task_progress(self.request.id, 90, "Confirming transaction")
        time.sleep(0.1)

        return {
            "transaction_id": f"txn_{int(time.time())}",
            "amount": amount,
            "currency": currency,
            "status": "approved",
            "processed_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.worker.generic_task",
    queue="default",
    max_retries=3,
)
def generic_task(self, task_db_id: str, payload: Dict[str, Any]) -> Dict:
    """Generic fallback task for unknown task types."""
    db = get_sync_db()
    try:
        task = db.query(Task).filter(Task.id == task_db_id).first()
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.worker = self.request.hostname
            db.commit()

        time.sleep(random.uniform(0.5, 2.0))
        update_task_progress(self.request.id, 100, "Done")
        return {"task_db_id": task_db_id, "payload": payload, "completed": True}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


@celery_app.task(name="app.tasks.worker.cleanup_old_tasks")
def cleanup_old_tasks() -> Dict:
    """Periodic task to soft-delete old completed tasks."""
    db = get_sync_db()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        result = db.query(Task).filter(
            Task.status.in_([TaskStatus.SUCCESS, TaskStatus.FAILURE]),
            Task.completed_at < cutoff,
            Task.deleted_at.is_(None)
        ).update({"deleted_at": datetime.utcnow()})
        db.commit()
        logger.info(f"Cleaned up {result} old tasks")
        return {"cleaned_up": result}
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


# Task type to Celery task function mapping
TASK_REGISTRY = {
    "generate_report": generate_report,
    "send_email": send_email,
    "process_data": process_data,
    "web_scrape": web_scrape,
    "critical_payment": critical_payment,
}


def get_task_function(task_type: str):
    return TASK_REGISTRY.get(task_type, generic_task)
