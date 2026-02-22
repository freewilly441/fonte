from __future__ import annotations

import hashlib
import os
import platform
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

APP_NAME = "fonte"
DEFAULT_MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m-00001-of-00001.gguf"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/enacimie/Qwen2.5-1.5B-Instruct-Q4_K_M-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m-00001-of-00001.gguf?download=true"
)
DEFAULT_MODEL_SHA256 = "3c5960d913d604bbc4a0b0b683de8a6d46d0556cec8214bb1441f6100aa7e9ce"
DEFAULT_MODEL_SIZE_BYTES = 986 * 1024 * 1024


class ModelDownloadError(RuntimeError):
    pass


class ModelDownloadCancelled(ModelDownloadError):
    pass


def resolve_model_dir(app_name: str = APP_NAME) -> Path:
    name = (app_name or APP_NAME).strip().lower()
    system = platform.system().lower()
    if system == "windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "Fonte" / "models"
        return Path.home() / "AppData" / "Roaming" / "Fonte" / "models"
    return Path.home() / ".local" / "share" / name / "models"


def default_model_path(model_dir: Path | None = None) -> Path:
    root = model_dir or resolve_model_dir()
    return root / DEFAULT_MODEL_FILENAME


def check_installed(model_path: Path | None = None) -> bool:
    path = model_path or default_model_path()
    return path.exists() and path.is_file() and path.stat().st_size > 0


def verify_checksum(path: Path, expected_sha256: str) -> bool:
    expected = (expected_sha256 or "").strip().lower()
    if not expected:
        raise ValueError("expected_sha256 is required")
    if not path.exists():
        return False
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest() == expected


def ensure_model_integrity(path: Path, expected_sha256: str) -> None:
    if not verify_checksum(path, expected_sha256):
        raise ModelDownloadError("Model checksum verification failed.")


def format_size(num_bytes: int) -> str:
    size = float(max(0, int(num_bytes)))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def estimate_time_remaining(downloaded: int, total: int, speed_bps: float) -> str:
    if total <= 0 or speed_bps <= 1:
        return "estimating..."
    remaining = max(0.0, float(total - downloaded) / speed_bps)
    if remaining < 60:
        return f"{int(remaining)}s"
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    return f"{minutes}m {seconds}s"


def download_model(
    *,
    url: str,
    dest_path: Path,
    expected_sha256: str,
    progress_callback: Callable[[int, int, float], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout_sec: int = 20,
) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    downloaded = part_path.stat().st_size if part_path.exists() else 0
    headers: dict[str, str] = {}
    if downloaded > 0:
        headers["Range"] = f"bytes={downloaded}-"
    request = urllib.request.Request(url=url, headers=headers, method="GET")
    started = time.monotonic()
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=max(5, int(timeout_sec))) as response:
            content_range = response.headers.get("Content-Range") or ""
            content_length = response.headers.get("Content-Length") or "0"
            if content_range and "/" in content_range:
                total = int(content_range.rsplit("/", 1)[-1])
            else:
                total = downloaded + int(content_length or "0")
            mode = "ab" if downloaded > 0 else "wb"
            with part_path.open(mode) as handle:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise ModelDownloadCancelled("Download cancelled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    elapsed = max(0.001, time.monotonic() - started)
                    speed = downloaded / elapsed
                    if progress_callback is not None:
                        progress_callback(downloaded, total, speed)
    except ModelDownloadCancelled:
        raise
    except Exception as exc:
        raise ModelDownloadError(f"Download failed: {exc}") from exc

    if cancel_event is not None and cancel_event.is_set():
        raise ModelDownloadCancelled("Download cancelled.")
    part_path.replace(dest_path)
    ensure_model_integrity(dest_path, expected_sha256)
    if progress_callback is not None:
        progress_callback(dest_path.stat().st_size, dest_path.stat().st_size, 0.0)
    return dest_path
