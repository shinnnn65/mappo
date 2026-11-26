"""CodeBuddy CLI session and history provider."""

import json
import os

from mappo.core.io import children, history_projects, sql_paths
from mappo.core.models import activity_time, update_activity
from mappo.providers.registry import EDITORS, SUPPORT


def codebuddy_history(inv):
    db = inv.home / SUPPORT / EDITORS["codebuddy"] / "codebuddy-sessions.vscdb"
    if db.is_file():
        sql_paths(
            inv,
            "codebuddy",
            db,
            """SELECT json_extract(value,'$.cwd'),json_extract(value,'$.updatedAt')
                  FROM ItemTable WHERE key LIKE 'session:%'""",
            "session.cwd",
            "inferred",
            "session.updatedAt",
        )
    history_projects(inv, "codebuddy")
    projects_dir = inv.home / ".codebuddy/projects"
    for folder in children(inv, "codebuddy", projects_dir):
        if not folder.is_dir():
            continue
        for path in children(inv, "codebuddy", folder):
            if path.suffix == ".jsonl":
                codebuddy_session(inv, path)


def codebuddy_session(inv, path):
    with inv.source("codebuddy", path):
        found = False
        for label, line in session_edges(path):
            with inv.source("codebuddy", path):
                event = json.loads(line)
                if event.get("cwd"):
                    source = f"{path}#{label}"
                    row = inv.add(
                        "codebuddy", "inferred", [event["cwd"]], source + ".cwd"
                    )
                    update_activity(
                        row,
                        activity_time(event.get("timestamp")),
                        source + ".timestamp",
                    )
                    found = True
        if not found:
            inv.note("codebuddy", path, "在大小限制内的首尾事件中没有可读取的 cwd")


def session_edges(path, limit=65536):
    # Read one header and a bounded suffix; do not walk a conversation.
    with path.open("rb") as stream:
        first = stream.readline(limit + 1)
        if first and len(first) <= limit:
            yield "first", first
        size = stream.seek(0, os.SEEK_END)
        if size <= len(first):
            return
        start = max(len(first), size - limit)
        stream.seek(start - 1)
        boundary = stream.read(1) == b"\n"
        lines = stream.read(limit).splitlines()
        if not boundary:
            lines = lines[1:]
        for line in reversed(lines):
            if line.strip():
                yield "last", line
                break
