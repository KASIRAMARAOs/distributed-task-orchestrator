import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text,
    Enum, JSON, ForeignKey, Index, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class TaskStatus(str, PyEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    REVOKED = "revoked"
    CANCELLED = "cancelled"


class TaskPriority(str, PyEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


PRIORITY_MAP = {
    TaskPriority.LOW: 1,
    TaskPriority.NORMAL: 5,
    TaskPriority.HIGH: 8,
    TaskPriority.CRITICAL: 10,
}


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    task_type = Column(String(100), nullable=False, index=True)
    status = Column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    priority = Column(
        Enum(TaskPriority),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True,
    )
    priority_value = Column(Integer, default=5)

    # Task input/output
    payload = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)

    # Execution metadata
    celery_task_id = Column(String(255), nullable=True, unique=True, index=True)
    worker = Column(String(255), nullable=True)
    queue = Column(String(100), default="default")

    # Retry configuration
    max_retries = Column(Integer, default=3)
    retry_count = Column(Integer, default=0)
    retry_eta = Column(DateTime, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    queued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Progress
    progress = Column(Integer, default=0)  # 0-100
    progress_message = Column(String(500), nullable=True)

    # Tags and metadata
    tags = Column(JSON, default=list)
    metadata = Column(JSON, default=dict)

    # Workflow
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=True)
    workflow = relationship("Workflow", back_populates="tasks")

    # Soft delete
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_tasks_status_priority", "status", "priority_value"),
        Index("ix_tasks_created_at", "created_at"),
        Index("ix_tasks_workflow_id", "workflow_id"),
    )

    def __repr__(self):
        return f"<Task id={self.id} name={self.name} status={self.status}>"

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.SUCCESS, TaskStatus.FAILURE,
            TaskStatus.REVOKED, TaskStatus.CANCELLED
        )

    @property
    def elapsed_time(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        if self.started_at:
            return (datetime.utcnow() - self.started_at).total_seconds()
        return None


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )

    tasks = relationship("Task", back_populates="workflow", lazy="dynamic")
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    metadata = Column(JSON, default=dict)

    def __repr__(self):
        return f"<Workflow id={self.id} name={self.name}>"


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_task_logs_task_id_created", "task_id", "created_at"),
    )
