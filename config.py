import json
from pathlib import Path

DEFAULT_CONFIG = {
    "embedding_model_path": "",
    "llm_model_path": "",
    "device_profile": "low",
    "demo_mode": "false",
    "llm_max_tokens": "192",
    "retrieval_limit": "4",
    "model_download_url": "",
}


def load_config(path: Path, *, return_ok: bool = False):
    ok = False
    if not path.exists():
        ok = False
        cfg = DEFAULT_CONFIG.copy()
        return (cfg, ok) if return_ok else cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        ok = False
        cfg = DEFAULT_CONFIG.copy()
        return (cfg, ok) if return_ok else cfg
    ok = True
    cfg = DEFAULT_CONFIG.copy()
    cfg.update({k: str(v) for k, v in data.items()})
    return (cfg, ok) if return_ok else cfg


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
