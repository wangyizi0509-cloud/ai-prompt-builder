#!/usr/bin/env python3
import os
import re
import time
import sys
import hashlib

# Configuration
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGY_LIB_DIR = os.path.join(ROOT_DIR, "Strategy_Library")

# Patterns
# Match <!-- MODULE START: path/to/file.md --> content <!-- MODULE END -->
MODULE_PATTERN = re.compile(
    r'(<!-- MODULE START: (.+?) -->)(.*?)(<!-- MODULE END -->)', 
    re.DOTALL
)

def get_file_content(path):
    """Read file content safely."""
    try:
        if not os.path.isabs(path):
            path = os.path.join(ROOT_DIR, path)
        
        if not os.path.exists(path):
            return None
            
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return None

def sync_file(file_path):
    """Sync modules in a single file."""
    content = get_file_content(file_path)
    if not content:
        return False
    
    new_content = content
    modified = False
    
    def replace_callback(match):
        nonlocal modified
        start_tag = match.group(1)
        module_rel_path = match.group(2).strip()
        current_module_content = match.group(3)
        end_tag = match.group(4)
        
        # Read the source module
        module_full_path = os.path.join(ROOT_DIR, module_rel_path)
        module_content = get_file_content(module_full_path)
        
        if module_content is None:
            print(f"  [WARN] Module not found: {module_rel_path} (referenced in {os.path.basename(file_path)})")
            return match.group(0) # Keep original if not found
            
        # Ensure module content ends with newline for cleanliness
        if not module_content.endswith('\n'):
            module_content += '\n'
            
        # Check if update is needed
        # We normalize newlines to avoid false positives
        if current_module_content.strip() != module_content.strip():
            modified = True
            # print(f"  [UPDATE] Updating module {module_rel_path}")
            return f"{start_tag}\n{module_content}{end_tag}"
        
        return match.group(0)

    # Perform replacement
    new_content = MODULE_PATTERN.sub(replace_callback, content)
    
    if modified:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"[SYNCED] {os.path.relpath(file_path, ROOT_DIR)}")
            return True
        except Exception as e:
            print(f"Error writing {file_path}: {e}")
            
    return False

def scan_and_sync():
    """Scan all md files and sync them."""
    count = 0
    # print("Scanning for updates...")
    for root, dirs, files in os.walk(STRATEGY_LIB_DIR):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                if sync_file(file_path):
                    count += 1
    return count

def get_dir_checksum():
    """Calculate a simple checksum of all file mtimes to detect changes."""
    checksum = ""
    for root, dirs, files in os.walk(STRATEGY_LIB_DIR):
        for file in files:
            if file.endswith(".md"):
                path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(path)
                    checksum += f"{path}:{mtime}|"
                except:
                    pass
    return hashlib.md5(checksum.encode('utf-8')).hexdigest()

def watch_mode():
    """Poll for changes and sync automatically."""
    print("👀 Watching for changes in Strategy_Library... (Press Ctrl+C to stop)")
    print("   Any changes to Global Modules will be automatically synced.")
    
    last_checksum = get_dir_checksum()
    
    try:
        while True:
            time.sleep(1) # Poll every second
            current_checksum = get_dir_checksum()
            
            if current_checksum != last_checksum:
                # Give a tiny buffer for write operations to complete
                time.sleep(0.1) 
                scan_and_sync()
                last_checksum = get_dir_checksum() # Update checksum after sync
                
    except KeyboardInterrupt:
        print("\nStopped watching.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        # Initial sync before watching
        scan_and_sync()
        watch_mode()
    else:
        updates = scan_and_sync()
        if updates == 0:
            print("All prompts are up to date.")
        else:
            print(f"Updated {updates} files.")
