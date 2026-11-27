"""Read-only local session adapters for Codex, Antigravity, Cursor, and CodeBuddy."""

import json
import os
import re
import sqlite3
from pathlib import Path

from mappo.core.io import query, read_json, workspace_json
from mappo.core.models import activity_time, root_path
from mappo.providers.codebuddy import session_edges
from mappo.providers.registry import EDITORS, SUPPORT

_ANTIGRAVITY_DIRS = (
    ("desktop", ".gemini/antigravity"),
    ("ide", ".gemini/antigravity-ide"),
    ("cli", ".gemini/antigravity-cli"),
)

_WRAPPER_TAG_RE = re.compile(
    r"<(USER_REQUEST|user_query)>\s*(.*?)\s*</\1>",
    re.S,
)
_METADATA_BLOCK_RE = re.compile(
    r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|timestamp)>.*?</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|timestamp)>",
    re.S,
)
_NOISE_PREFIXES = (
    "<environment_context>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<AGENTS.md>",
    "<app-context>",
    "<turn_aborted>",
    "# AGENTS.md instructions for ",
)
_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _safe_query(path, statement, params=()):
    if not path.is_file():
        return []
    try:
        return query(path, statement, params)
    except (OSError, sqlite3.Error, BlockingIOError):
        return []


def _table_columns(path, table):
    return {r[1] for r in _safe_query(path, f"PRAGMA table_info({table})")}


