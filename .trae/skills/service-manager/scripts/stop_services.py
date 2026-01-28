#!/usr/bin/env python3
"""
Stop Services Script
Stops LangGraph and FastAPI services running on ports 2024 and 8000
"""

import subprocess
import sys
import os


def run_command(args, cwd=None, env=None):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def get_processes_on_port(port):
    """Get PIDs of processes using the specified port"""
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
    """Stop services on the given port"""
    pids = get_processes_on_port(port)
    if not pids:
        print(f"✅ No {service_name} service found on port {port}")
        return False

    print(f"🔧 Stopping {service_name} service (PIDs: {', '.join(map(str, pids))})...")
    for pid in pids:
        try:
            subprocess.run(['kill', '-9', str(pid)], check=True)
            print(f"   ✓ Stopped PID {pid}")
        except subprocess.CalledProcessError:
            print(f"   ✗ Failed to stop PID {pid}")
    
    return True


def get_project_root():
    script_path = os.path.abspath(__file__)
    parent_dir = os.path.dirname(script_path)
    skill_dir = os.path.dirname(parent_dir)
    skills_dir = os.path.dirname(skill_dir)
    trae_dir = os.path.dirname(skills_dir)
    return os.path.dirname(trae_dir)


def stop_langgraph_docker_stack(agent_dir):
    project_name = os.path.basename(os.path.abspath(agent_dir))
    label_filters = [
        f"label=com.docker.compose.project={project_name}",
        f"label=com.docker.compose.project.working_dir={os.path.abspath(agent_dir)}",
    ]

    result = run_command(["docker", "ps", "-aq", *sum([["--filter", f] for f in label_filters], [])])
    container_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not container_ids:
        print("✅ No LangGraph Docker containers found")
        return False

    print(f"🔧 Stopping/removing Docker containers ({len(container_ids)}): {', '.join(container_ids)}")
    run_command(["docker", "rm", "-f", *container_ids])
    return True


def main():
    print("🛑 Stopping Services")
    print("=" * 50)
    
    # 1. 停止 LangGraph Up 模式（Docker Stack）
    print("\n🐳 Stopping LangGraph Docker Stack...")
    try:
        project_root = get_project_root()
        agent_dir = os.path.join(project_root, "agent_impl")
        stop_langgraph_docker_stack(agent_dir)
    except Exception as e:
        print(f"⚠️  Note: stopping Docker Stack failed (maybe not running): {e}")

    # 2. 强力清理端口
    print("\n🔍 Cleaning up remaining processes on ports...")
    stopped = False
    stopped |= stop_service(2024, "LangGraph (Dev)")
    stopped |= stop_service(8123, "LangGraph (Up)")
    stopped |= stop_service(8000, "FastAPI")
    
    if stopped:
        print("\n✅ All services stopped successfully")
    else:
        print("\n✅ No remaining services found")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
