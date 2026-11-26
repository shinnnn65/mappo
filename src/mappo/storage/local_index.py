"""Per-user scan snapshots, manual links, and local project metadata."""

import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from mappo.core.classify import annotate_project
from mappo.core.models import path_state
from mappo.providers.registry import (
    EXTENSIONS,
    PRODUCTS,
    detect_extension_hosts,
    tool_category,
)

MAX_TAG_LENGTH = 32
MAX_TAGS_PER_PROJECT = 20


def scope_key(agent, paths):
    roots = sorted({os.path.abspath(os.path.expanduser(path)) for path in paths})
    return json.dumps([agent, roots], ensure_ascii=False)


def normalize_tag(raw):
    if not isinstance(raw, str):
        raise ValueError("标签必须是文本")
    tag = " ".join(raw.strip().split())
    if not tag:
        raise ValueError("标签不能为空")
    if len(tag) > MAX_TAG_LENGTH:
        raise ValueError(f"标签长度不能超过 {MAX_TAG_LENGTH} 个字符")
    return tag


def normalize_tags(values):
    if not isinstance(values, (list, tuple, set)):
        raise ValueError("标签列表格式无效")
    seen = {}
    for raw in values:
        tag = normalize_tag(raw)
        key = tag.casefold()
        if key not in seen:
            seen[key] = tag
    if len(seen) > MAX_TAGS_PER_PROJECT:
        raise ValueError(f"单个项目最多添加 {MAX_TAGS_PER_PROJECT} 个标签")
    return sorted(seen.values(), key=lambda item: (item.casefold(), item))


