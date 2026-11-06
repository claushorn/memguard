# memguard

**The missing resource manager for autonomous AI agents on macOS.**

memguard protects your Mac from memory exhaustion caused by multiple independent AI agents. It covers RAM and GPU (Metal) memory, which share one pool on Apple Silicon. It supervises every agent's workloads across the whole machine and steps in before memory pressure turns into a kernel panic. It pauses a job first and kills only as a last resort.

**No agent changes. No library imports. No scheduler.** Install it once and it runs alongside your agents.

## Why

Coding agents such as Claude Code launch Python scripts, model inference and structure predictions, often several at once and often in the background. They don't know what the other agents are doing. Three jobs can each fit comfortably in memory and still exhaust the machine together.

Apple Silicon makes this hard to see. Metal/MPS allocations **do not appear in RSS**, so `ps`, Activity Monitor's default columns and psutil-based tools all miss them. Two measurements:

- A PyTorch job holding a 2 GB MPS tensor showed 0.10 GB RSS.
- A `boltz predict` run holding **20.7 GB** showed **7.8 MB** RSS.

**The incident behind this project:** a 24 GB M4 Pro running several agents kernel-panicked when memory ran out. At the moment of the panic it had 905 free pages and low swap space. Three Python jobs held about 24 GB between them, and 10.5 GB of the memory was wired, so it could not be swapped out.

## How it works

One daemon, launched by launchd, samples free memory every 3 s and reads the committed footprint (`phys_footprint`) of **every** process. This value includes Metal memory. A full scan of about 500 processes takes about 2 ms.

| Free memory (default) | Action |
|---|---|
| < 6 GB | **Warn:** macOS notification and a log line |
| < 3.5 GB | **Warn the largest job**, then **pause it** (`SIGSTOP`) about 27 s later if memory is still low |
| < 2 GB | **Pause the largest job immediately**. If one is already paused and memory is still under 2 GB, **kill it** |
| ≥ 6 GB for 3 samples | **Resume** the paused job (`SIGCONT`) |

- **The agent is never the target.** Killing an agent loses its context and leaves its runaway job running, so memguard targets the agent's child jobs. The `claude` CLI is protected by default. For other agent CLIs and for services that must never stall, add them to the exemption file.
- **It shows who uses the memory.** Jobs are grouped by the terminal window of the agent that started them, with its Claude Code task title (titles are read from Terminal.app). Background jobs whose launcher has exited are listed as `detached`.
- **Only one job is paused at a time.** Several jobs peaking together are time-sliced instead of crashing the machine together.
- **It never leaves a job frozen.** Stopping the daemon first resumes any job it has paused.

## Install

Requirements: macOS on Apple Silicon and [uv](https://docs.astral.sh/uv/). Tested on macOS 26.5 with an M4 Pro. Intel Macs are untested, and Linux and NVIDIA GPUs are not supported.

```bash
git clone https://github.com/claushorn/memguard.git
cd memguard
tools/install_memwatch.sh            # install and start the launchd agent (survives reboots)
launchctl list | grep memwatch       # check that it is running
tail -f logs/memwatch.log            # see what it does
```

Uninstall: `tools/install_memwatch.sh --uninstall`.

## Use

```bash
uv run memguard/memwatch.py                  # which window holds the memory
uv run memguard/memwatch.py --watch          # the same view, refreshed live
uv run memguard/memwatch.py --stop ttys012   # pause that window's jobs (reversible)
uv run memguard/memwatch.py --resume ttys012
uv run memguard/memwatch.py --kill ttys012   # irreversible
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

Create `~/.config/memguard/exempt` to protect processes. Each line is a substring of a command line; matching processes are never paused or killed:

```
# ~/.config/memguard/exempt
redis-server
my_live_service.py
/opt/homebrew/bin/codex
```

The file is read when the daemon starts; restart it with `launchctl kickstart -k gui/$(id -u)/com.memguard.memwatch`.

Environment overrides, set in the launchd plist or the shell:

| Variable | Default |
|---|---|
| `MEMWATCH_WARN_FREE_GB` / `MEMWATCH_STOP_FREE_GB` / `MEMWATCH_KILL_FREE_GB` | `6` / `3.5` / `2` |
| `MEMWATCH_RESUME_FREE_GB` | `6` |
| `MEMWATCH_PROJECT_MARKERS` | `~/code/`. Background jobs whose command line contains this are listed as `detached` |
| `MEMWATCH_EXEMPT_FILE` | `~/.config/memguard/exempt` |

## Optional: large-load guard for Python projects

This makes `pd.read_csv` / `pd.read_parquet` / `pq.read_table` refuse to load a multi-GB file whole. The error names the bounded alternative to use instead.

```bash
tools/install_memguard.sh /path/to/project/.venv     # --check / --uninstall
```

To allow a whole-file load that is genuinely needed: `with memguard.full_load_allowed("why", est_gb=4): ...`

## Roadmap

- **Feedback the agent can read.** Today a warning reaches the human, through a desktop notification, the log, and the job's terminal if it has one. It does not reach the LLM agent's input. The next step is a Claude Code hook that puts "your job is using 20 GB and will be paused" into the agent's context, so the agent can lower its batch size before it is paused.

## Development

```bash
uv run pytest -q
```

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0.txt).

Use, modification, and redistribution are permitted for noncommercial purposes under the terms of the license. Commercial use requires separate written permission from the copyright holder.

For commercial licensing inquiries, please contact the copyright holder.
