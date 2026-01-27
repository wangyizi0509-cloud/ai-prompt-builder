#!/usr/bin/env python3
"""
Stop Services Script
Stops LangGraph and FastAPI services running on ports 2024 and 8000
"""

import subprocess
import sys
import os


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


def main():
    print("🛑 Stopping Services")
    print("=" * 50)
    
    # 1. 尝试使用官方命令停止 Docker Stack
    print("\n🐳 Stopping LangGraph Docker Stack...")
    try:
        project_root = get_project_root()
        agent_dir = os.path.join(project_root, "agent_impl")
        
        # 执行 langgraph down
        env = os.environ.copy()
        # 尝试获取 Python 用户 bin 目录以确保能找到 langgraph cli
        try:
            import site
            user_bin = os.path.join(site.getuserbase(), 'bin')
            env["PATH"] = f"{user_bin}:{env.get('PATH', '')}"
        except:
            pass
        
        subprocess.run(['langgraph', 'down'], cwd=agent_dir, env=env, check=False)
        print("✅ langgraph down command executed")
    except Exception as e:
        print(f"⚠️  Note: langgraph down failed (maybe not running): {e}")

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
