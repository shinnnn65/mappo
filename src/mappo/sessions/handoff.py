"""Session listing, cross-agent reference resolution, and context handoff formatting."""

import os
import subprocess
from pathlib import Path

from mappo.core.models import path_state, root_path
from mappo.sessions.providers import PROVIDERS
from mappo.sessions.refs import SUPPORTED_SESSION_AGENTS, parse_session_ref

SESSION_AGENTS = SUPPORTED_SESSION_AGENTS


def _normalize_project_paths(paths):
    normalized = []
    for raw in paths or ():
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            norm = root_path(raw.strip())
        except ValueError:
            norm = raw.strip()
        if norm not in normalized:
            normalized.append(norm)
    return normalized


def _path_matches_target(candidate, target):
    if not candidate or not target:
        return False
    if candidate == target:
        return True
    prefix = target.rstrip("/") + "/"
    return candidate.startswith(prefix)


def _session_matches_project(session, project_query=None, project_paths=None):
    roots = [r for r in (session.get("roots") or ()) if r]
    if session.get("cwd") and session["cwd"] not in roots:
        roots.insert(0, session["cwd"])

    if project_paths:
        for target in project_paths:
            if any(_path_matches_target(r, target) for r in roots):
                return True
        return False

    if project_query:
        needle = project_query.strip().casefold()
        if not needle:
            return True
        if any(needle in r.casefold() for r in roots):
            return True
        if any(needle in Path(r).name.casefold() for r in roots):
            return True
        return False

    return True


