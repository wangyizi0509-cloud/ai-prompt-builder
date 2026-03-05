#!/usr/bin/env python3
import os
import sys
from langsmith import Client

def load_env():
    # Looking for .env in the root project directory
    # Skill path: .trae/skills/langsmith-trace-analyzer/scripts/list_recent_traces.py
    # Root path: ../../../../.env
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def main():
    load_env()
    
    # Try to get project name from arg, or env
    project_arg = sys.argv[1] if len(sys.argv) > 1 else None
    project_name = project_arg or os.environ.get("LANGSMITH_PROJECT", "crushe-agent-debug")
    
    api_key = os.environ.get("LANGSMITH_API_KEY")
        print("Error: LANGSMITH_API_KEY not found in .env")
        return

    client = Client(api_key=api_key)
    
    print(f"Fetching recent traces from project: {project_name}...\n")
    
    # List top-level runs (traces)
    runs = client.list_runs(
        project_name=project_name,
        is_root=True,
        limit=10
    )
    
    print(f"{'#':<3} {'Start Time':<25} {'Run ID':<40} {'Name':<20}")
    print("-" * 90)
    
    for i, run in enumerate(runs):
        start_time = str(run.start_time)
        run_id = str(run.id)
        name = run.name or "Unnamed"
        print(f"{i+1:<3} {start_time:<25} {run_id:<40} {name:<20}")

if __name__ == "__main__":
    main()
