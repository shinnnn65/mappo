"""Antigravity (Desktop, IDE, and CLI) workspace provider."""

import json

from mappo.core.io import children, query, read_json
from mappo.core.models import activity_time, update_activity
from mappo.providers.editors import editor
from mappo.providers.registry import SUPPORT

_SUMMARY_DBS = (
    ".gemini/antigravity/conversation_summaries.db",
    ".gemini/antigravity-ide/conversation_summaries.db",
    ".gemini/antigravity-cli/conversation_summaries.db",
)


def _extract_project_roots(obj):
    resources = (obj.get("projectResources") or {}).get("resources")
    if not isinstance(resources, list):
        return []
    roots = []
    for item in resources:
        if not isinstance(item, dict):
            continue
        uri = None
        for key in ("gitFolder", "localFolder", "folder"):
            sub = item.get(key)
            if isinstance(sub, dict) and sub.get("folderUri"):
                uri = sub["folderUri"]
                break
        if not uri:
            uri = item.get("folderUri") or item.get("uri")
        if uri and uri not in roots:
            roots.append(uri)
    return roots


def agy(inv):
    found_any_source = False

    # 1. Native Antigravity project configs (~/.gemini/config/projects/*.json)
    projects_dir = inv.home / ".gemini/config/projects"
    if projects_dir.exists():
        found_any_source = True
        for path in children(inv, "antigravity", projects_dir):
            if path.suffix != ".json":
                continue
            with inv.source("antigravity", path):
                obj = read_json(path)
                if not isinstance(obj, dict):
                    continue
                roots = _extract_project_roots(obj)
                if roots:
                    inv.add(
                        "antigravity",
                        "native",
                        roots,
                        str(path) + "#projectResources",
                        obj.get("id"),
                        obj.get("name"),
                    )

    # 2. Conversation summary databases (Antigravity 2.0 Desktop, IDE, CLI)
    for rel in _SUMMARY_DBS:
        db = inv.home / rel
        if not db.exists():
            continue
        found_any_source = True
        with inv.source("antigravity", db):
            columns = {
                r[1]
                for r in query(db, "PRAGMA table_info(conversation_summaries)")
            }
            if "workspace_uris" not in columns:
                continue
            time_cols = [
                c
                for c in ("last_modified_time", "last_user_input_time")
                if c in columns
            ]
            select_extra = "".join(f", MAX({c})" for c in time_cols)
            for row_data in query(
                db,
                f"SELECT workspace_uris{select_extra} FROM conversation_summaries GROUP BY workspace_uris",
            ):
                value = row_data[0]
                roots = json.loads(value or "[]")
                if not roots:
                    continue
                row = inv.add(
                    "antigravity", "inferred", roots, str(db) + "#workspace_uris"
                )
                for col, raw_ts in zip(time_cols, row_data[1:]):
                    update_activity(
                        row,
                        activity_time(raw_ts),
                        f"{db}#conversation_summaries.{col}",
                    )

    # 3. Antigravity IDE (VS Code-family workspaceStorage / recentlyOpenedPathsList / History)
    ide_base = inv.home / SUPPORT / "Antigravity IDE"
    if ide_base.exists():
        found_any_source = True
        editor(inv, "antigravity", "Antigravity IDE")

    if not found_any_source:
        inv.note(
            "antigravity",
            inv.home / ".gemini/antigravity/conversation_summaries.db",
            "未找到 Antigravity 项目配置、会话摘要库或 IDE 工作区数据",
            "missing_source",
        )
