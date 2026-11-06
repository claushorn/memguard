"""The guard must arm in a FRESH interpreter of a TARGET venv, with nothing imported.

This is the load-bearing test of the whole mechanism. `memguard` protects a project only
because `tools/install_memguard.sh` writes a `.pth` into that project's venv, which
CPython executes at interpreter startup; if that stops working, the guard silently
stops existing and every unit test would still pass. So these tests install into a
real, throwaway venv and assert the property END TO END from subprocesses.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "tools" / "install_memguard.sh"


@pytest.fixture(scope="module")
def target_venv(tmp_path_factory):
    """A throwaway venv with pandas, armed by the installer under test."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")
    venv = tmp_path_factory.mktemp("target") / ".venv"
    subprocess.run([uv, "venv", "--quiet", str(venv)], check=True)
    subprocess.run([uv, "pip", "install", "--quiet", "--python", str(venv / "bin" / "python"),
                    "pandas"], check=True)
    result = subprocess.run([str(INSTALLER), str(venv)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return venv


def _run(venv: Path, code: str, env_extra: dict | None = None):
    env = dict(os.environ)
    env.pop("MEMGUARD_DISABLED", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [str(venv / "bin" / "python"), "-c", code],
        capture_output=True, text=True, timeout=300, cwd=str(venv.parent), env=env,
    )


def test_installer_is_executable():
    assert INSTALLER.is_file(), f"{INSTALLER} is missing — the guard cannot be installed"
    assert os.access(INSTALLER, os.X_OK), f"{INSTALLER} is not executable"


def test_check_reports_the_hook(target_venv):
    result = subprocess.run([str(INSTALLER), str(target_venv), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hook present  : yes" in result.stdout
    assert "guard armed   : True" in result.stdout


def test_pandas_readers_are_wrapped_without_any_import_by_the_caller(target_venv):
    """A bare interpreter that imports only pandas must already be guarded."""
    result = _run(target_venv, "import pandas as pd;"
                  "print(getattr(pd.read_csv, '_memguard_wrapped', False))")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True", (result.stdout, result.stderr)


def test_oversized_load_raises_in_a_fresh_subprocess(target_venv, tmp_path):
    """The end-to-end property: an over-cap load fails loudly, with actionable advice."""
    big = tmp_path / "big.csv"
    big.write_bytes(b"datetime,close\n" + b"x" * (2 * 1024 * 1024))
    # 1 MB 'interesting' floor and a 0.001 GB cap => the 2 MB fixture is over-cap,
    # so no multi-GB file is needed to exercise the real code path.
    result = _run(target_venv, f"import pandas as pd\npd.read_csv({str(big)!r})\n", {
        "MEMGUARD_MIN_INTERESTING_BYTES": str(1024 * 1024),
        "MEMGUARD_MAX_RESIDENT_GB": "0.001",
    })
    assert result.returncode != 0, "an over-cap load was NOT refused"
    assert "MEMGUARD" in result.stderr, result.stderr
    assert "LargeDataLoadError" in result.stderr, result.stderr


def test_disabled_switch_lets_the_load_through(target_venv, tmp_path):
    """The documented escape switch works — and is what memwatch reports on."""
    small = tmp_path / "some.csv"
    small.write_text("a,b\n1,2\n")
    result = _run(target_venv, f"import pandas as pd; pd.read_csv({str(small)!r})", {
        "MEMGUARD_DISABLED": "1",
        "MEMGUARD_MIN_INTERESTING_BYTES": "1",
        "MEMGUARD_MAX_RESIDENT_GB": "0.0000001",
    })
    assert result.returncode == 0, result.stderr


def test_uninstall_disarms(tmp_path_factory, target_venv):
    """Runs last in this module: removing the hook leaves pandas unwrapped."""
    result = subprocess.run([str(INSTALLER), str(target_venv), "--uninstall"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = _run(target_venv, "import pandas as pd;"
                  "print(getattr(pd.read_csv, '_memguard_wrapped', False))")
    assert result.stdout.strip() == "False", (result.stdout, result.stderr)


def test_guard_fails_open_on_an_internal_error(tmp_path, monkeypatch):
    """A defect inside the guard must never break a caller.

    Only LargeDataLoadError may propagate; anything else is swallowed and the original
    reader runs. Verified by making the path resolver raise.
    """
    from memguard import _guard
    from memguard.arm import _wrap_reader

    def reader(path):
        return f"read {path}"

    def boom(*_a, **_k):
        raise RuntimeError("simulated guard defect")

    monkeypatch.setattr(_guard, "_resolve_path", boom)
    wrapped = _wrap_reader(reader, "test.reader")
    assert wrapped(str(tmp_path / "s.csv")) == f"read {tmp_path / 's.csv'}"
