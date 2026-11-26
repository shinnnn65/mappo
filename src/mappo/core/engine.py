"""Top-level read-only workspace scan orchestrator and project aggregator."""

import os
import shutil
from pathlib import Path

from mappo.core.classify import annotate_project
from mappo.core.models import Inventory, path_state, stable_id, update_activity
from mappo.providers import (
    CLI_ALIASES,
    EDITOR_EXTENSION_DIRS,
    EDITORS,
    EXTENSIONS,
    EXTRA_DATA_LOCATIONS,
    MAC_APP_VARIANTS,
    SUPPORT,
    agy,
    claude,
    codebuddy_history,
    codex,
    detect_extension_hosts,
    dsh,
    editor,
    filesystem,
    merged_registry,
    other,
    read_mac_bundle_id,
    tool_category,
    workbuddy,
)

_DIRECT_PROVIDERS = {
    "codex": codex,
    "dsh": dsh,
    "workbuddy": workbuddy,
    "claude": claude,
    "antigravity": agy,
}


def _find_cli_binary(agent, home):
    names = CLI_ALIASES.get(agent, (agent,))
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    extra_dirs = (
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        home / ".local" / "bin",
        home / ".codebuddy" / "bin",
    )
    for name in names:
        for directory in extra_dirs:
            cand = directory / name
            try:
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
            except OSError:
                continue
    return None


def _find_installed_apps(agent, default_app, home):
    variants = MAC_APP_VARIANTS.get(agent, ((default_app, None),))
    installed = []
    for app_name, required_bundle_id in variants:
        appname = app_name + ".app"
        for cand in (Path("/Applications") / appname, home / "Applications" / appname):
            try:
                if not cand.is_dir():
                    continue
                if required_bundle_id and read_mac_bundle_id(cand) != required_bundle_id:
                    continue
                path_str = str(cand)
                if path_str not in installed:
                    installed.append(path_str)
            except OSError:
                continue
    return installed


def sort_project_agents(agents, agent_activity=None, *, extensions=None):
    """Order a project's agents with primary tools before extensions and most recently active first."""
    activity = agent_activity or {}
    ext_map = EXTENSIONS if extensions is None else extensions
    # Sort by recency descending first (stable on original order for ties),
    # then place primary tools before editor extensions.
    by_recency = sorted(
        agents,
        key=lambda a: (bool(activity.get(a)), activity.get(a) or ""),
        reverse=True,
    )
    return sorted(
        by_recency,
        key=lambda a: (1 if a in ext_map else 0, 0 if activity.get(a) else 1),
    )


def scan(home=None, selected=None, paths=()):
    home = Path(home or Path.home()).resolve()
    products, extensions, limits = merged_registry(home=home)
    inv = Inventory(home)
    agents = []
    for agent, (app, location) in products.items():
        if selected and agent != selected:
            continue
        installed = _find_installed_apps(agent, app, home)
        binary = _find_cli_binary(agent, home)
        if binary and binary not in installed:
            installed.append(binary)
        if agent in extensions:
            for prefix in EDITOR_EXTENSION_DIRS.values():
                installed.extend(
                    str(p)
                    for p in sorted(
                        (home / prefix / "extensions").glob(extensions[agent] + "-*")
                    )
                )
        locations = [home / location] if location else []
        locations.extend(home / rel for rel in EXTRA_DATA_LOCATIONS.get(agent, ()))
        if agent in extensions:
            locations.extend(
                home / SUPPORT / product / "User/globalStorage" / extensions[agent]
                for product in EDITORS.values()
            )
        if agent in EDITORS:
            locations.append(home / SUPPORT / EDITORS[agent])
        before = len(inv.diagnostics)
        data = []
        for location_path in locations:
            with inv.source(agent, location_path):
                if location_path.exists():
                    data.append(str(location_path))
        if not (data or installed or selected or len(inv.diagnostics) > before):
            continue
        with inv.source(agent, location):
            if agent in limits:
                inv.note(agent, home / location, limits[agent], "unsupported")
            elif agent in EDITORS:
                editor(inv, agent, EDITORS[agent])
                if agent == "codebuddy":
                    codebuddy_history(inv)
            elif agent in extensions:
                for product in EDITORS.values():
                    editor(inv, agent, product, extensions[agent])
                if agent == "continue":
                    other(inv, agent)
            elif agent in _DIRECT_PROVIDERS:
                _DIRECT_PROVIDERS[agent](inv)
            else:
                other(inv, agent)
        agent_records = [v for v in inv.records.values() if v["agent"] == agent]
        count = len(agent_records)
        status = "ok" if count else "empty"
        issues = sorted({d["code"] for d in inv.diagnostics[before:]})
        if issues:
            status = (
                "partial"
                if count
                else next(
                    (
                        c
                        for c in (
                            "permission_denied",
                            "busy",
                            "invalid_source",
                            "read_error",
                            "unsupported",
                            "missing_source",
                        )
                        if c in issues
                    ),
                    issues[0],
                )
            )
        if not count and status == "empty":
            inv.note(
                agent,
                data[0] if data else app,
                "本机索引没有可归属此工具的发现记录",
                "empty",
            )
        entry = dict(
            agent=agent,
            display_name=app,
            category=tool_category(agent, extensions=extensions),
            installed=installed,
            data=data,
            records=count,
            issues=issues,
            status=status,
        )
        if agent in extensions:
            entry["host_editors"] = detect_extension_hosts(
                installed=installed,
                data=data,
                workspaces=agent_records,
            )
        agents.append(entry)
    for path in paths:
        filesystem(inv, Path(path).expanduser().absolute())
    # ChatGPT project mirrors are managed application storage. Keep the native
    # workspace and its IDs, but do not infer a local code asset from the mirror.
    managed = {
        root for row in inv.records.values() for root in row.get("managed_roots", [])
    }
    projects = {}
    project_agent_times = {}
    for row in inv.records.values():
        for root in row["roots"]:
            if row["agent"] == "codex" and root in managed:
                continue
            p = projects.setdefault(
                root,
                dict(
                    id=stable_id("p", root),
                    path=root,
                    status=path_state(root),
                    names=[],
                    last_activity=None,
                    activity_source=None,
                    agents=[],
                    workspaces=[],
                ),
            )
            if row["agent"] != "filesystem" and row["agent"] not in p["agents"]:
                p["agents"].append(row["agent"])
            for name in (Path(root).name, row["name"]):
                if name and name not in p["names"]:
                    p["names"].append(name)
            activity = (
                row.get("activity_by_root", {}).get(root, {})
                if "activity_by_root" in row
                else row
            )
            stamp = activity.get("last_activity")
            update_activity(p, stamp, activity.get("activity_source"))
            if row["agent"] != "filesystem" and stamp:
                per_agent = project_agent_times.setdefault(root, {})
                if stamp > per_agent.get(row["agent"], ""):
                    per_agent[row["agent"]] = stamp
            p["workspaces"].append(row["id"])
    for root, proj in projects.items():
        proj["agents"] = sort_project_agents(
            proj["agents"], project_agent_times.get(root), extensions=extensions
        )
    annotated = [annotate_project(projects[p], home=home) for p in sorted(projects)]
    return dict(
        agents=agents,
        projects=annotated,
        workspaces=sorted(inv.records.values(), key=lambda r: r["id"]),
        diagnostics=inv.diagnostics,
    )
