"""The rule: an over-threshold file may not be materialized whole without an opt-in.

Why this exists as a RUNTIME guard rather than a policy, a lint rule, or a review
checklist: the dominant failure mode on a shared agent machine is the throwaway
analysis script an agent writes and runs once. No static check can reach that script,
and an advisory rule must be RECALLED by an agent optimising for its own task. This
fires without cooperation.
"""
from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
from typing import Any, Optional

from ._settings import (
    MAX_RESIDENT_GB,
    MIN_FREE_GB_AFTER_LOAD,
    MIN_INTERESTING_BYTES,
    MIN_MATERIAL_GB,
    expansion_for,
    is_disabled,
)
from ._sysmem import available_gb

GB = 1024.0 ** 3


class LargeDataLoadError(MemoryError):
    """Raised when a load would materialize an over-threshold file whole.

    Subclasses MemoryError because that is what this prevents: callers with an
    existing `except MemoryError` fallback behave sensibly.
    """


# Re-entrant, per-thread opt-in depth. Thread-local because a prefetch thread
# (`utils.prefetch_iterator.prefetch_map`) must not inherit the main thread's
# permission — each thread states its own intent.
_optin = threading.local()


def _optin_depth() -> int:
    return getattr(_optin, "depth", 0)


@contextlib.contextmanager
def full_load_allowed(reason: str, est_gb: Optional[float] = None):
    """Permit whole-file loads in this thread for the duration of the block.

    Parameters
    ----------
    reason : str
        Why a whole-file read is genuinely correct here (e.g. "this job writes
        the file; must read whole"). Recorded in any error raised inside the block and
        visible at the call site during review.
    est_gb : float, optional
        Expected resident cost of the load, in GB. When given, it is CHECKED against
        currently-available memory: a sanctioned full load must still not fire into an
        already-full box, or the escape hatch would simply reintroduce the crash for
        the legitimate cases.

    Raises
    ------
    LargeDataLoadError
        If `est_gb` would not fit with `MIN_FREE_GB_AFTER_LOAD` to spare.

    Notes
    -----
    `git grep full_load_allowed` enumerates every sanctioned whole-file load in the
    repo. That inventory is the point: it is what makes the memory budget auditable.
    """
    if not reason or not str(reason).strip():
        raise ValueError("full_load_allowed requires a non-empty reason")

    if est_gb is not None and not is_disabled():
        free = available_gb()
        if free is not None and (free - est_gb) < MIN_FREE_GB_AFTER_LOAD:
            raise LargeDataLoadError(
                f"full_load_allowed({reason!r}, est_gb={est_gb}) REFUSED — not enough "
                f"free memory right now.\n"
                f"  declared cost : {est_gb:.2f} GB\n"
                f"  free now      : {free:.2f} GB\n"
                f"  would leave   : {free - est_gb:.2f} GB "
                f"(minimum {MIN_FREE_GB_AFTER_LOAD:.2f} GB)\n"
                f"This box is shared by many agents. Wait for the box to drain "
                f"(`memguard/memwatch.py` shows who holds it), or load a bounded "
                f"window instead."
            )

    _optin.depth = _optin_depth() + 1
    _optin.reason = reason
    try:
        yield
    finally:
        _optin.depth = _optin_depth() - 1


def _resolve_path(value: Any) -> Optional[Path]:
    """Return `value` as an existing local file path, else None.

    Buffers, URLs, file-like objects, globs and directories are all None — the guard
    only speaks about local files whose size it can stat.
    """
    if isinstance(value, (str, os.PathLike)):
        try:
            p = Path(value)
        except Exception:
            return None
        if "://" in str(value):
            return None
        try:
            return p if p.is_file() else None
        except OSError:
            return None
    return None


