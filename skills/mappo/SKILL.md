---
name: mappo
description: Discover, query, open, and audit local macOS Coding Agent workspaces (Codex, Cursor, Claude Code, Antigravity, CodeBuddy, WorkBuddy, DeepSeek Harness, VS Code, Trae) using the read-only Mappo CLI. Use when the user asks what projects they worked on recently across tools, where a local repository or worktree is located, which repositories have duplicate clones, how much disk space rebuildable dependencies or agent sandboxes consume, or wants to open a project in its most recently used editor or desktop agent.
---

# Mappo — Local Coding Agent Workspace Map

Use `mappo` as a deterministic, read-only local workspace index across all Coding Agents, editors, and extensions installed on macOS.

## 1. Pre-flight Check (Never Download Silently)

Check whether `mappo` is installed before running commands:

```sh
command -v mappo || [ -x ~/.local/bin/mappo ]
```

- If available at `~/.local/bin/mappo` but not on `PATH`, invoke `~/.local/bin/mappo`.
- If `mappo` is **not installed**, do **not** download binaries silently. Report that `mappo` is missing and share the official install instructions from `https://github.com/shinnnn65/mappo/releases`:

```sh
mkdir -p ~/.local/bin
curl -fsSL https://github.com/shinnnn65/mappo/releases/latest/download/mappo.pyz -o ~/.local/bin/mappo
chmod 755 ~/.local/bin/mappo
~/.local/bin/mappo scan
```

## 2. Read-Only Command Playbook

Prefer `--indexed --json` for fast queries against the local SQLite snapshot (`~/.local/state/mappo/index.sqlite`). If the index does not exist yet or the user explicitly asks for fresh results, run `mappo scan` first or omit `--indexed`.

| User intent | Command |
| --- | --- |
| Refresh local index across all tools | `mappo scan --json` |
| Find a repo by name or path fragment | `mappo projects --indexed --name <query> --json` |
| Cross-tool recent activity / weekly review | `mappo projects --indexed --recent --since 7d --json` |
| Filter by specific Agent / editor | `mappo projects --indexed --agent <codex\|cursor\|claude\|antigravity\|codebuddy\|workbuddy\|dsh\|vscode> --json` |
| Inspect project evidence, multi-roots, and sources | `mappo inspect <project_id> --indexed` |
| Audit reclaimable dependencies, duplicate clones & sandboxes | `mappo hygiene --indexed --json` |
| Check missing sources or macOS permission issues | `mappo doctor --indexed --json` |
| Preview how `mappo open` will launch a project | `mappo open <name-or-id> --indexed --dry-run --json` |
| Open a project in its most recent IDE / Agent (on explicit request) | `mappo open <name-or-id> --indexed` (or `--with cursor\|codex\|terminal\|finder\|remote`) |

## 3. Interpretation & Safety Rules

- **Respect evidence boundaries**: `kind="native"` indicates an explicit workspace registration; `kind="inferred"` comes from session history or cwd logs and may include temporary task directories; `asset_kind="sandbox"` denotes agent-managed sandboxes or Git worktrees. Do not present sandboxes or inferred cache paths as confirmed standalone projects without checking `mappo inspect`.
- **Stay strictly read-only by default**: Never run `rm -rf` or delete project directories based on `mappo hygiene` output. Present a concise summary of reclaimable artifact sizes (`node_modules`, `.venv`, `dist`, `target`, etc.) and duplicate clones, and guide the user to run `mappo web` (Organize tab) for interactive preview, on-demand Git safety checks, and reversible macOS Trash cleanup.
- **Keep user privacy intact**: Only surface project paths, branches, timestamps, and tool metadata relevant to the user's request.
