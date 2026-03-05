#!/usr/bin/env python3
import os
import sys
from langsmith import Client

def load_env():
    # Looking for .env in the root project directory
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
    
    # Try to get thread_id from arg 1, project from arg 2
    thread_id = sys.argv[1] if len(sys.argv) > 1 else None
    project_arg = sys.argv[2] if len(sys.argv) > 2 else None
    project_name = project_arg or os.environ.get("LANGSMITH_PROJECT", "Crushe2-0")
    
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        print("Error: LANGSMITH_API_KEY not found")
        return

    client = Client(api_key=api_key)
    
    if not thread_id:
        print("Usage: python scripts/inspect_by_thread.py <thread_id>")
        # Also list recent threads if no ID provided
        print(f"\nListing recent traces in project: {project_name}...")
        runs = list(client.list_runs(project_name=project_name, is_root=True, limit=10))
        print(f"{'#':<3} {'Start Time':<25} {'Run ID':<40} {'Thread ID (Metadata)':<20}")
        for i, run in enumerate(runs):
            tid = run.extra.get('metadata', {}).get('thread_id', 'N/A')
            print(f"{i+1:<3} {str(run.start_time):<25} {str(run.id):<40} {tid:<20}")
        return

    print(f"Searching for traces for thread_id: {thread_id} in project: {project_name}...")
    
    # List runs and filter in Python to avoid filter expression parsing issues
    all_runs = client.list_runs(
        project_name=project_name,
        is_root=True,
        limit=50
    )
    
    runs = [r for r in all_runs if r.extra.get('metadata', {}).get('thread_id') == thread_id]
    
    if not runs:
        # Try metadata search directly if the above didn't work (some runs might have it nested differently)
        print("No direct matches in root runs. Checking all runs in the last 100...")
        all_runs = client.list_runs(
            project_name=project_name,
            limit=100
        )
        runs = [r for r in all_runs if r.extra.get('metadata', {}).get('thread_id') == thread_id]

    if not runs:
        print("Still no runs found. Please check if the thread_id is correct or if it's stored under a different metadata key (e.g., session_id).")
        return

    print(f"\nFound {len(runs)} runs for thread_id: {thread_id}")
    print(f"{'#':<3} {'Start Time':<25} {'Run ID':<40} {'Name':<20}")
    print("-" * 90)
    for i, run in enumerate(runs):
        print(f"{i+1:<3} {str(run.start_time):<25} {str(run.id):<40} {run.name:<20}")

    print(f"\nYou can now use: python scripts/inspect_langsmith_run.py <Run ID>")

if __name__ == "__main__":
    main()
