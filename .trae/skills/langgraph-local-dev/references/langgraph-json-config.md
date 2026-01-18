# `langgraph.json` Configuration Reference

The `langgraph.json` file is the central configuration for your LangGraph application. It defines your graphs, dependencies, and environment.

## File Structure

```json
{
  "graphs": {
    "my_agent": "./src/agent.py:graph"
  },
  "dependencies": [
    "."
  ],
  "env": ".env",
  "python_version": "3.11",
  "dockerfile_lines": [
    "RUN apt-get update && apt-get install -y libmagic-dev"
  ]
}
```

## Key Fields

### `graphs`
A map of graph IDs to their entry points. The entry point is specified as `path/to/file.py:variable_name`.

### `dependencies`
A list of dependencies required for the application.
- `.` indicates the current directory.
- Can also include `pyproject.toml`, `requirements.txt`, or `package.json`.

### `env`
Path to the environment variables file (e.g., `.env`).

### `python_version`
The Python version to use in the Docker container (for `langgraph up` and production).

### `dockerfile_lines`
Custom instructions to add to the generated Dockerfile.

## Dependency Management

- **`langgraph dev`**: Runs code directly in your local environment. You must ensure dependencies are installed in your active Python/Node.js environment.
- **`langgraph up`**: Builds a Docker container and installs dependencies inside it based on `langgraph.json`.

### Recommended Practice
Keep your local environment in sync with your containerized environment by using the same dependency files (e.g., `requirements.txt`) in both places.
