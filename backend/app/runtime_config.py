"""
In-memory runtime configuration overrides.

Settings here take precedence over env vars for the current process lifetime.
They reset on restart — that's intentional. Persistent config changes should
go in .env; these are for toggling things live without a restart.

Currently managed:
  - auto_approve: controls whether trades bypass the approval queue
"""

from app.config import get_settings

_settings = get_settings()

# Initialized from env — mutable at runtime via the settings API
_auto_approve: bool = _settings.auto_approve


def get_auto_approve() -> bool:
    return _auto_approve


def set_auto_approve(value: bool) -> None:
    global _auto_approve
    _auto_approve = value
