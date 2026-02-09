#!/usr/bin/env python3
"""
Start Services Script
Starts LangGraph and FastAPI services for Crushe AI Agent project
"""

import subprocess
import sys
import time
import os
import argparse


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


def get_lan_ip():
    """
    Best-effort LAN IP detection for iOS/device testing.
    Uses a UDP connect trick (no packets necessarily sent) to infer the outbound interface IP.
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Start Crushe AI Agent services")
    parser.add_argument(
        "--mode", 
        choices=["dev", "up"], 
        default="dev", 
        help="Startup mode: 'dev' (lightweight) or 'up' (Docker Stack)"
    )
    args = parser.parse_args()

    print(f"🚀 Starting Services (Mode: {args.mode.upper()})")
    print("=" * 50)
    
    # Get to project root directory
    script_path = os.path.abspath(__file__)
    parent_dir = os.path.dirname(script_path)
    skill_dir = os.path.dirname(parent_dir)
    skills_dir = os.path.dirname(skill_dir)
    trae_dir = os.path.dirname(skills_dir)
    project_root = os.path.dirname(trae_dir)
    
    # Determine port and script based on mode
    lg_port = 2024 if args.mode == "dev" else 8123
    start_script_name = "start_dev.sh" if args.mode == "dev" else "start_up.sh"
    
    # Check and stop existing services
    print("\n🔍 Checking for existing services...")
    has_existing = False
    has_existing = has_existing or stop_service(lg_port, f"LangGraph ({args.mode})")
    has_existing = has_existing or stop_service(8000, "FastAPI")
    
    if has_existing:
        print("✅ Existing services stopped\n")
    else:
        print("✅ No existing services found\n")
    
    # Start services
    start_script = os.path.join(project_root, 'agent_impl', start_script_name)
    
    if not os.path.exists(start_script):
        print(f"❌ Error: Start script not found at {start_script}")
        return 1
    
    print(f"🚀 Starting services using agent_impl/{start_script_name}...")
    try:
        # 使用 Popen 运行以保持在后台
        # IMPORTANT: do not pipe stdout/stderr here.
        # This script exits immediately after spawning the bash script; if we pipe and do not
        # actively drain the pipe, child processes (LangGraph / Uvicorn) can block once the
        # pipe buffer fills, making the server appear "hung" (no responses).
        subprocess.Popen(['bash', start_script], cwd=project_root)
        
        print(f"✅ Services start command issued successfully! (Mode: {args.mode})")
        print("\n📊 Service Information:")
        print("   - FastAPI: http://localhost:8000")
        lan_ip = get_lan_ip()
        if lan_ip:
            print(f"   - iOS/Device (LAN): http://{lan_ip}:8000")
        print(f"   - LangGraph: http://127.0.0.1:{lg_port} ({'Local' if args.mode == 'dev' else 'Docker'})")
        print(f"   - LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:{lg_port}")
        
        if args.mode == "up":
            print("\n💡 Services are running in the background via Docker Stack.")
        else:
            print("\n💡 Services are running in the background (Local Dev).")
            
        print("   Use '.trae/skills/service-manager/scripts/stop_services.py' to stop them.")
        print("   Use '.trae/skills/service-manager/scripts/restart_services.py' to restart them.")
        
        return 0
    except Exception as e:
        print(f"❌ Error starting services: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
