from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, and_, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, TaskStatus, TaskPriority, TaskLog, Workflow, PRIORITY_MAP
from app.schemas.task import TaskSubmitRequest, WorkflowCreateRequest
from app.tasks.worker import get_task_function
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

QUEUE_BY_PRIORITY = {
    TaskPriority.CRITICAL: "critical",
    TaskPriority.HIGH: "high_priority",
    TaskPriority.NORMAL: "default",
    TaskPriority.LOW: "low_priority",
}


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_task(self, request: TaskSubmitRequest) -> Task:
        """Create and enqueue a task."""
        task = Task(
            name=request.name,
            task_type=request.task_type,
            status=TaskStatus.PENDING,
            priority=request.priority,
            priority_value=PRIORITY_MAP[request.priority],
            payload=request.payload,
            max_retries=request.max_retries,
            queue=request.queue or QUEUE_BY_PRIORITY[request.priority],
            tags=request.tags,
            metadata=request.metadata,
            workflow_id=request.workflow_id,
        )
        self.db.add(task)
        await self.db.flush()  # get task.id

        # Enqueue in Celery
        task_fn = get_task_function(request.task_type)
        queue = task.queue

        celery_result = task_fn.apply_async(
            kwargs={"task_db_id": str(task.id), "payload": request.payload},
            queue=queue,
            priority=PRIORITY_MAP[request.priority],
            retry=True,
            retry_policy={
                "max_retries": request.max_retries,
                "interval_start": 0,
                "interval_step": settings.CELERY_RETRY_BACKOFF,
                "interval_max": 300,
            },
        )

        task.celery_task_id = celery_result.id
        task.status = TaskStatus.QUEUED
        task.queued_at = datetime.utcnow()

        await self._add_log(task.id, "INFO", f"Task queued: {celery_result.id}", {"queue": queue})
        await self.db.commit()
        await self.db.refresh(task)

        logger.info(f"Task submitted: {task.id} -> celery:{celery_result.id} queue:{queue}")
        return task

    async def get_task(self, task_id: UUID) -> Optional[Task]:
        result = await self.db.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_task_by_celery_id(self, celery_id: str) -> Optional[Task]:
        result = await self.db.execute(
            select(Task).where(Task.celery_task_id == celery_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        task_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        filters = [Task.deleted_at.is_(None)]
        if status:
            filters.append(Task.status == status)
        if priority:
            filters.append(Task.priority == priority)
        if task_type:
            filters.append(Task.task_type == task_type)

        # Count
        count_q = select(func.count(Task.id)).where(and_(*filters))
        total = (await self.db.execute(count_q)).scalar()

        # Paginated results
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Task)
            .where(and_(*filters))
            .order_by(desc(Task.created_at))
            .offset(offset)
            .limit(page_size)
        )
        tasks = result.scalars().all()

        return {
            "tasks": tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    async def cancel_task(self, task_id: UUID) -> Optional[Task]:
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.is_terminal:
            return task  # Already finished

        # Revoke in Celery
        if task.celery_task_id:
            from app.core.celery_app import celery_app
            celery_app.control.revoke(task.celery_task_id, terminate=True, signal="SIGTERM")

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.utcnow()
        await self._add_log(task.id, "WARN", "Task cancelled by user")
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def retry_task(self, task_id: UUID) -> Optional[Task]:
        task = await self.get_task(task_id)
        if not task:
            return None
        if task.status not in (TaskStatus.FAILURE, TaskStatus.CANCELLED):
            return task

        task_fn = get_task_function(task.task_type)
        celery_result = task_fn.apply_async(
            kwargs={"task_db_id": str(task.id), "payload": task.payload},
            queue=task.queue,
        )

        task.celery_task_id = celery_result.id
        task.status = TaskStatus.QUEUED
        task.queued_at = datetime.utcnow()
        task.completed_at = None
        task.error = None
        task.result = None
        task.retry_count += 1

        await self._add_log(task.id, "INFO", f"Task manually retried: {celery_result.id}")
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_task_logs(self, task_id: UUID) -> List[TaskLog]:
        result = await self.db.execute(
            select(TaskLog)
            .where(TaskLog.task_id == task_id)
            .order_by(TaskLog.created_at)
        )
        return result.scalars().all()

    async def get_metrics(self) -> Dict[str, Any]:
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)

        status_counts = {}
        for status in TaskStatus:
            count = (await self.db.execute(
                select(func.count(Task.id)).where(Task.status == status, Task.deleted_at.is_(None))
            )).scalar()
            status_counts[status.value] = count

        avg_duration = (await self.db.execute(
            select(func.avg(Task.duration_seconds))
            .where(Task.status == TaskStatus.SUCCESS, Task.duration_seconds.isnot(None))
        )).scalar()

        tasks_per_hour = (await self.db.execute(
            select(func.count(Task.id))
            .where(Task.created_at >= hour_ago, Task.deleted_at.is_(None))
        )).scalar()

        return {
            "total_tasks": sum(status_counts.values()),
            "pending_tasks": status_counts.get("pending", 0) + status_counts.get("queued", 0),
            "running_tasks": status_counts.get("running", 0),
            "success_tasks": status_counts.get("success", 0),
            "failed_tasks": status_counts.get("failure", 0),
            "avg_duration_seconds": round(avg_duration, 2) if avg_duration else None,
            "tasks_per_hour": tasks_per_hour,
        }

    async def create_workflow(self, request: WorkflowCreateRequest) -> Workflow:
        workflow = Workflow(
            name=request.name,
            description=request.description,
            total_tasks=len(request.tasks),
            metadata=request.metadata,
        )
        self.db.add(workflow)
        await self.db.flush()

        for task_req in request.tasks:
            task_req.workflow_id = workflow.id
            await self.submit_task(task_req)

        await self.db.commit()
        await self.db.refresh(workflow)
        return workflow

    async def _add_log(self, task_id: UUID, level: str, message: str, data: Dict = None):
        log = TaskLog(task_id=task_id, level=level, message=message, data=data)
        self.db.add(log)
