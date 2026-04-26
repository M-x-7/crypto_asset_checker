import threading
from pathlib import Path

import yaml

_ENDPOINTS_FILE = Path(__file__).parent.parent.parent / "config" / "endpoints.yaml"
_cache: dict | None = None
_lock = threading.Lock()


def _load() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            with open(_ENDPOINTS_FILE, "r", encoding="utf-8") as f:
                _cache = yaml.safe_load(f)
    return _cache


def get_service(key: str) -> str:
    return _load()["services"][key]


def get_chains() -> dict:
    return _load()["chains"]