def _safe_root(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return root_path(value.strip())
    except ValueError:
        return value.strip()


def _clean_text(text):
    if not isinstance(text, str):
        return ""
    stripped = text.strip()
    if not stripped:
        return ""
    matches = _WRAPPER_TAG_RE.findall(stripped)
    if matches:
        joined = "\n\n".join(body.strip() for _tag, body in matches if body.strip())
        if joined:
            return joined
    stripped = _METADATA_BLOCK_RE.sub("", stripped).strip()
    return stripped


def _extract_content_text(content):
    """Extract readable plain text from string or list-of-blocks content."""
    if isinstance(content, str):
        return _clean_text(content)
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            text = _clean_text(block)
            if text:
                parts.append(text)
        elif isinstance(block, dict):
            btype = (block.get("type") or "").lower()
            if btype in (
                "thinking",
                "reasoning",
                "tool_use",
                "tool_result",
                "tool_call",
                "image",
                "image_url",
            ):
                continue
            raw = block.get("text")
            if raw is None and btype in ("text", "input_text", "output_text", ""):
                raw = block.get("content")
            if isinstance(raw, str):
                text = _clean_text(raw)
                if text:
                    parts.append(text)
    return "\n\n".join(parts).strip()


def _is_codex_injected_user_text(text):
    stripped = text.lstrip()
    return any(stripped.startswith(prefix) for prefix in _NOISE_PREFIXES)


def _first_line(text, limit=96):
    if not isinstance(text, str):
        return ""
    for line in text.splitlines():
        cleaned = " ".join(line.split())
        if cleaned:
            return cleaned[:limit] + ("..." if len(cleaned) > limit else "")
    return ""


def _short_id(session_id):
    cleaned = re.sub(r"[^0-9a-zA-Z]", "", str(session_id or ""))
    return cleaned[:8] if cleaned else str(session_id or "")[:8]


def _make_ref(agent, session_id):
    return f"{agent}:{_short_id(session_id)}"


def _append_message(messages, role, text, timestamp=None):
    cleaned = _clean_text(text)
    if not cleaned:
        return
    if messages and messages[-1]["role"] == role:
        if cleaned == messages[-1]["text"]:
            return
        messages[-1]["text"] += "\n\n" + cleaned
        if timestamp and not messages[-1].get("timestamp"):
            messages[-1]["timestamp"] = timestamp
        return
    entry = {"role": role, "text": cleaned}
    if timestamp:
        entry["timestamp"] = timestamp
    messages.append(entry)


def _project_slug(path_str):
    if not isinstance(path_str, str) or not path_str:
        return None
    return _SLUG_RE.sub("-", path_str.lstrip("/")).strip("-")


def _codex_state_db(home):
    base = home / ".codex"
    if not base.is_dir():
        return None
    dbs = sorted(
        (
            p
            for p in base.iterdir()
            if p.is_file() and p.match("state_*.sqlite") and p.stem[6:].isdigit()
        ),
        key=lambda p: int(p.stem.split("_")[-1]),
    )
    return dbs[-1] if dbs else None


def list_codex_sessions(home, include_archived=False):
    """List Codex sessions from ~/.codex/state_*.sqlite."""
    db = _codex_state_db(home)
    if db is None:
        return []
    cols = _table_columns(db, "threads")
    if "id" not in cols:
        return []

    wanted = [
        "id",
        "rollout_path" if "rollout_path" in cols else "NULL",
        "cwd" if "cwd" in cols else "NULL",
        "name" if "name" in cols else "NULL",
        "title" if "title" in cols else "NULL",
        "preview" if "preview" in cols else "NULL",
        "first_user_message" if "first_user_message" in cols else "NULL",
        "created_at_ms"
        if "created_at_ms" in cols
        else ("created_at" if "created_at" in cols else "NULL"),
        "updated_at_ms"
        if "updated_at_ms" in cols
        else ("updated_at" if "updated_at" in cols else "NULL"),
        "archived" if "archived" in cols else "0",
        "git_branch" if "git_branch" in cols else "NULL",
        "model" if "model" in cols else "NULL",
        "source" if "source" in cols else "NULL",
        "attached_thread_parent_id"
        if "attached_thread_parent_id" in cols
        else "NULL",
    ]
    where = "" if include_archived else "WHERE COALESCE(archived, 0) = 0"
    order_col = (
        "updated_at_ms"
        if "updated_at_ms" in cols
        else ("updated_at" if "updated_at" in cols else "rowid")
    )
    rows = _safe_query(
        db,
        f"SELECT {', '.join(wanted)} FROM threads {where} ORDER BY {order_col} DESC",
    )

    sessions = []
    for row in rows:
        (
            tid,
            rollout_path,
            cwd,
            thread_name,
            title,
            preview,
            first_msg,
            created_raw,
            updated_raw,
            archived,
            git_branch,
            model,
            source,
            parent_id,
        ) = row
        if not tid:
            continue
        if parent_id and not include_archived:
            continue
        norm_cwd = _safe_root(cwd)
        display_title = _first_line(thread_name or title or preview or first_msg or "")
        sessions.append(
            {
                "agent": "codex",
                "session_id": tid,
                "ref": _make_ref("codex", tid),
                "title": display_title or "(未命名 Codex 会话)",
                "cwd": norm_cwd,
                "roots": [norm_cwd] if norm_cwd else [],
                "created_at": activity_time(created_raw),
                "updated_at": activity_time(updated_raw),
                "archived": bool(archived),
                "model": model,
                "git_branch": git_branch,
                "source": source,
                "coverage": "full",
                "meta": {
                    "state_db": str(db),
                    "rollout_path": rollout_path,
                    "preview": preview,
                    "first_user_message": first_msg,
                },
            }
        )
    return sessions


def _read_codex_memory_summary(home, thread_id):
    base = home / ".codex"
    for name in ("memories_v2_1.sqlite", "memories_1.sqlite"):
        db = base / name
        if not db.is_file():
            continue
        cols = _table_columns(db, "stage1_outputs")
        if "thread_id" not in cols or "rollout_summary" not in cols:
            continue
        rows = _safe_query(
            db,
            "SELECT rollout_summary, raw_memory, rollout_slug FROM stage1_outputs WHERE thread_id=? LIMIT 1",
            (thread_id,),
        )
        if rows:
            summary, raw_mem, slug = rows[0]
            text = (summary or raw_mem or "").strip()
            if text:
                return text, str(db), slug
    return None, None, None


def _read_codex_thread_history(home, thread_id):
    db = home / ".codex" / "thread_history_1.sqlite"
    if not db.is_file():
        return [], [], [], None
    cols = _table_columns(db, "thread_items")
    if not {"thread_id", "item_type", "item_json"}.issubset(cols):
        return [], [], [], None
    order = "rollout_ordinal ASC, rowid ASC" if "rollout_ordinal" in cols else "rowid ASC"
    rows = _safe_query(
        db,
        f"""SELECT item_type, item_json, created_at_ms
              FROM thread_items
             WHERE thread_id=?
               AND item_type IN ('userMessage', 'agentMessage', 'fileChange', 'plan')
             ORDER BY {order}""",
        (thread_id,),
    )
    if not rows:
        return [], [], [], None

    messages = []
    changed_files = []
    seen_files = set()
    plans = []
    for item_type, raw_json, created_ms in rows:
        try:
            obj = json.loads(raw_json)
        except (TypeError, ValueError):
            continue
        ts = activity_time(created_ms)
        if item_type == "userMessage":
            text = _extract_content_text(obj.get("content"))
            if text and not _is_codex_injected_user_text(text):
                _append_message(messages, "user", text, ts)
        elif item_type == "agentMessage":
            text = _clean_text(obj.get("text") or "")
            if text:
                _append_message(messages, "assistant", text, ts)
        elif item_type == "fileChange":
            for change in obj.get("changes") or ():
                if isinstance(change, dict):
                    fpath = change.get("path")
                    if isinstance(fpath, str) and fpath and fpath not in seen_files:
                        seen_files.add(fpath)
                        changed_files.append(fpath)
        elif item_type == "plan":
            ptext = _clean_text(obj.get("text") or "")
            if ptext:
                plans.append(ptext)
    return messages, changed_files, plans, str(db)


def _read_codex_rollout_jsonl(rollout_path):
    if not rollout_path:
        return [], []
    path = Path(rollout_path)
    if not path.is_file():
        return [], []
    messages = []
    changed_files = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "response_item":
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "message":
                    continue
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = _extract_content_text(payload.get("content"))
                if not text:
                    continue
                if role == "user" and _is_codex_injected_user_text(text):
                    continue
                _append_message(messages, role, text, activity_time(obj.get("timestamp")))
    except OSError:
        return [], []
    return messages, changed_files


def read_codex_session(home, session):
    """Load detailed messages, summary, and changed files for a Codex session."""
    tid = session["session_id"]
    meta = session.get("meta") or {}
    source_paths = [meta["state_db"]] if meta.get("state_db") else []
    artifacts = []

    summary, mem_db, _slug = _read_codex_memory_summary(home, tid)
    if mem_db:
        source_paths.append(mem_db)

    messages, changed_files, plans, hist_db = _read_codex_thread_history(home, tid)
    if hist_db:
        source_paths.append(hist_db)

    if not messages:
        rpath = meta.get("rollout_path")
        messages, r_files = _read_codex_rollout_jsonl(rpath)
        if rpath and Path(rpath).is_file():
            source_paths.append(rpath)
        for item in r_files:
            if item not in changed_files:
                changed_files.append(item)

    if not messages and meta.get("first_user_message"):
        _append_message(messages, "user", meta["first_user_message"])

    if plans:
        artifacts.append({"kind": "plan", "text": plans[-1]})

    coverage = "full" if messages else ("summary_only" if summary else "meta_only")
    limitations = None
    if coverage != "full":
        limitations = "未在本地找到该 Codex 会话的完整对话正文，已返回可用元信息或摘要。"

    return {
        "messages": messages,
        "summary": summary or _clean_text(meta.get("preview") or "") or None,
        "changed_files": changed_files,
        "artifacts": artifacts,
        "source_paths": list(dict.fromkeys(source_paths)),
        "coverage": coverage,
        "limitations": limitations,
    }


def list_antigravity_sessions(home, include_archived=False):
    """List Antigravity sessions across Desktop, IDE, and CLI summary DBs."""
    sessions = []
    seen = set()
    for variant, rel in _ANTIGRAVITY_DIRS:
        base = home / rel
        db = base / "conversation_summaries.db"
        if not db.is_file():
            continue
        cols = _table_columns(db, "conversation_summaries")
        if "conversation_id" not in cols:
            continue
        wanted = [
            "conversation_id",
            "title" if "title" in cols else "NULL",
            "preview" if "preview" in cols else "NULL",
            "workspace_uris" if "workspace_uris" in cols else "NULL",
            "last_modified_time" if "last_modified_time" in cols else "NULL",
            "last_user_input_time" if "last_user_input_time" in cols else "NULL",
            "parent_conversation_id" if "parent_conversation_id" in cols else "NULL",
            "step_count" if "step_count" in cols else "NULL",
        ]
        order_col = "last_modified_time" if "last_modified_time" in cols else "rowid"
        rows = _safe_query(
            db,
            f"SELECT {', '.join(wanted)} FROM conversation_summaries ORDER BY {order_col} DESC",
        )
        for (
            cid,
            title,
            preview,
            uris_raw,
            mod_ts,
            input_ts,
            parent_id,
            step_count,
        ) in rows:
            if not cid or cid in seen:
                continue
            if parent_id and not include_archived:
                continue
            seen.add(cid)
            roots = []
            try:
                for uri in json.loads(uris_raw or "[]"):
                    norm = _safe_root(uri)
                    if norm and norm not in roots:
                        roots.append(norm)
            except ValueError:
                pass
            brain_dir = base / "brain" / cid
            transcript = brain_dir / ".system_generated" / "logs" / "transcript.jsonl"
            updated = activity_time(mod_ts) or activity_time(input_ts)
            sessions.append(
                {
                    "agent": "antigravity",
                    "session_id": cid,
                    "ref": _make_ref("antigravity", cid),
                    "title": _first_line(title or preview or "")
                    or "(未命名 Antigravity 会话)",
                    "cwd": roots[0] if roots else None,
                    "roots": roots,
                    "created_at": None,
                    "updated_at": updated,
                    "archived": bool(parent_id),
                    "model": None,
                    "git_branch": None,
                    "source": variant,
                    "coverage": "full" if transcript.is_file() else "summary_only",
                    "meta": {
                        "summary_db": str(db),
                        "brain_dir": str(brain_dir),
                        "transcript_path": str(transcript),
                        "preview": preview,
                        "step_count": step_count,
                    },
                }
            )
    return sessions


def read_antigravity_session(home, session):
    """Read Antigravity transcript.jsonl (or fallback to conversations_fts)."""
    del home
    cid = session["session_id"]
    meta = session.get("meta") or {}
    source_paths = [meta["summary_db"]] if meta.get("summary_db") else []
    messages = []
    model = None

    transcript = Path(meta.get("transcript_path") or "")
    if transcript.is_file():
        source_paths.append(str(transcript))
        try:
            with transcript.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    rec_type = obj.get("type")
                    ts = activity_time(obj.get("created_at"))
                    if obj.get("model") and not model:
                        model = obj.get("model")
                    if rec_type == "USER_INPUT":
                        text = _extract_content_text(obj.get("content"))
                        if text:
                            _append_message(messages, "user", text, ts)
                    elif rec_type == "PLANNER_RESPONSE":
                        text = _extract_content_text(obj.get("content"))
                        if text:
                            _append_message(messages, "assistant", text, ts)
        except OSError:
            pass

    if not messages and meta.get("summary_db"):
        db = Path(meta["summary_db"])
        fts_cols = _table_columns(db, "conversations_fts")
        if {"conversation_id", "user_body", "agent_body"}.issubset(fts_cols):
            rows = _safe_query(
                db,
                "SELECT user_body, agent_body FROM conversations_fts WHERE conversation_id=? ORDER BY chunk_index ASC",
                (cid,),
            )
            for user_body, agent_body in rows:
                if user_body:
                    _append_message(messages, "user", user_body)
                if agent_body:
                    _append_message(messages, "assistant", agent_body)

    artifacts = []
    brain_dir = Path(meta.get("brain_dir") or "")
    if brain_dir.is_dir():
        try:
            for item in sorted(brain_dir.iterdir()):
                if item.is_file() and item.suffix == ".md":
                    artifacts.append({"kind": "file", "path": str(item)})
        except OSError:
            pass

    summary = _clean_text(meta.get("preview") or "") or None
    coverage = "full" if messages else ("summary_only" if summary else "meta_only")
    limitations = None
    if coverage != "full":
        limitations = "未找到该 Antigravity 会话的 transcript.jsonl，已回退摘要库信息。"

    return {
        "messages": messages,
        "summary": summary,
        "changed_files": [],
        "artifacts": artifacts,
        "source_paths": list(dict.fromkeys(source_paths)),
        "coverage": coverage,
        "limitations": limitations,
        "model": model,
    }


def _cursor_workspace_map(home):
    """Map Cursor workspaceStorage hash IDs to normalized root paths."""
    base = home / SUPPORT / EDITORS["cursor"]
    storage = base / "User/workspaceStorage"
    mapping = {}
    if not storage.is_dir():
        return mapping
    try:
        entries = list(storage.iterdir())
    except OSError:
        return mapping
    for folder in entries:
        wj = folder / "workspace.json"
        if not wj.is_file():
            continue
        try:
            obj = read_json(wj)
        except (OSError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        roots = []
        if obj.get("folder"):
            norm = _safe_root(obj["folder"])
            if norm:
                roots.append(norm)
        elif obj.get("workspace"):
            ws_root = _safe_root(obj["workspace"])
            if ws_root and os.path.isabs(ws_root) and Path(ws_root).is_file():
                try:
                    ws_obj = workspace_json(Path(ws_root))
                    for item in ws_obj.get("folders") or ():
                        if isinstance(item, dict):
                            raw = (
                                item["uri"]
                                if "uri" in item
                                else str(Path(ws_root).parent / item["path"])
                            )
                            norm = _safe_root(raw)
                            if norm and norm not in roots:
                                roots.append(norm)
                except (OSError, ValueError, KeyError):
                    pass
            if not roots and ws_root:
                roots.append(ws_root)
        if roots:
            mapping[folder.name] = roots
    return mapping


def _find_cursor_transcript(home, composer_id, roots):
    projects_dir = home / ".cursor" / "projects"
    if not projects_dir.is_dir():
        return None
    slugs = []
    for root in roots or ():
        slug = _project_slug(root)
        if slug and slug not in slugs:
            slugs.append(slug)
        parent_slug = _project_slug(str(Path(root).parent)) if root else None
        if parent_slug and parent_slug not in slugs:
            slugs.append(parent_slug)
    for slug in slugs:
        at_dir = projects_dir / slug / "agent-transcripts"
        if not at_dir.is_dir():
            continue
        for candidate in (
            at_dir / f"{composer_id}.jsonl",
            at_dir / composer_id / f"{composer_id}.jsonl",
        ):
            if candidate.is_file():
                return candidate
    return None


def list_cursor_sessions(home, include_archived=False):
    """List Cursor sessions via the fast composerHeaders table (never scans cursorDiskKV)."""
    db = home / SUPPORT / EDITORS["cursor"] / "User/globalStorage/state.vscdb"
    if not db.is_file():
        return []
    cols = _table_columns(db, "composerHeaders")
    if "composerId" not in cols:
        return []
    clauses = []
    if not include_archived:
        if "isSubagent" in cols:
            clauses.append("COALESCE(isSubagent, 0) = 0")
        if "isArchived" in cols:
            clauses.append("COALESCE(isArchived, 0) = 0")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = "lastUpdatedAt DESC" if "lastUpdatedAt" in cols else "rowid DESC"
    rows = _safe_query(
        db,
        f"""SELECT composerId,
                   {'workspaceId' if 'workspaceId' in cols else 'NULL'},
                   {'createdAt' if 'createdAt' in cols else 'NULL'},
                   {'lastUpdatedAt' if 'lastUpdatedAt' in cols else 'NULL'},
                   {'isArchived' if 'isArchived' in cols else '0'},
                   {'value' if 'value' in cols else 'NULL'}
              FROM composerHeaders {where} ORDER BY {order}""",
    )
    ws_map = _cursor_workspace_map(home)
    sessions = []
    for cid, wid, created_raw, updated_raw, archived, raw_val in rows:
        if not cid:
            continue
        info = {}
        if raw_val:
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, dict):
                    info = parsed
            except ValueError:
                pass
        if info.get("isDraft") and not info.get("name") and not include_archived:
            continue
        roots = list(ws_map.get(wid, []))
        for repo in info.get("trackedGitRepos") or ():
            if isinstance(repo, str):
                norm = _safe_root(repo)
                if norm and norm not in roots:
                    roots.append(norm)
        transcript = _find_cursor_transcript(home, cid, roots)
        title = _first_line(info.get("name") or info.get("subtitle") or "")
        sessions.append(
            {
                "agent": "cursor",
                "session_id": cid,
                "ref": _make_ref("cursor", cid),
                "title": title or "(未命名 Cursor 会话)",
                "cwd": roots[0] if roots else None,
                "roots": roots,
                "created_at": activity_time(created_raw),
                "updated_at": activity_time(updated_raw),
                "archived": bool(archived),
                "model": None,
                "git_branch": None,
                "source": info.get("unifiedMode") or info.get("forceMode"),
                "coverage": "full",
                "meta": {
                    "state_db": str(db),
                    "workspace_id": wid,
                    "transcript_path": str(transcript) if transcript else None,
                    "subtitle": info.get("subtitle"),
                    "files_changed_count": info.get("filesChangedCount"),
                    "lines_added": info.get("totalLinesAdded"),
                    "lines_removed": info.get("totalLinesRemoved"),
                },
            }
        )
    return sessions


def _read_cursor_transcript_jsonl(path):
    messages = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                role = obj.get("role")
                if role not in ("user", "assistant"):
                    continue
                msg = obj.get("message")
                if isinstance(msg, dict):
                    text = _extract_content_text(msg.get("content"))
                else:
                    text = _extract_content_text(msg)
                if text:
                    _append_message(messages, role, text)
    except OSError:
        return []
    return messages


def _read_cursor_disk_kv_point(db_path, composer_id, max_bubbles=80):
    """Exact primary-key point lookups in cursorDiskKV (never scans the table)."""
    rows = _safe_query(
        db_path,
        "SELECT value FROM cursorDiskKV WHERE key=? LIMIT 1",
        (f"composerData:{composer_id}",),
    )
    if not rows or not rows[0][0]:
        return [], []
    try:
        composer = json.loads(rows[0][0])
    except ValueError:
        return [], []
    if not isinstance(composer, dict):
        return [], []

    headers = composer.get("fullConversationHeadersOnly") or []
    if len(headers) > max_bubbles:
        # Keep the opening header (goal) plus the most recent window.
        headers = headers[:4] + headers[-(max_bubbles - 4) :]

    messages = []
    changed_files = []
    for item in headers:
        if not isinstance(item, dict):
            continue
        bid = item.get("bubbleId")
        if not bid:
            continue
        brows = _safe_query(
            db_path,
            "SELECT value FROM cursorDiskKV WHERE key=? LIMIT 1",
            (f"bubbleId:{composer_id}:{bid}",),
        )
        if not brows or not brows[0][0]:
            continue
        try:
            bobj = json.loads(brows[0][0])
        except ValueError:
            continue
        if not isinstance(bobj, dict):
            continue
        btype = bobj.get("type")
        role = "user" if btype == 1 else ("assistant" if btype == 2 else None)
        if not role:
            continue
        text = _clean_text(bobj.get("text") or bobj.get("richText") or "")
        if text:
            _append_message(messages, role, text, activity_time(bobj.get("createdAt")))

    for fpath in composer.get("newlyCreatedFiles") or ():
        if isinstance(fpath, dict) and fpath.get("uri"):
            norm = _safe_root(fpath["uri"])
            if norm and norm not in changed_files:
                changed_files.append(norm)
        elif isinstance(fpath, str) and fpath not in changed_files:
            changed_files.append(fpath)
    return messages, changed_files


def read_cursor_session(home, session):
    """Read Cursor session from agent-transcripts JSONL, falling back to cursorDiskKV."""
    cid = session["session_id"]
    meta = session.get("meta") or {}
    source_paths = [meta["state_db"]] if meta.get("state_db") else []
    messages = []
    changed_files = []

    tpath = Path(meta["transcript_path"]) if meta.get("transcript_path") else None
    if not tpath or not tpath.is_file():
        tpath = _find_cursor_transcript(home, cid, session.get("roots"))
    if tpath and tpath.is_file():
        source_paths.append(str(tpath))
        messages = _read_cursor_transcript_jsonl(tpath)

    if not messages and meta.get("state_db"):
        messages, changed_files = _read_cursor_disk_kv_point(
            Path(meta["state_db"]), cid
        )

    summary = _clean_text(meta.get("subtitle") or "") or None
    coverage = "full" if messages else ("summary_only" if summary else "meta_only")
    limitations = None
    if coverage != "full":
        limitations = "该 Cursor 会话在 agent-transcripts 与 cursorDiskKV 中未找到可读对话正文。"

    return {
        "messages": messages,
        "summary": summary,
        "changed_files": changed_files,
        "artifacts": [],
        "source_paths": list(dict.fromkeys(source_paths)),
        "coverage": coverage,
        "limitations": limitations,
    }


def _codebuddy_jsonl_meta(path):
    cwd = None
    session_id = path.stem
    first_ts = None
    last_ts = None
    title = ""
    for label, raw in session_edges(path):
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("cwd") and not cwd:
            cwd = _safe_root(event["cwd"])
        if event.get("sessionId"):
            session_id = str(event["sessionId"])
        ts = activity_time(event.get("timestamp"))
        if label == "first" and ts:
            first_ts = ts
        if ts and (not last_ts or ts > last_ts):
            last_ts = ts
        if not title and event.get("type") == "message" and event.get("role") == "user":
            title = _first_line(_extract_content_text(event.get("content")))

    if not title:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh):
                    if idx >= 40:
                        break
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("cwd") and not cwd:
                        cwd = _safe_root(event["cwd"])
                    if event.get("type") == "message" and event.get("role") == "user":
                        text = _extract_content_text(event.get("content"))
                        if text:
                            title = _first_line(text)
                            break
        except OSError:
            pass

    if not last_ts:
        try:
            last_ts = activity_time(path.stat().st_mtime)
        except OSError:
            last_ts = None
    return {
        "agent": "codebuddy",
        "session_id": session_id,
        "ref": _make_ref("codebuddy", session_id),
        "title": title or "(未命名 CodeBuddy CLI 会话)",
        "cwd": cwd,
        "roots": [cwd] if cwd else [],
        "created_at": first_ts,
        "updated_at": last_ts,
        "archived": False,
        "model": None,
        "git_branch": None,
        "source": "cli_jsonl",
        "coverage": "full",
        "meta": {"jsonl_path": str(path)},
    }


