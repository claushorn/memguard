"""Guard against unbounded multi-GB data loads on a machine shared by many agents.

Armed automatically in every Python process of a venv via `memguard.pth`
(`tools/install_memguard.sh`) — there is nothing to import and nothing to remember.
The only symbol callers normally need is `full_load_allowed`, for the rare case where
a whole-file read is genuinely correct.

The box-wide OOM watchdog lives in `memguard/memwatch.py`.
"""
from ._guard import LargeDataLoadError, full_load_allowed
from ._settings import MAX_RESIDENT_GB, MIN_FREE_GB_AFTER_LOAD, is_disabled

__all__ = [
    "full_load_allowed",
    "LargeDataLoadError",
    "MAX_RESIDENT_GB",
    "MIN_FREE_GB_AFTER_LOAD",
    "is_disabled",
]
