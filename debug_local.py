import os
from pathlib import Path
import sys

from streamlit.web import cli as stcli


if __name__ == "__main__":
    app_path = Path(__file__).with_name("agent_app.py")
    os.chdir(app_path.parent)
    sys.argv = ["streamlit", "run", str(app_path)]
    raise SystemExit(stcli.main())
