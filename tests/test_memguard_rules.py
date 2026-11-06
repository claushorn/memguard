"""The decision rule: what is refused, what passes, and why.

These exercise `check_load` directly (no subprocess) so each branch is pinned
independently of the delivery mechanism, which `test_memguard_armed.py` owns.
"""
from __future__ import annotations

import pytest

from memguard import LargeDataLoadError, full_load_allowed
from memguard import _guard, _settings


@pytest.fixture
def big_csv(tmp_path):
    """A file whose SIZE is large enough to be interesting under a lowered floor."""
    path = tmp_path / "big_table.csv"
    path.write_bytes(b"datetime,close\n" + b"y" * (4 * 1024 * 1024))
    return path


@pytest.fixture(autouse=True)
def small_thresholds(monkeypatch):
    """1 MB floor, 1 MB cap — exercises the real branches without multi-GB fixtures."""
    monkeypatch.setattr(_guard, "MIN_INTERESTING_BYTES", 1024 * 1024)
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 0.001)
    monkeypatch.setattr(_guard, "MIN_FREE_GB_AFTER_LOAD", 0.0)
    monkeypatch.setattr(_guard, "MIN_MATERIAL_GB", 0.001)


def test_over_fair_share_is_refused_regardless_of_free_memory(big_csv, monkeypatch):
    """Refusal (1) is unconditional — an idle box does not license an unfair load."""
    monkeypatch.setattr(_guard, "available_gb", lambda: 999.0)
    with pytest.raises(LargeDataLoadError, match="over the"):
        _guard.check_load(str(big_csv), {}, reader="pd.read_csv")


def test_load_that_would_crowd_the_box_is_refused_for_now(big_csv, monkeypatch):
    """Refusal (2) is conditional, and says so — same contract as a failing malloc."""
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 1000.0)
    monkeypatch.setattr(_guard, "MIN_FREE_GB_AFTER_LOAD", 3.0)
    monkeypatch.setattr(_guard, "available_gb", lambda: 3.0)
    with pytest.raises(LargeDataLoadError, match="may succeed later"):
        _guard.check_load(str(big_csv), {}, reader="pd.read_csv")


def test_a_modest_load_is_never_refused_for_crowding(tmp_path, monkeypatch):
    """A nearly-full box must NOT start refusing small reads.

    Regression guard for a service hazard: without the material floor, startup
    reading a ~150 MB CSV would RAISE whenever the box sat near its margin.
    Refusing it frees nothing — a 0.15 GB load is not what exhausted the box.
    """
    monkeypatch.setattr(_guard, "MIN_INTERESTING_BYTES", 1024)
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 4.0)
    monkeypatch.setattr(_guard, "MIN_FREE_GB_AFTER_LOAD", 3.0)
    monkeypatch.setattr(_guard, "MIN_MATERIAL_GB", 1.0)
    monkeypatch.setattr(_guard, "available_gb", lambda: 0.5)   # box nearly exhausted

    modest_csv = tmp_path / "modest.csv"
    modest_csv.write_bytes(b"z" * (2 * 1024 * 1024))
    _guard.check_load(str(modest_csv), {}, reader="pd.read_csv")


def test_a_material_load_IS_refused_for_crowding(big_csv, monkeypatch):
    """The crowding rule still bites once the load is big enough to be the cause."""
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 1000.0)
    monkeypatch.setattr(_guard, "MIN_FREE_GB_AFTER_LOAD", 3.0)
    monkeypatch.setattr(_guard, "MIN_MATERIAL_GB", 0.001)
    monkeypatch.setattr(_guard, "available_gb", lambda: 3.0)
    with pytest.raises(LargeDataLoadError, match="may succeed later"):
        _guard.check_load(str(big_csv), {}, reader="pd.read_csv")


def test_load_that_fits_comfortably_passes(big_csv, monkeypatch):
    """A sub-GB file a job genuinely needs whole must NOT be blocked."""
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 1000.0)
    monkeypatch.setattr(_guard, "MIN_FREE_GB_AFTER_LOAD", 3.0)
    monkeypatch.setattr(_guard, "available_gb", lambda: 20.0)
    _guard.check_load(str(big_csv), {}, reader="pd.read_csv")


@pytest.mark.parametrize("kwargs", [
    {"chunksize": 100_000}, {"nrows": 10}, {"iterator": True},
])
def test_declared_bounds_exempt_the_call(big_csv, kwargs):
    _guard.check_load(str(big_csv), kwargs, reader="pd.read_csv")


