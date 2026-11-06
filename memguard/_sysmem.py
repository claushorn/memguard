"""Free-memory reading, with no hard dependency on psutil.

`memguard` is imported by EVERY Python process on this box via its `.pth`, so it must
not drag in a heavy dependency at import time. psutil is imported lazily, inside the
call, and only on the rare path where an over-threshold file is actually being loaded.
"""
from __future__ import annotations

GB = 1024.0 ** 3


def available_gb() -> float | None:
    """Physical memory available for a new allocation, in GB. None if unobtainable.

    Returns None rather than a guess when it cannot be measured — callers must treat
    "unknown" as "do not block", never as "plenty free".
    """
    try:
        import psutil
    except Exception:
        return None
    try:
        return psutil.virtual_memory().available / GB
    except Exception:
        return None


def total_gb() -> float | None:
    """Total physical memory in GB, or None if unobtainable."""
    try:
        import psutil
    except Exception:
        return None
    try:
        return psutil.virtual_memory().total / GB
    except Exception:
        return None
