"""Opt-in browser tests: SFINCS_E2E=1 micromamba run -n shiny python -m pytest app/e2e -q"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]

if os.environ.get("SFINCS_E2E") != "1":
    collect_ignore_glob = ["test_*.py"]


@pytest.fixture(scope="session")
def app_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "SFINCS_DATA_DIR": "/home/razinka/sfincs/curonian"}
    proc = subprocess.Popen([sys.executable, "-m", "shiny", "run", "--port", str(port), "app.py"],
                            cwd=APP_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("app did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)