def test_usecols_alone_does_not_exempt(big_csv):
    """A column subset of a 6 GB file is still hundreds of MB — no size heuristics."""
    with pytest.raises(LargeDataLoadError):
        _guard.check_load(str(big_csv), {"usecols": ["datetime"]}, reader="pd.read_csv")


def test_small_file_is_never_estimated(tmp_path):
    small = tmp_path / "small.csv"
    small.write_text("a,b\n1,2\n")
    _guard.check_load(str(small), {}, reader="pd.read_csv")


def test_non_path_arguments_are_ignored(big_csv):
    """Buffers, URLs and file objects are outside what the guard speaks about."""
    import io
    _guard.check_load(io.StringIO("a,b\n1,2\n"), {}, reader="pd.read_csv")
    _guard.check_load("https://example.com/x.csv", {}, reader="pd.read_csv")
    _guard.check_load(None, {}, reader="pd.read_csv")


def test_parquet_expansion_is_applied(tmp_path, monkeypatch):
    """0.65 GB on disk must be judged as ~5.2 GB resident, not 0.65 GB."""
    monkeypatch.setattr(_guard, "MIN_INTERESTING_BYTES", 1024)
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 0.02)
    monkeypatch.setattr(_guard, "available_gb", lambda: 999.0)
    parquet = tmp_path / "20251106.parquet"
    parquet.write_bytes(b"z" * (4 * 1024 * 1024))       # 4 MB * 8 = 32 MB > 20 MB cap
    csv = tmp_path / "same_size.csv"
    csv.write_bytes(b"z" * (4 * 1024 * 1024))           # 4 MB * 1 = 4 MB  < 20 MB cap

    with pytest.raises(LargeDataLoadError):
        _guard.check_load(str(parquet), {}, reader="pd.read_parquet")
    _guard.check_load(str(csv), {}, reader="pd.read_csv")


def test_advice_names_the_right_canonical_tool(tmp_path, monkeypatch):
    """The error must hand back a fix; a generic complaint would just be worked around."""
    monkeypatch.setattr(_guard, "MIN_INTERESTING_BYTES", 1024)
    monkeypatch.setattr(_guard, "MAX_RESIDENT_GB", 0.0001)
    monkeypatch.setattr(_guard, "available_gb", lambda: 999.0)

    parquet = tmp_path / "data.parquet"
    parquet.write_bytes(b"z" * (1024 * 1024))
    with pytest.raises(LargeDataLoadError, match="iter_batches"):
        _guard.check_load(str(parquet), {}, reader="pd.read_parquet")

    csv = tmp_path / "data.csv"
    csv.write_bytes(b"z" * (1024 * 1024))
    with pytest.raises(LargeDataLoadError, match="chunksize"):
        _guard.check_load(str(csv), {}, reader="pd.read_csv")


class TestFullLoadAllowed:
    def test_permits_an_otherwise_refused_load(self, big_csv, monkeypatch):
        monkeypatch.setattr(_guard, "available_gb", lambda: 999.0)
        with full_load_allowed("test: reviewed and correct"):
            _guard.check_load(str(big_csv), {}, reader="pd.read_csv")

    def test_est_gb_is_checked_against_free_memory(self, monkeypatch):
        """A sanctioned load must still not fire into a full box."""
        monkeypatch.setattr(_guard, "available_gb", lambda: 4.0)
        monkeypatch.setattr(_guard, "MIN_FREE_GB_AFTER_LOAD", 3.0)
        with pytest.raises(LargeDataLoadError, match="REFUSED"):
            with full_load_allowed("test: too big right now", est_gb=3.0):
                pass

    def test_requires_a_reason(self):
        with pytest.raises(ValueError):
            with full_load_allowed(""):
                pass

    def test_permission_does_not_leak_to_other_threads(self, big_csv, monkeypatch):
        """A prefetch thread must state its OWN intent, not inherit the main thread's."""
        import threading
        monkeypatch.setattr(_guard, "available_gb", lambda: 999.0)
        seen = {}

        def worker():
            try:
                _guard.check_load(str(big_csv), {}, reader="pd.read_csv")
                seen["raised"] = False
            except LargeDataLoadError:
                seen["raised"] = True

        with full_load_allowed("test: main thread only"):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

        assert seen["raised"] is True, "opt-in leaked into another thread"

    def test_permission_is_released_on_exit(self, big_csv, monkeypatch):
        monkeypatch.setattr(_guard, "available_gb", lambda: 999.0)
        with full_load_allowed("test"):
            pass
        with pytest.raises(LargeDataLoadError):
            _guard.check_load(str(big_csv), {}, reader="pd.read_csv")
