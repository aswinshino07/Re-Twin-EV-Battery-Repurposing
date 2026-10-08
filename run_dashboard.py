"""
Launcher script to run serve_dashboard.py and open http://localhost:8050/dashboard.html directly.
"""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    server_script = ROOT / "serve_dashboard.py"
    print("Launching RE-TWIN Dashboard Server...")
    proc = subprocess.Popen([sys.executable, str(server_script)], cwd=str(ROOT))
    time.sleep(1.5)
    webbrowser.open("http://localhost:8050/dashboard.html")
    print("Dashboard opened at http://localhost:8050/dashboard.html")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
