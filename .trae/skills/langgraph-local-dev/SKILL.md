---
name: langgraph-local-dev
description: "Guidance for local development, testing, and debugging of LangGraph applications using the LangGraph CLI. Use this skill when you need to: (1) Set up a local development environment for LangGraph, (2) Understand the differences between `langgraph dev` and `langgraph up`, (3) Debug Docker setup issues for LangGraph, (4) Configure `langgraph.json`, or (5) Follow best practices for LangGraph development workflows."
---

# LangGraph Local Development

This skill provides comprehensive guidance for developing and testing LangGraph applications locally using the LangGraph CLI.

## Overview

Local development in LangGraph revolves around two primary tools provided by the CLI: `langgraph dev` for rapid iteration and `langgraph up` for production-like validation.

For a detailed comparison and setup guide, see [langgraph-local-dev-guide.md](references/langgraph-local-dev-guide.md).

## Core Commands

### 1. `langgraph dev` (Lightweight Development)
Use this for daily feature development and fast prototyping.
- **Workflow**:
  1. Install CLI: `pip install -U "langgraph-cli[inmem]"`
  2. Start server: `langgraph dev`
  3. Iterate with hot reloading at `http://localhost:2024`.
- **Debugging**: Attach an IDE debugger using the `--debug-port` flag.

### 2. `langgraph up` (Production Validation)
Use this to verify your Docker build, dependencies, and environment configuration.
- **Workflow**:
  1. Ensure Docker is running.
  2. Start stack: `langgraph up`
  3. Validate at `http://localhost:8123`.
- **Pre-deployment**: Run `langgraph up --recreate` to ensure a clean build.

## Configuration

The `langgraph.json` file is required for both commands. It defines your graphs, dependencies, and environment.

For a full reference on configuration options, see [langgraph-json-config.md](references/langgraph-json-config.md).

## Recommended Workflow

| Phase | Tool | Purpose |
| :--- | :--- | :--- |
| **Iterate** | `langgraph dev` | Rapid code changes and logic testing. |
| **Validate** | `langgraph up` | Verify Docker build and persistence. |
| **Pre-deploy** | `langgraph up --recreate` | Final check of dependencies and environment. |

## Troubleshooting & Debugging

If you encounter issues:
1. **Dependency Errors**: Check the `dependencies` field in `langgraph.json`. Ensure they are installed locally for `dev` and correctly specified for `up`.
2. **Docker Issues**: Use `langgraph up` to catch networking or environment variable problems that only appear in containers.
3. **State Issues**: Remember that `langgraph dev` uses in-memory/local storage, while `langgraph up` uses a full PostgreSQL instance.
