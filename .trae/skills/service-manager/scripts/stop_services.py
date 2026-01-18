#!/usr/bin/env python3
"""
Stop Services Script
Stops LangGraph and FastAPI services running on ports 2024 and 8000
"""

import subprocess
import sys


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


def main():
    print("🛑 Stopping Services")
    print("=" * 50)
    
    stopped = False
    stopped |= stop_service(2024, "LangGraph")
    stopped |= stop_service(8000, "FastAPI")
    
    if stopped:
        print("\n✅ All services stopped successfully")
    else:
        print("\n✅ No services were running")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
