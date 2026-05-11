import os
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    app_path = Path(__file__).with_name("agent_app.py")
    os.chdir(app_path.parent)
    command = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    raise SystemExit(subprocess.call(command, cwd=str(app_path.parent)))