class LocalIndex:
    def __init__(self, filename=None):
        if filename is not None:
            self.path = Path(filename).expanduser()
        else:
            self.path = (Path.home() / ".local/state/mappo/index.sqlite").expanduser()
            legacy = (Path.home() / ".local/state/awh/index.sqlite").expanduser()
            if not self.path.exists() and legacy.is_file():
                try:
                    self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copy2(legacy, self.path)
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass

    def connect(self, writable=False):
        if writable:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
            db = sqlite3.connect(self.path, timeout=5)
        else:
            db = sqlite3.connect(
                self.path.absolute().as_uri() + "?mode=ro", uri=True, timeout=5
            )
        return closing(db)

    @staticmethod
    def _ensure_schema(db):
        db.execute(
            "CREATE TABLE IF NOT EXISTS snapshots (scope TEXT PRIMARY KEY, result TEXT NOT NULL)"
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS links (
               left_id TEXT, right_id TEXT, PRIMARY KEY(left_id, right_id))"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS project_meta (
               project_id TEXT PRIMARY KEY,
               favorite INTEGER NOT NULL DEFAULT 0,
               hidden INTEGER NOT NULL DEFAULT 0,
               promoted INTEGER NOT NULL DEFAULT 0,
               updated_at TEXT NOT NULL)"""
        )
        columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(project_meta)")
        }
        if "promoted" not in columns:
            db.execute(
                "ALTER TABLE project_meta ADD COLUMN promoted INTEGER NOT NULL DEFAULT 0"
            )
        db.execute(
            """CREATE TABLE IF NOT EXISTS project_tags (
               project_id TEXT NOT NULL,
               tag TEXT NOT NULL,
               created_at TEXT NOT NULL,
               PRIMARY KEY(project_id, tag))"""
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_tags_tag ON project_tags(tag)"
        )

    @staticmethod
    def _tables(db):
        return {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def save(self, scope, result):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect(writable=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure_schema(db)
            previous = db.execute(
                "SELECT result FROM snapshots WHERE scope=?", (scope,)
            ).fetchone()
            old = json.loads(previous[0]) if previous else {}
            for project in result["projects"]:
                project.update(index_state="observed", last_seen=now)
            found = {project["id"] for project in result["projects"]}
            workspaces = {row["id"]: row for row in old.get("workspaces", [])}
            for project in old.get("projects", []):
                if project["id"] in found:
                    continue
                evidence = project.get("historical_evidence")
                if evidence is None:
                    evidence = [
                        workspaces[key]
                        for key in project["workspaces"]
                        if key in workspaces
                    ]
                result["projects"].append(
                    dict(
                        project,
                        index_state="historical",
                        status=path_state(project["path"]),
                        workspaces=[],
                        historical_evidence=evidence,
                    )
                )
            result["projects"].sort(key=lambda row: row["path"])
            result["indexed_at"] = now
            db.execute(
                "INSERT OR REPLACE INTO snapshots VALUES (?, ?)",
                (scope, json.dumps(result, ensure_ascii=False)),
            )
            return self.with_links(db, result)

    def load(self, scope):
        if self.path.is_file():
            with self.connect() as db:
                db.execute("BEGIN")
                try:
                    if "snapshots" in self._tables(db):
                        result = db.execute(
                            "SELECT result FROM snapshots WHERE scope=?", (scope,)
                        ).fetchone()
                        if result:
                            return self.with_links(db, json.loads(result[0]))
                finally:
                    if db.in_transaction:
                        db.rollback()
        raise ValueError(
            "该扫描范围没有本地索引，请先用相同的 --agent 和 --path 执行 mappo scan"
        )

    def load_or_scan(self, scope, scan_fn):
        try:
            return self.load(scope)
        except ValueError:
            return self.save(scope, scan_fn())

    def hydrate_live(self, result):
        """Attach persisted links and user metadata onto a live scan result if an index exists."""
        if self.path.is_file():
            with self.connect() as db:
                db.execute("BEGIN")
                try:
                    return self.with_links(db, result)
                finally:
                    if db.in_transaction:
                        db.rollback()
        return self._decorate_defaults(result)

    def change_link(self, scope, first, second, remove=False):
        if first == second:
            raise ValueError("请选择两个不同的项目 ID")
        if not self.path.is_file():
            raise ValueError("请先执行 mappo scan 建立索引")
        pair = sorted((first, second))
        with self.connect(writable=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure_schema(db)
            if remove:
                db.execute("DELETE FROM links WHERE left_id=? AND right_id=?", pair)
                return
            row = db.execute(
                "SELECT result FROM snapshots WHERE scope=?", (scope,)
            ).fetchone()
            known = (
                {project["id"] for project in json.loads(row[0])["projects"]}
                if row
                else set()
            )
            if not known.issuperset(pair):
                raise ValueError("两个项目 ID 都必须存在于该扫描范围的索引")
            db.execute("INSERT OR IGNORE INTO links VALUES (?, ?)", pair)

    def update_meta(
        self,
        scope,
        project_id,
        *,
        favorite=None,
        hidden=None,
        promoted=None,
        tags=None,
        add_tags=None,
        remove_tags=None,
    ):
        if not self.path.is_file():
            raise ValueError("请先执行 mappo scan 建立索引")
        now = datetime.now(timezone.utc).isoformat()
        with self.connect(writable=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure_schema(db)
            row = db.execute(
                "SELECT result FROM snapshots WHERE scope=?", (scope,)
            ).fetchone()
            known = (
                {project["id"] for project in json.loads(row[0])["projects"]}
                if row
                else set()
            )
            if project_id not in known:
                raise ValueError("未找到该项目 ID，请使用相同的扫描范围或先执行 mappo scan")
            current_meta = db.execute(
                "SELECT favorite, hidden, promoted FROM project_meta WHERE project_id=?",
                (project_id,),
            ).fetchone()
            cur_fav = bool(current_meta[0]) if current_meta else False
            cur_hidden = bool(current_meta[1]) if current_meta else False
            cur_promoted = bool(current_meta[2]) if current_meta else False
            cur_tags = [
                r[0]
                for r in db.execute(
                    "SELECT tag FROM project_tags WHERE project_id=? ORDER BY lower(tag), tag",
                    (project_id,),
                )
            ]
            new_fav = cur_fav if favorite is None else bool(favorite)
            new_hidden = cur_hidden if hidden is None else bool(hidden)
            new_promoted = cur_promoted if promoted is None else bool(promoted)
            if tags is not None:
                new_tags = normalize_tags(tags)
            else:
                merged = list(cur_tags)
                if add_tags is not None:
                    if not isinstance(add_tags, (list, tuple, set)):
                        raise ValueError("add_tags 必须是标签列表")
                    merged.extend(add_tags)
                if remove_tags is not None:
                    if not isinstance(remove_tags, (list, tuple, set)):
                        raise ValueError("remove_tags 必须是标签列表")
                    drop = {normalize_tag(item).casefold() for item in remove_tags}
                    merged = [item for item in merged if item.casefold() not in drop]
                new_tags = normalize_tags(merged)
            if new_fav or new_hidden or new_promoted:
                db.execute(
                    """INSERT INTO project_meta (project_id, favorite, hidden, promoted, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(project_id) DO UPDATE SET
                         favorite=excluded.favorite,
                         hidden=excluded.hidden,
                         promoted=excluded.promoted,
                         updated_at=excluded.updated_at""",
                    (project_id, int(new_fav), int(new_hidden), int(new_promoted), now),
                )
            else:
                db.execute(
                    "DELETE FROM project_meta WHERE project_id=?", (project_id,)
                )
            if tags is not None or add_tags is not None or remove_tags is not None:
                db.execute(
                    "DELETE FROM project_tags WHERE project_id=?", (project_id,)
                )
                for tag in new_tags:
                    db.execute(
                        "INSERT INTO project_tags (project_id, tag, created_at) VALUES (?, ?, ?)",
                        (project_id, tag, now),
                    )
            return {
                "project_id": project_id,
                "favorite": new_fav,
                "hidden": new_hidden,
                "promoted": new_promoted,
                "tags": new_tags,
            }

    @staticmethod
    def _decorate_defaults(result, home=None):
        workspaces_by_agent = None
        for agent in result.get("agents", []):
            aid = agent["agent"]
            agent.setdefault(
                "display_name", PRODUCTS.get(aid, (aid, ""))[0]
            )
            agent.setdefault("category", tool_category(aid))
            if aid in EXTENSIONS and "host_editors" not in agent:
                if workspaces_by_agent is None:
                    workspaces_by_agent = {}
                    for row in result.get("workspaces", []):
                        workspaces_by_agent.setdefault(row["agent"], []).append(row)
                agent["host_editors"] = detect_extension_hosts(
                    installed=agent.get("installed"),
                    data=agent.get("data"),
                    workspaces=workspaces_by_agent.get(aid, ()),
                )
        for project in result.get("projects", []):
            project.setdefault("favorite", False)
            project.setdefault("hidden", False)
            project.setdefault("promoted", False)
            project.setdefault("tags", [])
            if "asset_kind" not in project:
                annotate_project(project, home=home)
        return result

    @staticmethod
    def with_links(db, result, home=None):
        LocalIndex._decorate_defaults(result, home=home)
        tables = LocalIndex._tables(db)
        by_id = {row["id"]: row for row in result.get("projects", [])}
        if "links" in tables:
            for left, right in db.execute(
                "SELECT left_id,right_id FROM links ORDER BY left_id,right_id"
            ):
                for key, related in ((left, right), (right, left)):
                    if key in by_id:
                        by_id[key].setdefault("related_projects", []).append(related)
        if "project_meta" in tables:
            meta_cols = {
                row[1] for row in db.execute("PRAGMA table_info(project_meta)")
            }
            if "promoted" in meta_cols:
                rows = db.execute(
                    "SELECT project_id, favorite, hidden, promoted FROM project_meta"
                )
                for project_id, favorite, hidden, promoted in rows:
                    if project_id in by_id:
                        by_id[project_id]["favorite"] = bool(favorite)
                        by_id[project_id]["hidden"] = bool(hidden)
                        by_id[project_id]["promoted"] = bool(promoted)
            else:
                for project_id, favorite, hidden in db.execute(
                    "SELECT project_id, favorite, hidden FROM project_meta"
                ):
                    if project_id in by_id:
                        by_id[project_id]["favorite"] = bool(favorite)
                        by_id[project_id]["hidden"] = bool(hidden)
                        by_id[project_id]["promoted"] = False
        if "project_tags" in tables:
            tags_by_id = {}
            for project_id, tag in db.execute(
                "SELECT project_id, tag FROM project_tags ORDER BY lower(tag), tag"
            ):
                if project_id in by_id:
                    tags_by_id.setdefault(project_id, []).append(tag)
            for project_id, tags in tags_by_id.items():
                by_id[project_id]["tags"] = tags
        for project in result.get("projects", []):
            if project.get("promoted") or "asset_kind" not in project:
                annotate_project(project, home=home)
        return result
