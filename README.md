# memguard

Memory safety for a macOS machine shared by many coding agents. Two independent layers:

| Layer | What it stops | How |
|---|---|---|
| **`memguard/memwatch.py`**: OOM watchdog | Aggregate pressure: many jobs together exhausting RAM and swap until the kernel panics | Samples free memory every 3 s. Under pressure it warns, then `SIGSTOP`s the largest non-exempt process, `SIGCONT`s it when the box drains, and `SIGKILL`s it only if suspension did not help |
| **`memguard` load guard** (`.pth` in a venv) | A single unbounded `pd.read_csv` / `pd.read_parquet` / `pq.read_table` of a multi-GB file | Refuses the load with a `LargeDataLoadError` that names the bounded alternative |

## Watchdog

```bash
uv sync
uv run memguard/memwatch.py            # report: which terminal window holds the memory
uv run memguard/memwatch.py --watch    # same, refreshed continuously
tools/install_memwatch.sh              # run permanently as a launchd agent
tools/install_memwatch.sh --uninstall
```

* **Log:** `logs/memwatch.log`
* **Stop:** `launchctl unload ~/Library/LaunchAgents/com.memguard.memwatch.plist`. `launchctl stop` does not work, because KeepAlive restarts the agent. On exit the watchdog resumes any process it holds suspended.
* **Manual control of one window's jobs:** `--stop ttysNNN`, `--resume ttysNNN`, `--kill ttysNNN`.
* **Thresholds** (GB free, env-overridable): `MEMWATCH_WARN_FREE_GB=6`, `MEMWATCH_STOP_FREE_GB=3.5`, `MEMWATCH_KILL_FREE_GB=2`.
* **Exemptions:** processes whose command line contains a line of `~/.config/memguard/exempt` are never suspended or killed. The file holds one substring per line, `#` starts a comment, and `MEMWATCH_EXEMPT_FILE` overrides the path. The file is machine-local. If it is missing, nothing is exempt; the daemon prints the list it loaded at startup.
* **Never targeted:** the `claude` CLI itself. Killing an agent leaves its runaway job running, so only the agent's compute children are targeted.
* **Detached jobs:** jobs without a terminal are grouped as `detached` when their command line contains `~/code/`. `MEMWATCH_PROJECT_MARKERS` overrides this and takes colon-separated values.

Memory is measured as **committed `phys_footprint`** (via `proc_pid_rusage`) for every process. RSS cannot be used because it does not include Metal/MPS (GPU) memory. Measured examples: a torch job holding a 2 GB MPS tensor showed 0.10 GB RSS, and a `boltz predict` run showed 7.8 MB RSS while holding 20.7 GB.

## Load guard (optional, per project venv)

```bash
tools/install_memguard.sh /path/to/project/.venv            # arm
tools/install_memguard.sh /path/to/project/.venv --check
tools/install_memguard.sh /path/to/project/.venv --uninstall
```

Opting in to a whole-file read that is genuinely needed:
`with memguard.full_load_allowed("reason", est_gb=...): ...`.
Set `MEMGUARD_DISABLED=1` to switch the guard off; `memwatch` reports any process it sees doing so.

## Tests

```bash
uv run pytest -q
```
