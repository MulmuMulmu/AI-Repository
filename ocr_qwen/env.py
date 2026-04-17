from __future__ import annotations

import os
from pathlib import Path


_ENV_LOADED = False


def load_local_env(env_path: str | Path | None = None) -> Path | None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return _resolve_env_path(env_path)

    path = _resolve_env_path(env_path)
    if path is None or not path.exists():
        _ENV_LOADED = True
        return path

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_key = key.strip()
        env_value = value.strip().strip('"').strip("'")
        if env_key and env_key not in os.environ:
            os.environ[env_key] = env_value

    _ENV_LOADED = True
    return path


def _resolve_env_path(env_path: str | Path | None) -> Path | None:
    if env_path is not None:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / ".env.local"
