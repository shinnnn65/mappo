"""Codex workspace provider (SQLite state DB and desktop JSON fallback)."""

import json
from pathlib import Path

from mappo.core.io import children, dated_paths, query, read_json
from mappo.core.models import activity_time, root_path, update_activity


def codex(inv):
    base = inv.home / ".codex"
    dbs = sorted(
        (
            p
            for p in children(inv, "codex", base)
            if p.match("state_*.sqlite") and p.stem[6:].isdigit()
        ),
        key=lambda p: int(p.stem.split("_")[-1]),
    )
    native_ok = False
    if dbs:
        db = dbs[-1]
        with inv.source("codex", db):
            columns = {r[1] for r in query(db, "PRAGMA table_info(projects)")}
            updated = "p.updated_at_ms" if "updated_at_ms" in columns else "NULL"
            rows = query(
                db,
                f"""SELECT p.id,p.name,r.path,{updated} FROM projects p LEFT JOIN project_roots r
                         ON p.id=r.project_id ORDER BY p.position,r.position""",
            )
            for key, name, path, stamp in rows:
                row = inv.add(
                    "codex",
                    "native",
                    [path] if path else [],
                    str(db) + "#projects",
                    key,
                    name,
                )
                update_activity(
                    row, activity_time(stamp), str(db) + "#projects.updated_at_ms"
                )
                if (
                    path
                    and Path(path).parent == base / ".chatgpt-projects"
                    and Path(path).name.startswith("g-p-")
                ):
                    row["chatgpt_project_id"] = Path(path).name
                    row["native_type"] = "chatgpt_project"
                    row.setdefault("managed_roots", []).append(root_path(path))
            native_ok = True
        dated_paths(inv, "codex", db, "threads", "cwd", "updated_at", "inferred")
        if native_ok:
            codex_desktop_ids(inv, base)
    if not native_ok:
        path = base / ".codex-global-state.json"
        with inv.source("codex", path):
            data = read_json(path)
            for key, project in data.get("local-projects", {}).items():
                inv.add(
                    "codex",
                    "native",
                    project["rootPaths"],
                    path,
                    key,
                    project.get("name"),
                )
            for key, roots in data.items():
                if key == "electron-saved-workspace-roots" or key.startswith(
                    "electron-owner-value:electron-saved-workspace-roots:"
                ):
                    for root in roots:
                        inv.add(
                            "codex",
                            "native",
                            [root],
                            str(path) + "#saved-workspace-roots",
                        )


def codex_desktop_ids(inv, base):
    db = base / ".codex-global-state.sqlite"
    mapping_key = "app-server-project-id-by-legacy-project-id-by-host"
    file = base / ".codex-global-state.json"
    state = {}
    source = db
    if db.exists():
        with inv.source("codex", db):
            state = {
                key: json.loads(value)
                for key, value in query(
                    db,
                    "SELECT key,value FROM settings WHERE scope='global' AND key IN (?,?)",
                    ("local-projects", mapping_key),
                )
            }
    if mapping_key not in state and file.exists():
        source = file
        with inv.source("codex", file):
            state = read_json(file)
    by_id = {
        r["native_id"]: r
        for r in inv.records.values()
        if r["agent"] == "codex" and r["kind"] == "native"
    }
    for host, mapping in state.get(mapping_key, {}).items():
        if host.startswith("local:"):
            for desktop_id, server_id in mapping.items():
                if server_id in by_id and desktop_id in state.get("local-projects", {}):
                    row = by_id[server_id]
                    row.setdefault("desktop_ids", []).append(desktop_id)
                    evidence = str(source) + "#" + mapping_key
                    if evidence not in row["sources"]:
                        row["sources"].append(evidence)
