---
name: service-manager
description: "Manage local LangGraph and FastAPI services. Use when user wants to start, restart, or stop the agent services running on ports 2024 (LangGraph) and 8000 (FastAPI). Supports starting both services together or managing them individually."
---

# Service Manager

Manage the LangGraph and FastAPI services for the Crushe AI Agent project.

## Overview

This skill provides tools to start, restart, and stop the local development services:
- **LangGraph service**: Runs on port 2024
- **FastAPI service**: Runs on port 8000

## Quick Start

To start all services:
```
scripts/start_services.py
```

To restart all services:
```
scripts/restart_services.py
```

To stop all services:
```
scripts/stop_services.py
```

## Service Management

### Start Services

Start both LangGraph and FastAPI services in the background.

**Usage:**
```bash
scripts/start_services.py
```

**What it does:**
1. Checks for existing services on ports 2024 and 8000
2. Stops any existing services to avoid conflicts
3. Starts LangGraph service using `agent_impl/start.sh`
4. Starts FastAPI service
5. Reports service status and access URLs

**Output:**
- LangGraph PID
- FastAPI PID
- Access URLs:
  - FastAPI: http://localhost:8000
  - LangGraph: http://127.0.0.1:2024
  - LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

### Restart Services

Restart all running services.

**Usage:**
```bash
scripts/restart_services.py
```

**What it does:**
1. Stops all existing services
2. Waits for processes to terminate
3. Starts services again

### Stop Services

Stop all running services.

**Usage:**
```bash
scripts/stop_services.py
```

**What it does:**
1. Finds processes using ports 2024 and 8000
2. Kills them gracefully

## Troubleshooting

### Port Already in Use

If you see "Address already in use" errors:
1. Run `scripts/stop_services.py` to clear ports
2. Verify no processes are using the ports: `lsof -i :2024 -i :8000`
3. Try starting again

### Services Not Responding

If services start but don't respond:
1. Check process status: `ps aux | grep -E "langgraph|uvicorn"`
2. Check logs in the terminal where services are running
3. Verify environment variables in `.env` file

### Service Startup Failures

If services fail to start:
1. Check Python dependencies: `pip install -r agent_impl/requirements.txt`
2. Verify LangGraph CLI is installed: `which langgraph`
3. Check `.env` file has required variables

## Resources

### scripts/start_services.py
Main script to start all services with error handling and status reporting.

### scripts/restart_services.py
Script to restart all services (stop then start).

### scripts/stop_services.py
Script to stop all running services gracefully.
