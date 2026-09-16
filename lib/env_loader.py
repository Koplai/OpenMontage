"""Environment variable loader for OpenMontage.

Loads .env file and provides typed access to environment configuration.
"""

from __future__ import annotations

import os
import json
import logging
import re
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values


_LOGGER = logging.getLogger(__name__)
_POLICY = json.loads(Path(__file__).with_name("env_policy.json").read_text(encoding="utf-8"))
_ALLOWED_KEYS = frozenset(_POLICY["allowed_keys"])
_SLUG_KEYS = frozenset(_POLICY["slug_keys"])


def dotenv_value_allowed(key: str, value: str) -> bool:
    """Project data may configure providers, not the process or credential destination."""
    return (
        key in _ALLOWED_KEYS
        and "\x00" not in value
        and (
            key not in _SLUG_KEYS
            or not value
            or re.fullmatch(r"[a-z0-9-]+", value) is not None
        )
    )


def load_env(project_root: Optional[Path] = None) -> None:
    """Load allowlisted provider data without interpolation or overriding the process."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    if env_path.is_file():
        for key, value in dotenv_values(env_path, interpolate=False).items():
            if value is None:
                continue
            if not dotenv_value_allowed(key, value):
                safe_key = key if re.fullmatch(r"[A-Z][A-Z0-9_]*", key) else "<invalid name>"
                _LOGGER.warning(
                    "Ignoring project .env variable %s: not permitted by environment policy. "
                    "Process, endpoint and credential-file settings must come from the trusted launcher.",
                    safe_key,
                )
                continue
            if not os.environ.get(key, "").strip():
                os.environ[key] = value


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get an environment variable with optional default."""
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    """Get a required environment variable. Raises if missing."""
    value = os.environ.get(key)
    if value is None or not value.strip():
        raise EnvironmentError(f"Required environment variable {key!r} is not set")
    return value