def _public_session(session):
    """Strip internal provider metadata before returning public list entries."""
    return {
        "ref": session["ref"],
        "agent": session["agent"],
        "session_id": session["session_id"],
        "title": session["title"],
        "cwd": session["cwd"],
        "roots": session["roots"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "archived": session["archived"],
        "model": session["model"],
        "git_branch": session["git_branch"],
        "source": session["source"],
        "coverage": session["coverage"],
    }


def _collect_sessions(home, agent=None, include_archived=False):
    base_home = Path(home).expanduser() if home is not None else Path.home()
    if agent is not None:
        if agent not in PROVIDERS:
            raise ValueError(
                f"暂不支持读取 {agent} 的会话；目前支持：{', '.join(SESSION_AGENTS)}"
            )
        targets = (agent,)
    else:
        targets = SESSION_AGENTS

    items = []
    for name in targets:
        lister, _reader = PROVIDERS[name]
        items.extend(lister(base_home, include_archived=include_archived))
    items.sort(
        key=lambda row: (row.get("updated_at") or "", row.get("created_at") or ""),
        reverse=True,
    )
    return items


def list_sessions(
    home=None,
    agent=None,
    project_query=None,
    project_paths=None,
    since=None,
    limit=20,
    include_archived=False,
):
    """List recent sessions across supported agents without loading full transcripts."""
    norm_paths = _normalize_project_paths(project_paths)
    items = _collect_sessions(home, agent=agent, include_archived=include_archived)
    filtered = []
    for item in items:
        if since and (not item.get("updated_at") or item["updated_at"] < since):
            continue
        if not _session_matches_project(
            item, project_query=project_query, project_paths=norm_paths
        ):
            continue
        filtered.append(_public_session(item))
        if limit is not None and len(filtered) >= limit:
            break
    return filtered


def resolve_session(raw_ref, home=None, agent=None):
    """Resolve a session reference/URI/command/ID to a single internal session record."""
    parsed = parse_session_ref(raw_ref, default_agent=agent)
    target_agent = parsed.agent or agent
    items = _collect_sessions(home, agent=target_agent, include_archived=True)

    needle = parsed.session_id.casefold()
    exact = [row for row in items if row["session_id"].casefold() == needle]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, [_public_session(r) for r in exact]

    compact_needle = needle.replace("-", "")
    prefix = [
        row
        for row in items
        if row["session_id"].casefold().startswith(needle)
        or row["session_id"].casefold().replace("-", "").startswith(compact_needle)
    ]
    if len(prefix) == 1:
        return prefix[0], None
    if len(prefix) > 1:
        if parsed.cwd_hint:
            hint_norm = _normalize_project_paths([parsed.cwd_hint])
            narrowed = [
                row
                for row in prefix
                if _session_matches_project(row, project_paths=hint_norm)
            ]
            if len(narrowed) == 1:
                return narrowed[0], None
        return None, [_public_session(r) for r in prefix]

    return None, []


def _truncate_text(text, max_chars):
    if not isinstance(text, str):
        return ""
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max(120, int(max_chars * 0.72))
    tail = max(60, max_chars - head - 32)
    omitted = len(text) - head - tail
    if omitted <= 40:
        return text[:max_chars] + "..."
    return f"{text[:head].rstrip()}\n\n...（已省略 {omitted} 字符）...\n\n{text[-tail:].lstrip()}"


def _inspect_live_git(cwd):
    if not cwd or not os.path.isabs(cwd) or path_state(cwd) != "directory":
        return None
    try:
        top = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if top.returncode != 0 or top.stdout.strip() != "true":
            return None
        branch_res = subprocess.run(
            ["git", "-C", cwd, "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        branch = (
            branch_res.stdout.strip()
            if branch_res.returncode == 0
            else "HEAD (detached)"
        )
        head_res = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        head = head_res.stdout.strip() if head_res.returncode == 0 else None
        status_res = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        dirty_lines = [
            line.strip()
            for line in (status_res.stdout or "").splitlines()
            if line.strip()
        ]
        return {
            "branch": branch,
            "head": head,
            "dirty_count": len(dirty_lines),
            "status_sample": dirty_lines[:10],
        }
    except (OSError, subprocess.SubprocessError):
        return None


def _select_messages(messages, turns, max_chars):
    """Select the opening goal plus the most recent N user/assistant turns."""
    if not messages:
        return None, [], 0
    first_user = next((m for m in messages if m["role"] == "user"), None)
    goal = _truncate_text(first_user["text"], max_chars) if first_user else None

    user_indices = [idx for idx, m in enumerate(messages) if m["role"] == "user"]
    turns_total = len(user_indices) if user_indices else len(messages)

    if turns is None or turns <= 0:
        selected_raw = messages
    elif user_indices:
        start_idx = user_indices[-turns] if len(user_indices) > turns else 0
        selected_raw = messages[start_idx:]
    else:
        selected_raw = messages[-(turns * 2) :]

    selected = []
    for msg in selected_raw:
        entry = {
            "role": msg["role"],
            "text": _truncate_text(msg["text"], max_chars),
        }
        if msg.get("timestamp"):
            entry["timestamp"] = msg["timestamp"]
        selected.append(entry)
    return goal, selected, turns_total


def build_handoff(
    raw_ref,
    home=None,
    agent=None,
    turns=6,
    max_chars=1600,
    include_git=True,
):
    """Build a structured, denoised cross-agent handoff payload for one session."""
    base_home = Path(home).expanduser() if home is not None else Path.home()
    session, candidates = resolve_session(raw_ref, home=base_home, agent=agent)
    if session is None:
        return None, candidates

    _lister, reader = PROVIDERS[session["agent"]]
    detail = reader(base_home, session)
    messages = detail.get("messages") or []
    goal, selected_messages, turns_total = _select_messages(messages, turns, max_chars)
    git_info = _inspect_live_git(session.get("cwd")) if include_git else None

    payload = {
        "ref": session["ref"],
        "agent": session["agent"],
        "session_id": session["session_id"],
        "title": session["title"],
        "cwd": session["cwd"],
        "roots": session["roots"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "model": detail.get("model") or session.get("model"),
        "source": session.get("source"),
        "coverage": detail.get("coverage") or session.get("coverage"),
        "limitations": detail.get("limitations"),
        "git": git_info,
        "summary": _truncate_text(detail["summary"], max_chars * 2)
        if detail.get("summary")
        else None,
        "goal": goal,
        "turns_total": turns_total,
        "messages_included": len(selected_messages),
        "messages": selected_messages,
        "changed_files": detail.get("changed_files") or [],
        "artifacts": detail.get("artifacts") or [],
        "source_paths": detail.get("source_paths") or [],
    }
    return payload, None


def render_handoff_markdown(handoff):
    """Render a handoff payload into concise Markdown suitable for any Coding Agent."""
    lines = [
        f"# 跨 Agent 会话交接：{handoff['title']}",
        "",
        f"- **来源会话**：`{handoff['ref']}`（`{handoff['agent']}` / `{handoff['session_id']}`）",
    ]
    if handoff.get("cwd"):
        lines.append(f"- **工作目录**：`{handoff['cwd']}`")
    if handoff.get("git"):
        git = handoff["git"]
        branch_part = f"`{git['branch']}`"
        if git.get("head"):
            branch_part += f" @ `{git['head']}`"
        dirty = git.get("dirty_count", 0)
        dirty_part = f"（当前有 {dirty} 处未提交改动）" if dirty else "（工作区干净）"
        lines.append(f"- **当前 Git 状态**：{branch_part} {dirty_part}")
    if handoff.get("updated_at"):
        lines.append(f"- **最近活动（UTC）**：`{handoff['updated_at']}`")
    if handoff.get("model"):
        lines.append(f"- **原模型**：`{handoff['model']}`")
    lines.append(f"- **可读完整度**：`{handoff['coverage']}`")
    if handoff.get("limitations"):
        lines.append(f"- **说明**：{handoff['limitations']}")

    if handoff.get("summary"):
        lines.extend(["", "## 原生摘要", "", handoff["summary"]])

    goal = handoff.get("goal")
    selected = handoff.get("messages") or []
    first_selected_user = next(
        (m["text"] for m in selected if m["role"] == "user"), None
    )
    if goal and goal != first_selected_user:
        lines.extend(["", "## 初始目标", "", goal])

    if selected:
        total = handoff.get("turns_total") or len(selected)
        lines.extend(
            [
                "",
                f"## 最近对话摘录（共 {total} 轮，展示最近 {len(selected)} 条消息）",
                "",
            ]
        )
        for msg in selected:
            label = "用户" if msg["role"] == "user" else "助手"
            ts = f" ({msg['timestamp']})" if msg.get("timestamp") else ""
            lines.append(f"### {label}{ts}")
            lines.append("")
            lines.append(msg["text"])
            lines.append("")

    changed = handoff.get("changed_files") or []
    if changed:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(["## 会话中改动过的文件", ""])
        for path in changed[:30]:
            lines.append(f"- `{path}`")
        if len(changed) > 30:
            lines.append(f"- ...（共 {len(changed)} 个文件）")
        lines.append("")

    git_sample = (handoff.get("git") or {}).get("status_sample") or []
    if git_sample:
        lines.extend(["## 当前工作区未提交变更（`git status --porcelain`）", "", "```text"])
        lines.extend(git_sample)
        lines.extend(["```", ""])

    artifacts = handoff.get("artifacts") or []
    if artifacts:
        lines.extend(["## 相关产物 / 计划", ""])
        for item in artifacts:
            if item.get("path"):
                lines.append(f"- `{item['path']}`")
            elif item.get("text"):
                lines.append(item["text"])
        lines.append("")

    if handoff.get("source_paths"):
        lines.extend(["## 本地只读证据路径", ""])
        for sp in handoff["source_paths"]:
            lines.append(f"- `{sp}`")

    return "\n".join(lines).rstrip() + "\n"
