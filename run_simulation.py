"""
Convenience launcher to run the RE-TWIN Real-Time CAN simulation.
Works from the root folder or subfolder.
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_DIR = ROOT / "RE-TWIN" if (ROOT / "RE-TWIN").exists() else ROOT

if __name__ == "__main__":
    script = PROJECT_DIR / "src" / "realtime_pipeline.py"
    cmd = [sys.executable, str(script)] + sys.argv[1:]
    print(f"Starting RE-TWIN Real-Time CAN Simulation Stream...")
    print(f"Command: {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd, cwd=str(PROJECT_DIR))
    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")
