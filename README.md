# Memguard

**The resource manager for autonomous AI agents on macOS.**

Running several AI agents on one Mac can bring it down. Each agent starts its own jobs: model inference, structure prediction, data processing. Together they can use up all the memory, and the Mac freezes or restarts. memguard stops that from happening.

It watches every job on your Mac, **including GPU memory that Activity Monitor doesn't show**. When memory runs low, it tells the agent responsible so the agent can shrink its job. If that doesn't help, memguard pauses the largest job and resumes it once memory frees up. A job is killed only as a last resort.

**Nothing to configure. No changes to your agents.** Install it once and it runs in the background.

## Install

1. Download the latest **memguard .dmg** from [Releases](https://github.com/memguard-agent/memguard/releases).
2. Open it and double-click **Install memguard**.
3. Answer the questions. That's it.

Requires macOS. Tested on macOS 26.5.

## What you'll notice

- **Normally, nothing.** memguard uses almost no resources.
- **When memory gets low,** you get a notification naming the job that uses the most memory.
- **Your Claude Code agents are told too.** An agent learns that its job is using too much memory and how to reduce it, before anything gets paused. It is also told if its job is paused, resumed or stopped.
- **If memory stays critical,** the largest job is paused and continues on its own once memory frees up. Your agents themselves are never stopped, only the jobs they started.

| Free memory | What memguard does |
|---|---|
| under 6 GB | notifies you |
| under 3.5 GB | warns the agent, then pauses its job about 30 seconds later |
| under 2 GB | pauses the largest job immediately; if memory is still critical, stops it |
| back above 6 GB | resumes the paused job |

## Protect important programs

To make sure a program is never paused, add part of its name to the file `~/.config/memguard/exempt`, one name per line. For example:

```
redis-server
my_server.py
```

## Why memguard exists

It was built after a Mac running several AI agents crashed when memory ran out. Three jobs used about 24 GB between them on a 24 GB machine. Much of what such jobs use is GPU memory, which ordinary tools miss: one job was measured at **20.7 GB** while ordinary tools reported only **7.8 MB**. memguard measures what each job really uses, so it catches exactly this.

## Uninstall

Open the disk image again and double-click **Uninstall memguard**.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0.txt).

Use, modification, and redistribution are permitted for noncommercial purposes under the terms of the license. Commercial use requires separate written permission from the copyright holder.

For commercial licensing inquiries, please contact the copyright holder.

<!-- **Team / enterprise licensing:** [contact us](https://github.com/memguard-agent/memguard/issues/new?title=Team%20%2F%20enterprise%20licensing%20inquiry). -->
