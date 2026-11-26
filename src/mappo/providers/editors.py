"""VS Code-family editor and extension workspace provider."""

import json
import os
import stat
from pathlib import Path
from urllib.parse import urlsplit

from mappo.core.io import query, read_json, workspace_json
from mappo.core.models import activity_time, root_path, update_activity
from mappo.providers.registry import SUPPORT


def workspace(inv, agent, uri, config, source, base, native_id=None, kind="native"):
    root = root_path(uri)
    roots = [root]
    if config:
        roots = []
        path = Path(root)
        with inv.source(agent, root):
            if not path.is_absolute():
                raise NotImplementedError("远程工作区配置无法在本机展开")
            if not (
                path.suffix == ".code-workspace"
                or (
                    path.name == "workspace.json"
                    and (base / "Workspaces") in path.parents
                )
            ):
                raise NotImplementedError(
                    "unsupported workspace configuration location"
                )
            if not stat.S_ISREG(path.stat().st_mode):
                raise NotImplementedError("工作区配置必须是普通文件")
            for folder in workspace_json(path)["folders"]:
                roots.append(
                    folder["uri"]
                    if "uri" in folder
                    else str(path.parent / folder["path"])
                )
    row = inv.add(
        agent,
        kind,
        roots,
        source,
        native_id,
        Path(root).stem if config else None,
        identity=(str(base), root, config),
    )
    row["resource"] = uri


def editor(inv, agent, product, extension=None):
    base = inv.home / SUPPORT / product
    storage = base / "User/workspaceStorage"
    db = base / "User/globalStorage/state.vscdb"
    if not extension and not storage.exists() and not db.exists():
        inv.note(
            agent,
            base / "User",
            "缺少 workspaceStorage 和 globalStorage/state.vscdb",
            "missing_source",
        )
    paths = []
    if storage.exists():
        with inv.source(agent, storage):
            for folder in storage.iterdir():
                path = folder / "workspace.json"
                with inv.source(agent, path):
                    if path.is_file():
                        paths.append(path)
    for path in sorted(paths):
        with inv.source(agent, path):
            source = path
            if extension:
                db = path.parent / "state.vscdb"
                if not db.exists() or not query(
                    db,
                    "SELECT 1 FROM ItemTable WHERE key=? COLLATE NOCASE",
                    (extension,),
                ):
                    continue
                source = str(db) + "#" + extension
            obj = read_json(path)
            workspace(
                inv,
                agent,
                obj.get("workspace") or obj["folder"],
                "workspace" in obj,
                source,
                base,
                path.parent.name if not extension else None,
                "inferred" if extension else "native",
            )
    db = base / "User/globalStorage/state.vscdb"
    if not extension and db.exists():
        with inv.source(agent, db):
            for (raw,) in query(
                db,
                "SELECT value FROM ItemTable WHERE key='history.recentlyOpenedPathsList'",
            ):
                for entry in json.loads(raw)["entries"]:
                    with inv.source(agent, db):
                        cfg = entry.get("workspace")
                        uri = cfg["configPath"] if cfg else entry.get("folderUri")
                        if (
                            uri
                            and entry.get("remoteAuthority")
                            and uri.startswith("file:")
                        ):
                            uri = (
                                "vscode-remote://"
                                + entry["remoteAuthority"]
                                + urlsplit(uri).path
                            )
                        if uri:
                            workspace(
                                inv,
                                agent,
                                uri,
                                bool(cfg),
                                str(db) + "#recentlyOpenedPathsList",
                                base,
                                cfg.get("id") if cfg else None,
                            )

    if not extension:
        editor_activity(inv, agent, base / "User/History")


def editor_activity(inv, agent, directory):
    if not directory.exists():
        return
    by_root = {}
    for row in inv.records.values():
        if row["agent"] == agent:
            for root in row["roots"]:
                if os.path.isabs(root):
                    by_root.setdefault(root, []).append(row)
    with inv.source(agent, directory):
        for folder in directory.iterdir():
            index = folder / "entries.json"
            with inv.source(agent, index):
                if not index.is_file():
                    continue
                data = read_json(index)
                resource = root_path(data["resource"])
                if not os.path.isabs(resource):
                    continue
                # Attribute file edits to the nearest known project, never its siblings.
                root = next(
                    (str(p) for p in Path(resource).parents if str(p) in by_root), None
                )
                if root:
                    stamp = max(
                        (
                            activity_time(e.get("timestamp")) or ""
                            for e in data["entries"]
                        ),
                        default="",
                    )
                    for row in by_root[root]:
                        evidence = str(index) + "#entries.timestamp"
                        update_activity(row, stamp, evidence)
                        per_root = row.setdefault("activity_by_root", {}).setdefault(
                            root, {}
                        )
                        update_activity(per_root, stamp, evidence)
