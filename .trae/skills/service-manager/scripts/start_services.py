#!/usr/bin/env python3
"""
Start Services Script
Starts LangGraph and FastAPI services for Crushe AI Agent project
"""

import subprocess
import sys
import time
import os


def get_processes_on_port(port):
    """Get PIDs of processes using specified port"""
    try:
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            return [int(pid) for pid in result.stdout.strip().split('\n')]
        return []
    except Exception as e:
        print(f"Error checking port {port}: {e}")
        return []


def stop_service(port, service_name):
    """Stop services on given port"""
    pids = get_processes_on_port(port)
    if not pids:
        return False

    print(f"🔧 Stopping existing {service_name} service (PIDs: {', '.join(map(str, pids))})...")
    for pid in pids:
        try:
            subprocess.run(['kill', '-9', str(pid)], check=True)
        except subprocess.CalledProcessError:
            pass
    
    time.sleep(1)
    return True


def main():
    print("🚀 Starting Services")
    print("=" * 50)
    
    # Get to project root directory
    script_path = os.path.abspath(__file__)
    parent_dir = os.path.dirname(script_path)
    skill_dir = os.path.dirname(parent_dir)
    skills_dir = os.path.dirname(skill_dir)
    trae_dir = os.path.dirname(skills_dir)
    project_root = os.path.dirname(trae_dir)
    
    # Check and stop existing services
    print("\n🔍 Checking for existing services...")
    has_existing = False
    has_existing = has_existing or stop_service(2024, "LangGraph")
    has_existing = has_existing or stop_service(8000, "FastAPI")
    
    if has_existing:
        print("✅ Existing services stopped\n")
    else:
        print("✅ No existing services found\n")
    
    # Start services
    start_script = os.path.join(project_root, 'agent_impl', 'start.sh')
    
    if not os.path.exists(start_script):
        print(f"❌ Error: Start script not found at {start_script}")
        return 1
    
    print("🚀 Starting services using agent_impl/start.sh...")
    try:
        process = subprocess.Popen(
            ['bash', start_script],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        print("✅ Services started successfully!")
        print("\n📊 Service Information:")
        print("   - FastAPI: http://localhost:8000")
        print("   - LangGraph: http://127.0.0.1:2024")
        print("   - LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024")
        print("\n💡 Services are running in the background.")
        print("   Use 'scripts/stop_services.py' to stop them.")
        print("   Use 'scripts/restart_services.py' to restart them.")
        
        return 0
    except Exception as e:
        print(f"❌ Error starting services: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
