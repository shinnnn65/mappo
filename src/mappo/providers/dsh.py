"""DeepSeek Harness (DSH) workspace provider."""

from mappo.core.io import children, read_json
from mappo.core.models import activity_time, update_activity


def dsh(inv):
    path = inv.home / ".dsh/storages/workspace.json"
    with inv.source("dsh", path):
        for key, item in read_json(path)["tables"]["workspaces"].items():
            with inv.source("dsh", path):
                row = inv.add(
                    "dsh", "native", [item["path"]], path, key, item.get("title")
                )
                update_activity(
                    row,
                    activity_time(item.get("updatedAt")),
                    str(path) + "#workspaces.updatedAt",
                )
    for path in children(inv, "dsh", path.parent / "session_projcache/sessions"):
        if path.suffix != ".json":
            continue
        with inv.source("dsh", path):
            identity = read_json(path)["record"]["identity"]
            row = inv.add("dsh", "inferred", [identity["cwd"]], path)
            update_activity(
                row,
                activity_time(identity.get("createdAt")),
                str(path) + "#identity.createdAt",
            )
