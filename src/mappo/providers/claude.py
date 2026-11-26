"""Claude Code workspace provider."""

from mappo.core.io import history_projects, read_json


def claude(inv):
    path = inv.home / ".claude.json"
    with inv.source("claude", path):
        for root in read_json(path)["projects"]:
            with inv.source("claude", path):
                inv.add("claude", "native", [root], str(path) + "#projects")
    history_projects(inv, "claude")