def list_codebuddy_sessions(home, include_archived=False):
    """List CodeBuddy CLI JSONL sessions and CodeBuddy CN IDE vscdb sessions."""
    del include_archived
    by_id = {}

    projects_dir = home / ".codebuddy" / "projects"
    if projects_dir.is_dir():
        try:
            folders = list(projects_dir.iterdir())
        except OSError:
            folders = []
        for folder in folders:
            if not folder.is_dir():
                continue
            try:
                files = list(folder.iterdir())
            except OSError:
                continue
            for path in files:
                if path.suffix != ".jsonl":
                    continue
                try:
                    if path.stat().st_size <= 0:
                        continue
                except OSError:
                    continue
                item = _codebuddy_jsonl_meta(path)
                by_id[item["session_id"]] = item

    cb_support = home / SUPPORT / EDITORS["codebuddy"]
    vscdb = cb_support / "codebuddy-sessions.vscdb"
    copilot_dir = cb_support / "User/globalStorage/tencent-cloud.coding-copilot"
    if vscdb.is_file():
        rows = _safe_query(
            vscdb,
            "SELECT key, value FROM ItemTable WHERE key LIKE 'session:%'",
        )
        for key, raw in rows:
            try:
                obj = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            cid = str(obj.get("conversationId") or key.split(":", 1)[-1])
            if not cid or cid in by_id:
                continue
            cwd = _safe_root(obj.get("cwd"))
            edit_session = copilot_dir / "edit-sessions" / f"{cid}.json"
            overview_md = copilot_dir / "brain" / cid / "overview.md"
            has_diffs = edit_session.is_file()
            by_id[cid] = {
                "agent": "codebuddy",
                "session_id": cid,
                "ref": _make_ref("codebuddy", cid),
                "title": _first_line(obj.get("title") or "")
                or "(未命名 CodeBuddy IDE 会话)",
                "cwd": cwd,
                "roots": [cwd] if cwd else [],
                "created_at": activity_time(obj.get("createdAt")),
                "updated_at": activity_time(obj.get("updatedAt")),
                "archived": False,
                "model": None,
                "git_branch": None,
                "source": "ide_vscdb",
                "coverage": "meta_and_diffs" if has_diffs else "meta_only",
                "meta": {
                    "vscdb_path": str(vscdb),
                    "edit_session_path": str(edit_session) if has_diffs else None,
                    "overview_path": str(overview_md)
                    if overview_md.is_file()
                    else None,
                    "status": obj.get("status"),
                },
            }

    return list(by_id.values())


