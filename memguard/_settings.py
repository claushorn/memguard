"""Tunables for the large-data load guard. One place, all env-overridable.

The rule is deliberately about ESTIMATED RESIDENT COST, not file size. Size alone is
the wrong proxy: a 0.6 GB CSV is a perfectly reasonable load that a job may genuinely
need in full, while a 0.65 GB compressed parquet can decode to ~5.8 GB resident.
Judging both by "megabytes on disk" would simultaneously block legitimate work and wave
the real bomb through.
"""
from __future__ import annotations

import os

GB = 1024.0 ** 3

#: Below this, never even estimate — the overwhelming majority of reads are small
#: CSVs, configs and metadata, and they must cost one `stat` at most.
MIN_INTERESTING_BYTES = int(os.environ.get("MEMGUARD_MIN_INTERESTING_BYTES", 100 * 1024**2))

#: One agent's fair share of a shared machine. A load estimated above this is refused
#: REGARDLESS of how much happens to be free at that instant: it is unfair to every
#: other session, and free memory can vanish between the check and the allocation.
#: This is a CEILING, not an allowance. It is also checked ONCE, from a static
#: estimate, and never re-checked as the process grows — `memguard/memwatch.py
#: --daemon` is what actually stands between an admitted load and an OOM.
MAX_RESIDENT_GB = float(os.environ.get("MEMGUARD_MAX_RESIDENT_GB", 6.0))

#: A load smaller than the cap is still refused when it would not leave this much free.
MIN_FREE_GB_AFTER_LOAD = float(os.environ.get("MEMGUARD_MIN_FREE_GB_AFTER_LOAD", 3.0))

#: ...but the crowding rule applies ONLY to loads at least this large.
#:
#: Without this floor, a nearly-full box would start refusing modest reads (a 0.1 GB
#: CSV at 3.0 GB free would raise). That is pointless: a 0.1 GB load is not what
#: exhausted the box, and refusing it frees nothing. Pressure is caused by material
#: loads, so only material loads are refused on account of it. The hard fair-share cap
#: above is independent and still applies at any size.
MIN_MATERIAL_GB = float(os.environ.get("MEMGUARD_MIN_MATERIAL_GB", 1.0))

#: Bytes-on-disk -> bytes-resident multipliers.
#:
#: CSV ~1.0: numeric text is close to break-even ("1234.5678" is 9 bytes, float64 is 8).
#:
#: Parquet ~8.0: compressed columnar on disk and expands hard on decode — a measured
#: case is a 0.70 GB parquet reaching ~5.8 GB resident.
EXPANSION_BY_SUFFIX = {
    ".csv": float(os.environ.get("MEMGUARD_CSV_EXPANSION", 1.0)),
    ".parquet": float(os.environ.get("MEMGUARD_PARQUET_EXPANSION", 8.0)),
}
DEFAULT_EXPANSION = 1.5


def expansion_for(suffix: str) -> float:
    return EXPANSION_BY_SUFFIX.get(suffix.lower(), DEFAULT_EXPANSION)


def is_disabled() -> bool:
    """True when the operator has switched the guard off.

    Deliberate, acknowledged hole: a guard defect with no override would block all
    work on the box. The mitigation is VISIBILITY, not prevention — `memguard/memwatch.py`
    reports every process it can see running with this set.
    """
    return os.environ.get("MEMGUARD_DISABLED", "") not in ("", "0", "false", "False")
