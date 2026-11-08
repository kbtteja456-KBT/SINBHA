"""
Isolated Test Server Harness for SINBHA
Spins up a temporary, loopback-only uvicorn server with:
- A unique disposable SQLite database in a temp directory
- Mocked external AI, search, and email providers (zero external requests)
- Automatic process and resource cleanup upon completion
"""

import os
import sys
import time
import socket
import tempfile
import subprocess
import shutil
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent.parent


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def isolated_test_server(port: int = None, startup_timeout: float = 20.0):
    """
    Context manager that yields (base_url, db_path, temp_dir).
    Guarantees zero database or state pollution on host system.
    """
    if port is None:
        port = get_free_port()

    temp_dir = tempfile.mkdtemp(prefix="sinbha_test_")
    db_path = Path(temp_dir) / "test_isolated.db"
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["ENV"] = "development"
    env["SINBHA_TEST_MODE"] = "1"
    env["MOCK_LLM_PROVIDERS"] = "1"
    env["MOCK_EMAIL"] = "true"
    env["SECRET_KEY"] = "isolated_test_harness_secret_key_32bytes_long"
    env["PORT"] = str(port)

    # Launch dedicated loopback uvicorn server
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    import httpx

    # Wait for /api/health to respond 200
    t0 = time.time()
    started = False
    with httpx.Client(timeout=2.0) as client:
        while time.time() - t0 < startup_timeout:
            if proc.poll() is not None:
                _, err = proc.communicate()
                raise RuntimeError(f"Server subprocess failed to start: {err.decode('utf-8', errors='ignore')}")
            try:
                r = client.get(f"{base_url}/api/health")
                if r.status_code == 200:
                    started = True
                    break
            except Exception:
                time.sleep(0.3)

    if not started:
        proc.terminate()
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise TimeoutError(f"Server at {base_url} did not become ready within {startup_timeout}s")

    try:
        yield {
            "base_url": base_url,
            "port": port,
            "db_path": str(db_path),
            "temp_dir": temp_dir,
            "env": env,
        }
    finally:
        # Graceful shutdown
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        # Cleanup disposable database directory
        shutil.rmtree(temp_dir, ignore_errors=True)

