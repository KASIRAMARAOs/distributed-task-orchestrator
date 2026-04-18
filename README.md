# ⚙️ Distributed Task & Workflow Orchestrator

A production-grade distributed task processing system that enables asynchronous execution, priority-based scheduling, workflow orchestration, and real-time monitoring using Celery, Redis, and FastAPI.

---

## 💡 Key Highlights

* ⚡ Asynchronous distributed task execution using Celery
* 🎯 Priority-based scheduling with multiple queues (critical → low)
* 🔄 Automatic retry with exponential backoff for fault tolerance
* 📊 Real-time task progress tracking (0–100%)
* 🧩 Workflow orchestration for grouped task execution
* 📡 Scalable architecture with multiple workers
* 🏗 Built as a production-style distributed backend system

---

## 🚀 Features

* Distributed task execution across multiple workers
* 4 priority queues: critical, high, normal, low
* Retry mechanism with exponential backoff
* Workflow support (task grouping & chaining)
* Real-time progress tracking
* Persistent task storage in PostgreSQL
* Flower dashboard for monitoring
* Scheduled tasks using Celery Beat
* Structured logging
* REST API with OpenAPI documentation

---

## 🛠 Tech Stack

| Layer          | Technology                    |
| -------------- | ----------------------------- |
| Backend API    | FastAPI, Uvicorn              |
| Task Queue     | Celery                        |
| Broker         | Redis                         |
| Result Backend | Redis                         |
| Database       | PostgreSQL (SQLAlchemy async) |
| Monitoring     | Flower                        |
| DevOps         | Docker, Docker Compose        |

---

## 🧠 System Architecture

```id="arch-task"
Client → FastAPI API → Redis Broker → Celery Workers → Redis (Results) → PostgreSQL
```

---

## 🔄 Task Execution Pipeline

```id="pipeline-task"
Client Request
     │
     ▼
FastAPI API (Validate + Create Task)
     │
     ▼
Push Task → Redis Broker
     │
     ▼
Celery Worker Picks Task
     │
     ▼
Execute Task Logic
     │
     ▼
Store Result → Redis + PostgreSQL
     │
     ▼
Client Polls Status / Result
```

---

## 🔄 Priority Queue Processing

```id="pipeline-priority"
Tasks → Queue Selection
         │
         ├── Critical Queue
         ├── High Priority Queue
         ├── Normal Queue
         └── Low Priority Queue
                │
                ▼
        Dedicated Workers Process Tasks
```

---

## 🔄 Workflow Orchestration Pipeline

```id="pipeline-workflow"
Workflow Request
     │
     ▼
Create Workflow (Group Tasks)
     │
     ▼
Submit Tasks to Queue
     │
     ▼
Execute Tasks (Sequential / Parallel)
     │
     ▼
Aggregate Results
     │
     ▼
Return Workflow Status
```

---

## 🔄 Retry & Fault Tolerance

```id="pipeline-retry"
Task Execution
     │
     ▼
Failure Detected
     │
     ▼
Retry with Backoff
     │
     ▼
Max Retries Reached?
     │        │
     │ Yes    │ No
     ▼        ▼
Mark Failed  Retry Again
```

---

## 🧠 Core System Design Concepts

### ⚡ Asynchronous Processing

* Tasks executed in background
* API remains non-blocking
* Improves system responsiveness

---

### 🎯 Priority Scheduling

* Critical tasks processed first
* Prevents starvation of high-priority jobs
* Ensures SLA compliance

---

### 🔄 Fault Tolerance

* Automatic retries
* Backoff strategy prevents overload
* Persistent task state ensures recovery

---

### 📈 Horizontal Scaling

* Add more workers to increase throughput
* Stateless API allows scaling
* Redis enables distributed coordination

---

## ⚙️ Setup Instructions

### 🔧 Prerequisites

* Docker & Docker Compose

---

### 🚀 Quick Start

```bash id="setup-task1"
git clone https://github.com/KASIRAMARAOs/distributed-task-orchestrator.git
cd distributed-task-orchestrator

cp .env.example .env

docker-compose up --build
```

👉 API Docs: http://localhost:8000/docs
👉 Flower: http://localhost:5555

---

### 💻 Local Development

```bash id="setup-task2"
docker-compose up db redis -d

pip install -r requirements.txt

uvicorn app.main:app --reload

celery -A app.core.celery_app worker \
  --loglevel=info \
  --queues=default,high_priority,low_priority,critical

celery -A app.core.celery_app flower --port=5555
```

---

## 🔌 API Endpoints

```id="api-task"
POST   /api/v1/tasks
GET    /api/v1/tasks
GET    /api/v1/tasks/{id}
GET    /api/v1/tasks/{id}/status
GET    /api/v1/tasks/{id}/result
POST   /api/v1/tasks/{id}/cancel
POST   /api/v1/tasks/{id}/retry
GET    /api/v1/tasks/{id}/logs

POST   /api/v1/workflows

GET    /api/v1/metrics
GET    /api/v1/health
```

---

## 📊 Example

### Submit Task

```bash id="example-task"
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"task_type": "generate_report"}'
```

---

## 📈 Scalability Considerations

* Multiple workers process tasks in parallel
* Redis handles distributed task queue
* PostgreSQL ensures persistence
* Can scale to high throughput systems

---

## 📌 Future Improvements

* DAG-based workflow engine
* Distributed tracing (OpenTelemetry)
* Kafka-based event streaming
* Auto-scaling workers

---

## 👨‍💻 Author

**Kasi Sripalasetty**
