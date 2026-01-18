#!/usr/bin/env python3
"""
Restart Services Script
Restarts LangGraph and FastAPI services
"""

import subprocess
import sys
import os


def main():
    print("🔄 Restarting Services")
    print("=" * 50)
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Stop services
    print("\n🛑 Stopping services...")
    stop_script = os.path.join(script_dir, 'stop_services.py')
    try:
        subprocess.run(['python3', stop_script], check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: Stop script failed: {e}")
    
    # Start services
    print("\n🚀 Starting services...")
    start_script = os.path.join(script_dir, 'start_services.py')
    try:
        subprocess.run(['python3', start_script], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: Start script failed: {e}")
        return 1
    
    print("\n✅ Services restarted successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
