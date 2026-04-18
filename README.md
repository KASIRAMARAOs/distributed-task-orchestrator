# TaskOrchestrator — Distributed Task & Workflow Orchestrator

A production-grade distributed task queue system demonstrating async processing, retry logic, priority queues, workflow orchestration, and real-time monitoring.

## Features

- **Distributed task execution** via Celery workers
- **4 priority queues**: critical → high → normal → low
- **Automatic retry** with exponential backoff
- **Workflow support** — group related tasks under a workflow
- **Real-time progress tracking** — 0–100% per task
- **Persistent task history** in PostgreSQL
- **Flower dashboard** for live worker/queue monitoring
- **Celery Beat** for periodic/scheduled tasks
- **Structured logging** with structlog
- **Full REST API** with OpenAPI docs

## Tech Stack

| Component | Technology |
|---|---|
| API | Python 3.11, FastAPI, Uvicorn |
| Task Queue | Celery 5 |
| Broker | Redis |
| Result Backend | Redis |
| Database | PostgreSQL 15 + SQLAlchemy 2 (async) |
| Monitoring | Flower |
| Containerization | Docker, Docker Compose |

## Architecture

```
                    ┌─────────────┐
   HTTP Request ───►│  FastAPI    │
                    │   API       │──── PostgreSQL (task state)
                    └──────┬──────┘
                           │ submit
                           ▼
                    ┌─────────────┐
                    │    Redis    │◄─── Celery Beat (scheduled)
                    │  (Broker)   │
                    └──────┬──────┘
               ┌───────────┼───────────┐
               ▼           ▼           ▼
        ┌────────────┐ ┌────────┐ ┌──────────┐
        │  Worker    │ │Worker  │ │ Worker   │
        │ (critical/ │ │(default│ │(low      │
        │  high)     │ │ queue) │ │ priority)│
        └────────────┘ └────────┘ └──────────┘
               │           │           │
               └───────────┼───────────┘
                           │ results
                           ▼
                    ┌─────────────┐
                    │    Redis    │
                    │  (Results)  │
                    └─────────────┘
```

## Task Types

| Task Type | Queue | Description |
|---|---|---|
| `generate_report` | default | Generates data reports |
| `send_email` | default | Sends emails via SMTP |
| `process_data` | default | Data pipeline processing |
| `web_scrape` | low_priority | Web scraping jobs |
| `critical_payment` | critical | Payment processing |
| `generic_task` | default | Fallback for unknown types |

## Setup

### Quick Start (Docker)

```bash
git clone <repo>
cd project2-task-orchestrator

cp .env.example .env

docker-compose up --build

# API docs: http://localhost:8000/docs
# Flower:   http://localhost:5555  (admin:admin)
```

### Local Development

```bash
# Start infra
docker-compose up db redis -d

# Create virtualenv
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Copy env
cp .env.example .env
# Edit DATABASE_URL and REDIS_URL to point to localhost

# Run API
uvicorn app.main:app --reload --port 8000

# Run worker (new terminal)
celery -A app.core.celery_app.celery_app worker --loglevel=info --queues=default,high_priority,low_priority,critical

# Run Flower (new terminal)
celery -A app.core.celery_app.celery_app flower --port=5555
```

## API Reference

```
POST   /api/v1/tasks                    Submit a task
GET    /api/v1/tasks                    List tasks (filterable)
GET    /api/v1/tasks/{id}               Get task details
GET    /api/v1/tasks/{id}/status        Get task status (lightweight poll)
GET    /api/v1/tasks/{id}/result        Get task result
POST   /api/v1/tasks/{id}/cancel        Cancel task
POST   /api/v1/tasks/{id}/retry         Retry failed task
GET    /api/v1/tasks/{id}/logs          Get task execution logs
DELETE /api/v1/tasks/{id}               Soft-delete task

POST   /api/v1/workflows                Create workflow (grouped tasks)

GET    /api/v1/metrics                  Queue metrics
GET    /api/v1/health                   Health check
```

### Submit Task Example

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monthly Report Q4",
    "task_type": "generate_report",
    "payload": {"report_id": "q4-2024", "report_type": "monthly"},
    "priority": "high",
    "max_retries": 3,
    "tags": ["reports", "q4"]
  }'
```

### Poll Task Status

```bash
curl http://localhost:8000/api/v1/tasks/{task_id}/status
# Returns: { "status": "running", "progress": 60, "progress_message": "Aggregating results" }
```

### Create Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily ETL Pipeline",
    "tasks": [
      {"name": "Fetch data", "task_type": "process_data", "payload": {"dataset": "users"}},
      {"name": "Send summary", "task_type": "send_email", "payload": {"to": "team@co.com"}}
    ]
  }'
```

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async PostgreSQL DSN |
| `DATABASE_SYNC_URL` | Sync PostgreSQL DSN (for Celery) |
| `CELERY_BROKER_URL` | Redis broker URL |
| `CELERY_RESULT_BACKEND` | Redis result backend URL |
| `CELERY_MAX_RETRIES` | Max retry attempts |
| `CELERY_RETRY_BACKOFF` | Seconds between retries |
| `TASK_SOFT_TIME_LIMIT` | Soft timeout (seconds) |
| `TASK_TIME_LIMIT` | Hard timeout (seconds) |
