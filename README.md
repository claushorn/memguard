# memguard

**Keep a Mac with many AI coding agents running from crashing.**

When several agents (Claude Code, Codex, Cursor, …) work on one machine, each one starts its own jobs, such as model inference, structure prediction or data processing. No single job has to misbehave: together they use up RAM and swap, macOS stalls, and the kernel watchdog panics the machine. memguard is a small watchdog that prevents this.

- **It notices the pressure first.** It samples free memory every 3 s.
- **It warns the agent responsible.** The warning is printed in that agent's own terminal.
- **It pauses before it kills.** The largest job is paused with `SIGSTOP` and resumed when memory frees up. It is killed only when free memory reaches the kill threshold.
- **It sees GPU memory.** It measures each process's real committed footprint. RSS misses Metal/MPS memory: one PyTorch job holding **20.7 GB** showed **7.8 MB** RSS.
- **It never kills your agent.** The `claude` / agent CLI is never targeted, only its child processes. You can also exempt any service.
- **It is cheap to run.** A full scan of about 500 processes takes about 2 ms.

macOS only. Requires [uv](https://docs.astral.sh/uv/).

## Install

```bash
git clone https://github.com/claushorn/memguard.git
cd memguard
tools/install_memwatch.sh        # installs and starts a launchd agent (survives reboots)
```

Check that it is running: `launchctl list | grep memwatch`. It logs to `logs/memwatch.log`.
Uninstall: `tools/install_memwatch.sh --uninstall`.

## Use

```bash
uv run memguard/memwatch.py              # which terminal window is holding the memory
uv run memguard/memwatch.py --watch      # the same view, refreshed live
uv run memguard/memwatch.py --stop ttys012     # pause that window's jobs (reversible)
uv run memguard/memwatch.py --resume ttys012
uv run memguard/memwatch.py --kill ttys012     # irreversible
```

Example report:

```
FREE 3.1 GB / 24.0 GB   swap 12.3 GB          [SIGSTOP threshold 3.5 GB]

TTY           GB  WINDOW TITLE                             STATE     TOP CHILD
detached    20.9! DETACHED background jobs (no owning term           boltz  20.7 GB
ttys024      6.8  Fold candidate binders                             python  6.7 GB
ttys021      3.9  Train embedding model                              python  3.7 GB
```

## Configure

| What | How |
|---|---|
| Never pause or kill a process | Add a substring of its command line to `~/.config/memguard/exempt`, one per line. The file is read at startup. |
| Thresholds, in GB free | `MEMWATCH_WARN_FREE_GB=6` · `MEMWATCH_STOP_FREE_GB=3.5` · `MEMWATCH_KILL_FREE_GB=2` · `MEMWATCH_RESUME_FREE_GB=6` |
| Where agent projects live | `MEMWATCH_PROJECT_MARKERS` (colon-separated, default `~/code/`). Used to group background jobs that have no terminal. |

## Optional: large-load guard for Python projects

This makes `pd.read_csv` / `pd.read_parquet` / `pq.read_table` refuse to load a multi-GB file whole. The error names the bounded alternative to use instead.

```bash
tools/install_memguard.sh /path/to/project/.venv     # --check / --uninstall
```

To allow a whole-file load that is genuinely needed: `with memguard.full_load_allowed("why", est_gb=4): ...`

## Development

```bash
uv run pytest -q
```

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0.txt).

Use, modification, and redistribution are permitted for noncommercial purposes under the terms of the license. Commercial use requires separate written permission from the copyright holder.

For commercial licensing inquiries, please contact the copyright holder.
