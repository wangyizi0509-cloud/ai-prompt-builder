# LangGraph Local Development & Testing Guide

This guide covers the local development tools and workflows for building and testing LangGraph applications.

## Overview

LangGraph provides two primary CLI commands for local development:

1.  **`langgraph dev`**: A lightweight development server for rapid iteration.
2.  **`langgraph up`**: A production-like testing environment using Docker for validation.

### Comparison Table

| Feature | `langgraph dev` | `langgraph up` |
| :--- | :--- | :--- |
| **Docker Required** | No | Yes |
| **Installation** | `pip install langgraph-cli[inmem]` | `pip install langgraph-cli` |
| **Primary Use Case** | Rapid development & testing | Production-like validation |
| **State Persistence** | In-memory & local directory | PostgreSQL |
| **Hot Reloading** | Yes (default) | Optional (`--watch` flag) |
| **Default Port** | 2024 | 8123 |
| **Resource Usage** | Lightweight | Heavier (Docker containers) |
| **IDE Debugging** | Built-in DAP support | Regular container debugging |

---

## `langgraph dev`

The `langgraph dev` command runs a lightweight server directly in your environment.

### Key Features
- **No Docker required**: Runs directly in your environment.
- **Hot reloading**: Automatically reloads when you change code.
- **Fast startup**: Ready in seconds.
- **DAP Support**: Attach your IDE debugger using `--debug-port`.
- **Local storage**: State is persisted to a local directory.

### Getting Started
```bash
# Install with inmem extra
pip install -U "langgraph-cli[inmem]"

# Start dev server
langgraph dev
```
The server starts at `http://localhost:2024` with hot reloading enabled.

---

## `langgraph up`

The `langgraph up` command orchestrates a full Docker-based stack that mirrors production infrastructure.

### Key Features
- **Verify build & dependencies**: Tests your build process.
- **Isolated networking**: Realistic container networking.
- **Production validation**: Verifies deployment readiness.

### Getting Started
```bash
# Ensure Docker is running
docker ps

# Start production-like stack
langgraph up
```
The server starts at `http://localhost:8123` with full persistent storage.

---

## Typical Workflow

1.  **Daily Development**: Use `langgraph dev` for rapid iteration.
2.  **Periodic Validation**: Test major changes with `langgraph up`.
3.  **Pre-deployment Check**: Run `langgraph up --recreate` for a fresh build.
4.  **Deploy**: Push to production via LangSmith UI or Control Plane API.

---

## Pre-deployment Checklist

Before deploying, verify the following with `langgraph up`:
- [ ] All dependencies install correctly in the container.
- [ ] Application starts without errors.
- [ ] Graph executes successfully.
- [ ] All environment variables work correctly.
- [ ] Authentication/authorization works as expected.
