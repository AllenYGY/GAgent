"""
Springer Nature API configuration.
"""

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Optional


@dataclass(slots=True)
class SpringerSettings:
    """Springer Nature API keys."""

    meta_api_key: Optional[str] = None
    openaccess_api_key: Optional[str] = None


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value is None:
        return default
    value = value.strip()
    return value or default


@lru_cache(maxsize=1)
def get_springer_settings() -> SpringerSettings:
    """Read environment variables and return SpringerSettings."""

    meta_api_key = _env("SPRINGER_META_API_KEY")
    openaccess_api_key = _env("SPRINGER_OPENACCESS_API_KEY")

    return SpringerSettings(
        meta_api_key=meta_api_key,
        openaccess_api_key=openaccess_api_key,
    )


def reset_springer_settings_cache() -> None:
    """Clear cached Springer settings (tests)."""

    get_springer_settings.cache_clear()  # type: ignore[attr-defined]
