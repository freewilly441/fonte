from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Callable

import requests

LMS_PORT = 1234
API_URL = f"http://localhost:{LMS_PORT}/v1/models"
MODELS = [
    "google/gemma-3-1b",
    "qwen/qwen3-1.7b",
]


def _run(cmd: str) -> None:
    subprocess.run(
        cmd,
        shell=True,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_server_start() -> None:
    subprocess.Popen(
        f"lms server start --port {LMS_PORT}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def ensure_lms_cli() -> None:
    if shutil.which("lms") is None:
        raise RuntimeError("LM Studio CLI not found. Please install LM Studio.")


def server_status() -> bool:
    result = subprocess.run(
        "lms server status --json --quiet",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
        return bool(data.get("running", False))
    except Exception:
        return False


def runtime_healthy() -> bool:
    try:
        response = requests.get(API_URL, timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def loaded_models() -> list[str]:
    result = subprocess.run(
        "lms ps --json",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
    except Exception:
        return []

    models: list[str] = []
    if isinstance(data, list):
        for model in data:
            if isinstance(model, dict) and "id" in model:
                models.append(str(model["id"]))
    return models


def _wait_for_api(retries: int = 30, delay_seconds: float = 1.0) -> bool:
    for _ in range(retries):
        if runtime_healthy():
            return True
        time.sleep(delay_seconds)
    return False


def _restart_server() -> None:
    _run("lms server stop")
    _run_server_start()


def _ensure_models_loaded() -> None:
    loaded = loaded_models()
    for model in MODELS:
        if model not in loaded:
            _run(f"lms load {model}")


def shutdown_runtime() -> None:
    subprocess.run(
        "lms server stop",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def bootstrap_runtime(status_callback: Callable[[str], None] | None = None) -> None:
    ensure_lms_cli()

    if not server_status():
        if status_callback is not None:
            status_callback("Initializing AI runtime...")
        _run("lms daemon up")
        if status_callback is not None:
            status_callback("Starting inference engine...")
        _run_server_start()
    if not runtime_healthy():
        # Allow short warmup before declaring runtime unhealthy.
        if not _wait_for_api(retries=5, delay_seconds=1.0):
            if status_callback is not None:
                status_callback("Initializing AI runtime...")
            if status_callback is not None:
                status_callback("Starting inference engine...")
            _restart_server()

    if status_callback is not None:
        status_callback("Loading models...")
    _ensure_models_loaded()

    if not _wait_for_api():
        raise RuntimeError("LM Studio server failed to start")
