import subprocess
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script(script_name):
    script_path = os.path.join(BASE_DIR, script_name)
    print(f"--- Starting: {script_name} ---")
    
    result = subprocess.run(["python3.10", script_path], capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
        
    if result.returncode != 0:
        print(f"Error running {script_name}:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
    else:
        print(f"--- Finished: {script_name} successfully ---")

if __name__ == "__main__":
    run_script("stockUpdates.py")
    run_script("stockAlertsEmail.py")