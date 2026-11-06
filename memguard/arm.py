"""Arm the guard in this interpreter. Imported by `memguard.pth` at startup.

Two properties this module MUST hold, because it runs in every Python process on the
box — including long-running services:

1. **Lazy.** Arming installs a `sys.meta_path` finder and returns. The reader functions
   are patched only when pandas / pyarrow is first imported, so the ~500 non-pandas
   processes on this box pay essentially nothing and interpreter startup is unaffected.

2. **Fails OPEN.** Any unexpected exception inside the guard is swallowed and the
   original reader runs. A defect in the guard must never break a caller — the ONLY
   exception it may propagate is its own deliberate `LargeDataLoadError`.
"""
from __future__ import annotations

import functools
import sys

_ARMED_FLAG = "_memguard_wrapped"


def _wrap_reader(orig, reader_name, path_arg_index=0, path_kwarg_names=()):
    """Return `orig` wrapped with the size check. Idempotent."""
    if getattr(orig, _ARMED_FLAG, False):
        return orig

    from ._guard import LargeDataLoadError, check_load

    @functools.wraps(orig)
    def wrapper(*args, **kwargs):
        try:
            if len(args) > path_arg_index:
                path_arg = args[path_arg_index]
            else:
                path_arg = next(
                    (kwargs[n] for n in path_kwarg_names if n in kwargs), None
                )
            check_load(path_arg, kwargs, reader=reader_name)
        except LargeDataLoadError:
            raise
        except Exception:
            pass  # fail OPEN: a guard bug must never break a caller
        return orig(*args, **kwargs)

    setattr(wrapper, _ARMED_FLAG, True)
    wrapper.__wrapped_by_memguard__ = orig
    return wrapper


def _patch_pandas(pandas_module) -> None:
    for name, kwarg_names in (
        ("read_csv", ("filepath_or_buffer",)),
        ("read_table", ("filepath_or_buffer",)),
        ("read_parquet", ("path",)),
    ):
        orig = getattr(pandas_module, name, None)
        if orig is None:
            continue
        setattr(
            pandas_module,
            name,
            _wrap_reader(orig, f"pd.{name}", path_kwarg_names=kwarg_names),
        )


def _patch_pyarrow_parquet(pq_module) -> None:
    """A direct pyarrow caller would otherwise bypass the pandas wrapper entirely."""
    orig = getattr(pq_module, "read_table", None)
    if orig is not None:
        pq_module.read_table = _wrap_reader(
            orig, "pq.read_table", path_kwarg_names=("source",)
        )


_TARGETS = {
    "pandas": _patch_pandas,
    "pyarrow.parquet": _patch_pyarrow_parquet,
}


class _PatchOnImport:
    """meta_path finder that patches a target module right after it executes.

    CPython has no native post-import hook, so this defers to the real finders for the
    spec, then wraps that spec's `exec_module` to run the patch once the module body has
    finished executing. Loader instances are created per `find_spec`, so mutating this
    spec's loader cannot leak into any other module's import.
    """

    def find_spec(self, fullname, path=None, target=None):
        patch = _TARGETS.get(fullname)
        if patch is None:
            return None

        spec = None
        for finder in sys.meta_path:
            if finder is self:
                continue
            try:
                spec = finder.find_spec(fullname, path, target)
            except Exception:
                spec = None
            if spec is not None:
                break
        if spec is None or spec.loader is None:
            return None

        orig_exec = spec.loader.exec_module

        def exec_module(module, _orig=orig_exec, _patch=patch):
            _orig(module)
            try:
                _patch(module)
            except Exception:
                pass  # fail OPEN

        try:
            spec.loader.exec_module = exec_module
        except Exception:
            return None  # immutable loader — leave the import untouched
        return spec


def arm() -> None:
    """Install the import hook, and patch anything already imported. Idempotent."""
    if getattr(sys, "_memguard_armed", False):
        return
    sys._memguard_armed = True

    for fullname, patch in _TARGETS.items():
        module = sys.modules.get(fullname)
        if module is not None:
            try:
                patch(module)
            except Exception:
                pass

    sys.meta_path.insert(0, _PatchOnImport())


try:
    arm()
except Exception:
    pass  # arming must never break interpreter startup