def _canonical_advice(path: Path) -> str:
    """The bounded alternative for THIS file kind, so the error is a fix.

    The guard's value depends on recovery being cheaper than the workaround; an agent
    that hits this must be handed the right call, not a puzzle.
    """
    if path.suffix == ".parquet":
        return (
            "  Read a column subset and/or row-group batches rather than the whole file:\n"
            "      import pyarrow.parquet as pq\n"
            "      for batch in pq.ParquetFile(path).iter_batches(columns=[...]):\n"
            "          ..."
        )

    return (
        "  Read it in bounded chunks and accumulate only what you need:\n"
        "      for chunk in pd.read_csv(path, chunksize=100_000):\n"
        "          ..."
    )


def check_load(path_arg: Any, kwargs: dict, *, reader: str) -> None:
    """Raise LargeDataLoadError if this load would take an unsafe share of the box.

    Two independent refusals, for two different harms:

    1. **Over one agent's fair share** (`MAX_RESIDENT_GB`) — refused unconditionally.
       Free memory at this instant is irrelevant: the load is unfair to the other ~19
       sessions, and whatever is free can be claimed by them before this allocation
       completes.
    2. **Would not leave the box a working margin** (`MIN_FREE_GB_AFTER_LOAD`) — refused
       for now. A load that is fine on an idle box is not fine on a full one; this is
       the same contract as a failing `malloc`, and it is deliberately conditional.

    Cheap by construction: one `os.stat` on the fast path, and an early return when the
    caller already declared a bound.
    """
    if is_disabled() or _optin_depth() > 0:
        return

    if _declared_bound(kwargs) is not None:
        return

    path = _resolve_path(path_arg)
    if path is None:
        return

    try:
        size = path.stat().st_size
    except OSError:
        return
    if size < MIN_INTERESTING_BYTES:
        return

    est_gb = (size / GB) * expansion_for(path.suffix)
    free = available_gb()

    over_cap = est_gb > MAX_RESIDENT_GB
    crowds_box = (
        est_gb >= MIN_MATERIAL_GB
        and free is not None
        and (free - est_gb) < MIN_FREE_GB_AFTER_LOAD
    )
    if not (over_cap or crowds_box):
        return

    if over_cap:
        headline = (
            f"this load alone is estimated at {est_gb:.1f} GB, over the "
            f"{MAX_RESIDENT_GB:.1f} GB one agent may fairly take on a box "
            f"shared by many sessions"
        )
    else:
        headline = (
            f"this load is estimated at {est_gb:.1f} GB and only {free:.1f} GB is free "
            f"right now — it would leave the box under its {MIN_FREE_GB_AFTER_LOAD:.1f} "
            f"GB working margin. The box is busy; this may succeed later"
        )

    raise LargeDataLoadError(
        f"\n"
        f"MEMGUARD: refusing {reader}() — {headline}.\n"
        f"\n"
        f"  file      : {path}\n"
        f"  on disk   : {size / GB:.2f} GB\n"
        f"  estimated : {est_gb:.1f} GB resident "
        f"({expansion_for(path.suffix):g}x for {path.suffix or 'this format'})\n"
        f"  free now  : {f'{free:.1f} GB' if free is not None else 'unknown'}\n"
        f"\n"
        f"{_canonical_advice(path)}\n"
        f"\n"
        f"If this whole-file read is genuinely correct and sized right, say so:\n"
        f"      from memguard import full_load_allowed\n"
        f"      with full_load_allowed('why this must be read whole', est_gb={est_gb:.1f}):\n"
        f"          ...\n"
        f"(That records the reason, still refuses when the box has no room, and keeps\n"
        f" every sanctioned full load greppable: `git grep full_load_allowed`.)\n"
    )


def _declared_bound(kwargs: dict) -> Optional[str]:
    """Name of the bound the caller declared, or None if the call is unbounded.

    `usecols` / `columns` deliberately do NOT count. A three-column subset of a 6.4 GB
    CSV is still several hundred MB, and admitting a size-estimation heuristic here
    would reintroduce exactly the judgement call this guard exists to remove. A caller
    who has established that a subset is small uses `full_load_allowed(est_gb=...)`.
    """
    for key in ("chunksize", "nrows"):
        if kwargs.get(key) is not None:
            return key
    if kwargs.get("iterator"):
        return "iterator"
    return None
