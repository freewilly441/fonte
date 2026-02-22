import json
from pathlib import Path

DEFAULT_CONFIG = {
    "embedding_model_path": "",
    "llm_backend": "lmstudio",
    "llm_model_path": "",
    "ai_answers_enabled": "true",
    "ai_provider": "local",
    "ai_low_resource_mode": "true",
    "llm_context_window": "1536",
    "lmstudio_base_url": "http://localhost:1234/v1",
    "model_small_id": "google/gemma-3-1b",
    "model_large_id": "qwen/qwen3-1.7b",
    "temperature": "0.2",
    "max_tokens": "192",
    "timeout_seconds": "20",
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3.2:3b",
    "ollama_timeout_sec": "60",
    "device_profile": "low",
    "demo_mode": "false",
    "llm_max_tokens": "192",
    "retrieval_limit": "4",
    "model_download_url": "",
    "online_sources_enabled": "false",
    "online_cache_days": "30",
    "online_timeout_sec": "20",
    "online_user_agent": "Fonte/1.0 (+local-app)",
    "wikipedia_language": "en",
    "feature_push_notifications": "false",
    "feature_deep_linking": "false",
    "feature_referrals": "false",
    "feature_ab_testing": "false",
    "feature_premium_gating": "false",
    "feature_online_import_enabled": "true",
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
