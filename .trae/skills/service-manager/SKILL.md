---
name: service-manager
description: "Manage local LangGraph (Dev/Docker) and FastAPI services. Supports 'dev' (lightweight) and 'up' (Docker Stack) modes. Manages ports 2024/8123 and 8000."
---

# Service Manager

Manage the LangGraph and FastAPI services for the Crushe AI Agent project.

## Overview

This skill provides tools to start, restart, and stop local services in two modes:
- **Dev Mode (Local)**: Lightweight, runs on port 2024.
- **Up Mode (Docker)**: Production-like, runs on port 8123 with full Postgres/Redis stack.

## Quick Start

### Start in Dev Mode (Recommended for rapid iteration)
```bash
python3 scripts/start_services.py --mode dev
```

### Start in Up Mode (Recommended for production-readiness validation)
```bash
python3 scripts/start_services.py --mode up
```

### Stop All Services
```bash
python3 scripts/stop_services.py
```

### Restart Services
```bash
python3 scripts/restart_services.py
```

## Service Management

### Start Services

**Usage:**
```bash
python3 scripts/start_services.py [--mode {dev,up}]
```

**What it does:**
1. Checks for existing services on relevant ports (2024/8123 and 8000)
2. Stops existing services to avoid conflicts
3. Starts LangGraph service (via `start_dev.sh` or `start_up.sh`)
4. Starts FastAPI service
5. Reports service status and access URLs

**URLs:**
- **FastAPI**: http://localhost:8000
- **LangGraph Dev**: http://127.0.0.1:2024
- **LangGraph Up**: http://127.0.0.1:8123

### Stop Services

**Usage:**
```bash
python3 scripts/stop_services.py
```

**What it does:**
1. Runs `langgraph down` to stop Docker containers (if any)
2. Kills processes on ports 2024, 8123, and 8000

## Troubleshooting

### Docker Issues (Up Mode only)
1. Ensure Docker Desktop is running
2. Run `docker ps` to verify connection

### Port Conflicts
If you see "Address already in use":
1. Run `python3 scripts/stop_services.py`
2. Manually check: `lsof -i :2024 -i :8123 -i :8000`

## Resources

### scripts/start_services.py
Main script to start all services with error handling and status reporting.

### scripts/restart_services.py
Script to restart all services (stop then start).

### scripts/stop_services.py
Script to stop all running services gracefully.