def read_codebuddy_session(home, session):
    """Read CodeBuddy CLI JSONL messages or IDE metadata + edit-session fileDiffs."""
    del home
    meta = session.get("meta") or {}
    source_paths = []
    messages = []
    changed_files = []
    artifacts = []
    summary = None

    jsonl_path = Path(meta["jsonl_path"]) if meta.get("jsonl_path") else None
    if jsonl_path and jsonl_path.is_file():
        source_paths.append(str(jsonl_path))
        try:
            with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("type") != "message":
                        continue
                    role = obj.get("role")
                    if role not in ("user", "assistant"):
                        continue
                    text = _extract_content_text(obj.get("content"))
                    if text:
                        _append_message(
                            messages, role, text, activity_time(obj.get("timestamp"))
                        )
        except OSError:
            pass
        return {
            "messages": messages,
            "summary": None,
            "changed_files": changed_files,
            "artifacts": artifacts,
            "source_paths": source_paths,
            "coverage": "full" if messages else "meta_only",
            "limitations": None
            if messages
            else "未在 CodeBuddy CLI 会话文件中解析到对话消息。",
        }

    if meta.get("vscdb_path"):
        source_paths.append(meta["vscdb_path"])
    if meta.get("edit_session_path"):
        es_path = Path(meta["edit_session_path"])
        if es_path.is_file():
            source_paths.append(str(es_path))
            try:
                es_obj = read_json(es_path)
                diffs = es_obj.get("fileDiffs") if isinstance(es_obj, dict) else None
                if isinstance(diffs, dict):
                    changed_files = sorted(str(k) for k in diffs.keys())
                elif isinstance(diffs, list):
                    for item in diffs:
                        if isinstance(item, dict) and item.get("uri"):
                            norm = _safe_root(item["uri"])
                            if norm and norm not in changed_files:
                                changed_files.append(norm)
            except (OSError, ValueError):
                pass
    if meta.get("overview_path"):
        ov = Path(meta["overview_path"])
        if ov.is_file():
            source_paths.append(str(ov))
            artifacts.append({"kind": "file", "path": str(ov)})
            try:
                summary = _clean_text(ov.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass

    coverage = "meta_and_diffs" if changed_files else "meta_only"
    return {
        "messages": [],
        "summary": summary,
        "changed_files": changed_files,
        "artifacts": artifacts,
        "source_paths": source_paths,
        "coverage": coverage,
        "limitations": (
            "CodeBuddy CN IDE 会话正文未以明文 JSONL 落盘；"
            "已提取本地会话元信息与 edit-sessions 文件改动清单。"
            if changed_files
            else "CodeBuddy CN IDE 会话正文未以明文 JSONL 落盘；本地仅包含会话元信息。"
        ),
    }


PROVIDERS = {
    "codex": (list_codex_sessions, read_codex_session),
    "antigravity": (list_antigravity_sessions, read_antigravity_session),
    "cursor": (list_cursor_sessions, read_cursor_session),
    "codebuddy": (list_codebuddy_sessions, read_codebuddy_session),
}
