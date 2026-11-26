"""Lightweight workspace launcher for editors, desktop agents, terminal, Finder, and Git remotes."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from mappo.providers.registry import read_mac_bundle_id

EDITOR_LAUNCHERS = (
    {
        "id": "cursor",
        "label": "Cursor",
        "kind": "editor",
        "apps": (("Cursor", "Cursor", None),),
        "clis": ("cursor",),
        "opens_path": True,
    },
    {
        "id": "codebuddy",
        "label": "CodeBuddy CN",
        "kind": "editor",
        "apps": (("CodeBuddy CN", "CodeBuddy CN", None),),
        "clis": ("codebuddy",),
        "opens_path": True,
    },
    {
        "id": "vscode",
        "label": "VS Code",
        "kind": "editor",
        "apps": (("Visual Studio Code", "VS Code", None),),
        "clis": ("code",),
        "opens_path": True,
    },
    {
        "id": "trae",
        "label": "Trae",
        "kind": "editor",
        "apps": (("Trae", "Trae", None), ("Trae CN", "Trae CN", None)),
        "clis": ("trae", "trae-cn"),
        "opens_path": True,
    },
)

DESKTOP_AGENT_LAUNCHERS = (
    {
        "id": "codex",
        "label": "Codex",
        "kind": "coding_agent",
        "apps": (
            ("Codex", "Codex", None),
            ("ChatGPT", "Codex", "com.openai.codex"),
        ),
        "clis": (),
        "opens_path": True,
    },
    {
        "id": "workbuddy",
        "label": "WorkBuddy",
        "kind": "coding_agent",
        "apps": (("WorkBuddy", "WorkBuddy", None),),
        "clis": (),
        "opens_path": True,
    },
    {
        "id": "claude",
        "label": "Claude",
        "kind": "coding_agent",
        "apps": (("Claude", "Claude", None),),
        "clis": (),
        "opens_path": True,
    },
    {
        "id": "antigravity",
        "label": "Antigravity",
        "kind": "coding_agent",
        "apps": (
            ("Antigravity IDE", "Antigravity IDE", None, True),
            ("Antigravity", "Antigravity", None, False),
        ),
        "clis": ("antigravity-ide",),
        "opens_path": True,
    },
    {
        "id": "dsh",
        "label": "DeepSeek Harness",
        "kind": "coding_agent",
        "apps": (("DeepSeek Harness", "DeepSeek Harness", None),),
        "clis": (),
        "opens_path": False,
    },
)

APP_LAUNCHERS = EDITOR_LAUNCHERS + DESKTOP_AGENT_LAUNCHERS
EDITOR_BY_ID = {item["id"]: item for item in EDITOR_LAUNCHERS}
APP_BY_ID = {item["id"]: item for item in APP_LAUNCHERS}

MAC_TERMINALS = (
    ("Ghostty", "Ghostty"),
    ("Warp", "Warp"),
    ("iTerm", "iTerm"),
    ("WezTerm", "WezTerm"),
    ("Alacritty", "Alacritty"),
    ("Terminal", "终端"),
)

VALID_TARGETS = frozenset({"finder", "terminal", "remote", *APP_BY_ID})
_SCP_REMOTE_RE = re.compile(r"^(?:[^@\s]+@)?([A-Za-z0-9._-]+):(.+)$")


def _find_mac_app(app_name, home=None, *, bundle_id=None):
    base_home = Path(home) if home is not None else Path.home()
    candidates = (
        Path("/Applications") / f"{app_name}.app",
        Path("/System/Applications/Utilities") / f"{app_name}.app",
        Path("/System/Applications") / f"{app_name}.app",
        base_home / "Applications" / f"{app_name}.app",
    )
    for cand in candidates:
        try:
            if not cand.exists():
                continue
            if bundle_id and read_mac_bundle_id(cand) != bundle_id:
                continue
            return str(cand)
        except OSError:
            continue
    return None


def _resolve_cli(names, *, which=None, home=None):
    which_fn = which or shutil.which
    for name in names:
        found = which_fn(name)
        if found:
            return found
    if which is not None:
        return None
    base_home = Path(home) if home is not None else Path.home()
    extra_dirs = (
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        base_home / ".local" / "bin",
        base_home / ".codebuddy" / "bin",
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


def _resolve_mac_app_spec(spec, *, home=None):
    default_opens_path = bool(spec.get("opens_path", True))
    for entry in spec.get("apps", ()):
        app_name, label, required_bundle_id = entry[:3]
        opens_path = bool(entry[3]) if len(entry) > 3 else default_opens_path
        app_path = _find_mac_app(app_name, home=home, bundle_id=required_bundle_id)
        if app_path:
            return app_path, label, opens_path
    return None, spec["label"], default_opens_path


def _detect_mac_terminal(home=None):
    for app_name, label in MAC_TERMINALS:
        app_path = _find_mac_app(app_name, home=home)
        if app_path:
            return app_path, label
    return None, None


def remote_web_url(raw_url):
    """Convert a Git remote URL into a safe http(s) browser URL when possible."""
    url = (raw_url or "").strip()
    if not url:
        return None
    if url.lower().startswith(("http://", "https://")):
        parsed = urlsplit(url)
        if not parsed.hostname:
            return None
        path = parsed.path.rstrip("/")
        if path.lower().endswith(".git"):
            path = path[:-4]
        netloc = parsed.hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return f"{parsed.scheme.lower()}://{netloc}{path}"
    if url.lower().startswith("ssh://"):
        parsed = urlsplit(url)
        if not parsed.hostname:
            return None
        path = parsed.path.rstrip("/")
        if path.lower().endswith(".git"):
            path = path[:-4]
        return f"https://{parsed.hostname}{path}"
    if "://" in url:
        return None
    match = _SCP_REMOTE_RE.match(url)
    if match:
        host, repo_path = match.group(1), match.group(2).strip().lstrip("/").rstrip("/")
        if repo_path.lower().endswith(".git"):
            repo_path = repo_path[:-4]
        if host and "." in host and repo_path:
            return f"https://{host}/{repo_path}"
    return None


def detect_launchers(*, home=None, platform=None, which=None):
    """Return local launcher availability metadata for Web UI and CLI."""
    plat = platform or sys.platform
    which_fn = which or shutil.which
    items = []
    for spec in APP_LAUNCHERS:
        app_path, label, app_opens_path = (
            _resolve_mac_app_spec(spec, home=home)
            if plat == "darwin"
            else (None, spec["label"], bool(spec.get("opens_path", True)))
        )
        cli_names = spec.get("clis") or ()
        cli_path = (
            _resolve_cli(cli_names, which=which, home=home) if cli_names else None
        )
        opens_path = app_opens_path if app_path else bool(spec.get("opens_path", True))
        items.append(
            {
                "id": spec["id"],
                "label": label,
                "kind": spec["kind"],
                "opens_path": opens_path,
                "available": bool(app_path or cli_path),
            }
        )
    if plat == "darwin":
        term_app, term_label = _detect_mac_terminal(home=home)
        items.append(
            {
                "id": "terminal",
                "label": term_label or "终端",
                "kind": "terminal",
                "opens_path": True,
                "available": bool(term_app),
            }
        )
        items.append(
            {
                "id": "finder",
                "label": "访达",
                "kind": "finder",
                "opens_path": True,
                "available": True,
            }
        )
    elif plat.startswith("linux"):
        term_bin = next(
            (
                which_fn(name)
                for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm")
                if which_fn(name)
            ),
            None,
        )
        items.append(
            {
                "id": "terminal",
                "label": "终端",
                "kind": "terminal",
                "opens_path": True,
                "available": bool(term_bin),
            }
        )
        items.append(
            {
                "id": "finder",
                "label": "文件管理器",
                "kind": "finder",
                "opens_path": True,
                "available": bool(which_fn("xdg-open")),
            }
        )
    else:
        items.append(
            {
                "id": "terminal",
                "label": "终端",
                "kind": "terminal",
                "opens_path": True,
                "available": False,
            }
        )
        items.append(
            {
                "id": "finder",
                "label": "访达",
                "kind": "finder",
                "opens_path": True,
                "available": False,
            }
        )
    return items


def workspace_activity_for_root(ws, root=None):
    """Return the most specific last_activity timestamp for a workspace on a project root."""
    if not isinstance(ws, dict):
        return ""
    if root and isinstance(ws.get("activity_by_root"), dict):
        entry = ws["activity_by_root"].get(root)
        if isinstance(entry, dict) and entry.get("last_activity"):
            return entry["last_activity"]
    return ws.get("last_activity") or ""


def project_agent_activity(project, workspaces=()):
    """Compute {agent_id: latest_iso_timestamp} for a project across its workspaces."""
    ws_ids = set(project.get("workspaces") or ())
    root = project.get("path")
    activity = {}
    for ws in workspaces or ():
        if ws_ids and ws.get("id") not in ws_ids:
            continue
        agent = ws.get("agent")
        if not agent:
            continue
        stamp = workspace_activity_for_root(ws, root)
        if stamp and stamp > activity.get(agent, ""):
            activity[agent] = stamp
    return activity


def pick_preferred_launcher(project, workspaces=(), launchers=None):
    """Pick the most recently active available editor or desktop agent for a project."""
    resolved = launchers if launchers is not None else detect_launchers()
    available_apps = {
        item["id"]
        for item in resolved
        if item.get("kind") in ("editor", "coding_agent")
        and item.get("available")
        and item.get("opens_path", True)
    }
    if not available_apps:
        return None
    activity = project_agent_activity(project, workspaces)
    best_app = None
    best_stamp = ""
    for agent, stamp in activity.items():
        if agent not in available_apps:
            continue
        if best_app is None or stamp > best_stamp:
            best_app = agent
            best_stamp = stamp
    if best_app:
        return best_app
    for agent in project.get("agents") or ():
        if agent in available_apps:
            return agent
    return None


pick_preferred_editor = pick_preferred_launcher


def build_launch_command(
    path,
    target="finder",
    *,
    remote_url=None,
    home=None,
    platform=None,
    which=None,
):
    """Build the subprocess argv and display label for a launch target."""
    plat = platform or sys.platform
    which_fn = which or shutil.which
    if target not in VALID_TARGETS:
        raise ValueError(f"unsupported_target|不支持的打开方式：{target}")

    if target == "remote":
        web_url = remote_web_url(remote_url)
        if not web_url:
            raise ValueError("no_remote|该项目没有可打开的 Git 远程仓库地址")
        if plat == "darwin":
            return ["open", web_url], "Git 仓库", web_url
        if plat.startswith("linux"):
            return ["xdg-open", web_url], "Git 仓库", web_url
        raise OSError("当前操作系统暂不支持自动打开远程地址")

    if target == "finder":
        if plat == "darwin":
            return ["open", path], "访达", path
        if plat.startswith("linux"):
            return ["xdg-open", path], "文件管理器", path
        raise OSError("当前操作系统暂不支持自动打开本地目录")

    if target == "terminal":
        if plat == "darwin":
            term_app, term_label = _detect_mac_terminal(home=home)
            if not term_app:
                raise ValueError("unavailable_launcher|未检测到可用的终端应用")
            return ["open", "-a", term_app, path], term_label or "终端", path
        if plat.startswith("linux"):
            for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                found = which_fn(name)
                if found:
                    if name == "gnome-terminal":
                        return [found, f"--working-directory={path}"], "终端", path
                    return [found], "终端", path
            raise ValueError("unavailable_launcher|未检测到可用的终端应用")
        raise OSError("当前操作系统暂不支持自动打开终端")

    spec = APP_BY_ID[target]
    if plat == "darwin":
        app_path, label, opens_path = _resolve_mac_app_spec(spec, home=home)
        if app_path:
            if opens_path:
                return ["open", "-a", app_path, path], label, path
            return ["open", "-a", app_path], label, app_path
    cli_names = spec.get("clis") or ()
    cli_path = _resolve_cli(cli_names, which=which, home=home) if cli_names else None
    if cli_path:
        return [cli_path, path], spec["label"], path
    raise ValueError(f"unavailable_launcher|未检测到已安装的 {spec['label']}")


def launch_target(
    path,
    target="finder",
    *,
    remote_url=None,
    home=None,
    platform=None,
    which=None,
    runner=None,
):
    """Execute the launch command for the given target and return launch metadata."""
    cmd, label, opened_value = build_launch_command(
        path,
        target,
        remote_url=remote_url,
        home=home,
        platform=platform,
        which=which,
    )
    spec = APP_BY_ID.get(target)
    opens_path = True if spec is None else (opened_value == path)
    run_fn = runner or (
        lambda argv: subprocess.run(
            argv,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=path if target == "terminal" and os.path.isdir(path) else None,
        )
    )
    run_fn(cmd)
    return {
        "target": target,
        "label": label,
        "opened": opened_value,
        "opens_path": opens_path,
    }
