"""Additional read-only providers (OpenClaw, OpenCode, Gemini CLI, Continue)."""

from mappo.core.io import read_json, sql_paths


def other(inv, agent):
    h = inv.home
    if agent == "openclaw":
        db = h / ".openclaw/state/openclaw.sqlite"
        sql_paths(
            inv,
            agent,
            db,
            "SELECT workspace_path FROM workspace_setup_state",
            "workspace_setup_state",
            "native",
        )
        sql_paths(
            inv,
            agent,
            db,
            "SELECT DISTINCT cwd FROM acp_sessions",
            "acp_sessions.cwd",
            "inferred",
        )
    elif agent == "opencode":
        db = h / ".local/share/opencode/opencode.db"
        sql_paths(
            inv,
            agent,
            db,
            "SELECT worktree FROM project WHERE id != 'global'",
            "project.worktree",
            "native",
        )
    elif agent == "gemini":
        path = h / ".gemini/projects.json"
        with inv.source(agent, path):
            for root in read_json(path)["projects"]:
                inv.add(agent, "native", [root], path)
    elif agent == "continue":
        path = h / ".continue/sessions/sessions.json"
        with inv.source(agent, path):
            for session in read_json(path):
                if session.get("workspaceDirectory"):
                    inv.add(agent, "inferred", [session["workspaceDirectory"]], path)
