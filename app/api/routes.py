from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from uuid import UUID
import time

from app.db.session import get_db
from app.db.models import TaskStatus, TaskPriority
from app.schemas.task import (
    TaskSubmitRequest, TaskResponse, TaskListResponse,
    TaskStatusResponse, WorkflowCreateRequest, WorkflowResponse,
    TaskLogEntry, HealthResponse, MetricsResponse
)
from app.core.task_service import TaskService
from app.core.config import get_settings
import redis as redis_lib
import logging

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

START_TIME = time.time()


# ─── HEALTH ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    db_status = "ok"
    redis_status = "ok"
    celery_workers = 0

    try:
        await db.execute("SELECT 1")
    except Exception:
        db_status = "error"

    try:
        r = redis_lib.from_url(settings.REDIS_URL)
        r.ping()
        # Check active Celery workers
        from app.core.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=1.0)
        active = inspect.active()
        celery_workers = len(active) if active else 0
    except Exception:
        redis_status = "error"

    return HealthResponse(
        status="healthy" if db_status == "ok" and redis_status == "ok" else "degraded",
        database=db_status,
        redis=redis_status,
        celery_workers=celery_workers,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


# ─── TASKS ─────────────────────────────────────────────────────────────────────

@router.post("/tasks", response_model=TaskResponse, status_code=201, tags=["Tasks"])
async def submit_task(
    request: TaskSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit a new task to the queue."""
    service = TaskService(db)
    try:
        task = await service.submit_task(request)
        return task
    except Exception as e:
        logger.error(f"submit_task error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@router.get("/tasks", response_model=TaskListResponse, tags=["Tasks"])
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[TaskStatus] = Query(default=None),
    priority: Optional[TaskPriority] = Query(default=None),
    task_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks with pagination and filtering."""
    service = TaskService(db)
    result = await service.list_tasks(
        page=page,
        page_size=page_size,
        status=status,
        priority=priority,
        task_type=task_type,
    )
    return TaskListResponse(**result)


@router.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get full task details by ID."""
    service = TaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/status", response_model=TaskStatusResponse, tags=["Tasks"])
async def get_task_status(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get lightweight task status (for polling)."""
    service = TaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(
        id=task.id,
        status=task.status,
        progress=task.progress,
        progress_message=task.progress_message,
        result=task.result,
        error=task.error,
        retry_count=task.retry_count,
        started_at=task.started_at,
        completed_at=task.completed_at,
        duration_seconds=task.duration_seconds,
    )


@router.get("/tasks/{task_id}/result", tags=["Tasks"])
async def get_task_result(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get task result (only available when status=success)."""
    service = TaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.SUCCESS:
        raise HTTPException(
            status_code=409,
            detail=f"Task result not available. Current status: {task.status.value}"
        )
    return {"task_id": str(task.id), "result": task.result}


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse, tags=["Tasks"])
async def cancel_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Cancel a running or queued task."""
    service = TaskService(db)
    task = await service.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse, tags=["Tasks"])
async def retry_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Manually retry a failed or cancelled task."""
    service = TaskService(db)
    task = await service.retry_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/logs", response_model=List[TaskLogEntry], tags=["Tasks"])
async def get_task_logs(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get execution logs for a task."""
    service = TaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logs = await service.get_task_logs(task_id)
    return logs


@router.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Soft-delete a terminal task."""
    service = TaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.is_terminal:
        raise HTTPException(status_code=409, detail="Cannot delete a non-terminal task. Cancel it first.")
    from datetime import datetime
    task.deleted_at = datetime.utcnow()
    await db.commit()


# ─── WORKFLOWS ─────────────────────────────────────────────────────────────────

@router.post("/workflows", response_model=WorkflowResponse, status_code=201, tags=["Workflows"])
async def create_workflow(
    request: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a workflow (group of related tasks)."""
    service = TaskService(db)
    workflow = await service.create_workflow(request)
    return workflow


# ─── METRICS ───────────────────────────────────────────────────────────────────

@router.get("/metrics", response_model=MetricsResponse, tags=["System"])
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """Get task queue metrics."""
    service = TaskService(db)
    return await service.get_metrics()
