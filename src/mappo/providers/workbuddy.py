"""WorkBuddy workspace provider."""

from mappo.core.io import dated_paths, read_json
from mappo.core.models import activity_time, update_activity


def workbuddy(inv):
    db = inv.home / ".workbuddy/workbuddy.db"
    dated_paths(inv, "workbuddy", db, "workspaces", "path", "last_opened_at", "native")
    dated_paths(
        inv,
        "workbuddy",
        db,
        "sessions",
        "cwd",
        "last_activity_at",
        "inferred",
        "WHERE deleted_at IS NULL",
    )
    path = inv.home / ".workbuddy/app/sessions.json"
    if path.exists():
        with inv.source("workbuddy", path):
            for item in read_json(path)["sessions"]:
                with inv.source("workbuddy", path):
                    row = inv.add(
                        "workbuddy",
                        "inferred",
                        [item["workDir"]],
                        str(path) + "#sessions.workDir",
                    )
                    for field in ("resumedAt", "startedAt"):
                        update_activity(
                            row, activity_time(item.get(field)), str(path) + "#" + field
                        )
