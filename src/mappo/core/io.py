"""Read-only JSON, JSONC, SQLite, directory, and JSONL history helpers."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from mappo.core.models import activity_time, error_code, update_activity


def read_json(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


# Keep quoted strings intact when dropping JSONC comments and trailing commas.
JSONC = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*.*?\*/', re.S)
TRAILING_COMMA = re.compile(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])')


def workspace_json(path):
    raw = path.read_text(encoding="utf-8-sig")
    raw = JSONC.sub(lambda m: m[0] if m[0].startswith('"') else " ", raw)
    return json.loads(TRAILING_COMMA.sub(lambda m: "" if m[0] == "," else m[0], raw))


def query(path, statement, params=()):
    # A WAL reader requires shared memory. Never create sidecars in a source directory.
    # Surface ENOENT and EACCES separately; SQLite maps both to CANTOPEN.
    with path.open("rb") as stream:
        wal_mode = stream.read(20)[18:20] == b"\x02\x02"
    wal = Path(str(path) + "-wal")
    has_wal = wal.exists()
    if has_wal and not Path(str(path) + "-shm").exists():
        raise BlockingIOError(
            "WAL exists without shared memory; retry after writer checkpoints"
        )
    options = "?mode=ro"
    if wal_mode and not has_wal:
        # A checkpointed WAL database may have no sidecars. SQLite otherwise
        # creates them even for readers. Rollback-journal readers retain locking.
        options += "&immutable=1"
    with closing(sqlite3.connect(path.as_uri() + options, uri=True, timeout=0.2)) as db:
        return db.execute(statement, params).fetchall()


def sql_paths(inv, agent, path, statement, label, kind, time_field=None):
    with inv.source(agent, path):
        for root, *times in query(path, statement):
            if root:
                with inv.source(agent, path):
                    row = inv.add(agent, kind, [root], str(path) + "#" + label)
                    if times:
                        update_activity(
                            row, activity_time(times[0]), str(path) + "#" + time_field
                        )


def dated_paths(inv, agent, path, table, root, time_field, kind, where=""):
    with inv.source(agent, path):
        columns = {r[1] for r in query(path, f"PRAGMA table_info({table})")}
        time_column = f",MAX({time_field})" if time_field in columns else ""
        sql_paths(
            inv,
            agent,
            path,
            f"SELECT {root}{time_column} FROM {table} {where} GROUP BY {root}",
            f"{table}.{root}",
            kind,
            f"{table}.{time_field}",
        )


def children(inv, agent, directory):
    try:
        return sorted(directory.iterdir())
    except FileNotFoundError:
        return []
    except OSError as error:
        inv.note(agent, directory, str(error), error_code(error))
    return []


def history_projects(inv, agent):
    path = inv.home / ("." + agent) / "history.jsonl"
    if path.is_file():
        with inv.source(agent, path), path.open("rb") as stream:
            for index, line in enumerate(stream, 1):
                with inv.source(agent, f"{path}#{index}"):
                    event = json.loads(line)
                    root = event.get("project")
                    if root:
                        row = inv.add(agent, "inferred", [root], str(path) + "#project")
                        update_activity(
                            row,
                            activity_time(event.get("timestamp")),
                            f"{path}#{index}.timestamp",
                        )
