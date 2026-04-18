from pydantic import BaseModel, Field, validator
from typing import Optional, Any, List, Dict
from datetime import datetime
from uuid import UUID
from app.db.models import TaskStatus, TaskPriority


class TaskSubmitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable task name")
    task_type: str = Field(..., description="Type of task to execute (e.g. 'send_email', 'process_data')")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Task input data")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)
    max_retries: int = Field(default=3, ge=0, le=10)
    queue: str = Field(default="default", description="Queue to submit to (default, high_priority, low_priority)")
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    workflow_id: Optional[UUID] = None

    @validator("queue")
    def validate_queue(cls, v):
        allowed = {"default", "high_priority", "low_priority", "critical"}
        if v not in allowed:
            raise ValueError(f"Queue must be one of: {allowed}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Process user report",
                "task_type": "generate_report",
                "payload": {"user_id": 123, "report_type": "monthly"},
                "priority": "high",
                "max_retries": 3,
                "tags": ["reports", "user-123"]
            }
        }


class TaskResponse(BaseModel):
    id: UUID
    name: str
    task_type: str
    status: TaskStatus
    priority: TaskPriority
    payload: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    celery_task_id: Optional[str] = None
    worker: Optional[str] = None
    queue: str
    max_retries: int
    retry_count: int
    progress: int
    progress_message: Optional[str] = None
    tags: List[str]
    metadata: Dict[str, Any]
    workflow_id: Optional[UUID] = None
    created_at: datetime
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int


class TaskStatusResponse(BaseModel):
    id: UUID
    status: TaskStatus
    progress: int
    progress_message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    tasks: List[TaskSubmitRequest]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    status: TaskStatus
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any]

    class Config:
        from_attributes = True


class TaskLogEntry(BaseModel):
    id: UUID
    task_id: UUID
    level: str
    message: str
    data: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    celery_workers: int
    uptime_seconds: float
    version: str = "1.0.0"


class MetricsResponse(BaseModel):
    total_tasks: int
    pending_tasks: int
    running_tasks: int
    success_tasks: int
    failed_tasks: int
    avg_duration_seconds: Optional[float]
    tasks_per_hour: float
