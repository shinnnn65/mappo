"""Project asset classification, Git inspection, noise filtering, and remote URI parsing."""

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

_TIMESTAMP_DIR_RE = re.compile(
    r"^(?:\d{14}|\d{4}-\d{2}-\d{2}(?:[-_]\d{2}-\d{2}-\d{2})?)$"
)
_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_GENERIC_HOME_DIRS = frozenset(
    {
        (),
        ("Downloads",),
        ("Desktop",),
        ("Documents",),
        ("Library",),
        ("Applications",),
    }
)

_TEMP_PREFIXES = (
    "/tmp",
    "/private/tmp",
    "/var/tmp",
    "/private/var/tmp",
    "/var/folders",
    "/private/var/folders",
    "/Library/Caches",
    "/System/Volumes/Data/private/tmp",
    "/System/Volumes/Data/private/var/folders",
)

_REMOTE_TEMP_EXACT = frozenset({"/", "/tmp", "/var/tmp"})
_REMOTE_TEMP_PREFIXES = ("/tmp/", "/var/tmp/")
_WORKTREE_SEGMENTS = frozenset({".worktrees", "worktrees"})
_SANDBOX_AGENT_DIRS = frozenset({"CodeBuddy", "WorkBuddy"})
_HARNESS_KEYWORDS = ("harness", "codex", "buddy", "agent")
_HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_REMOTE_SECTION_RE = re.compile(r'^\[remote\s+"([^"]+)"\]$', re.IGNORECASE)
_SECTION_HEADER_RE = re.compile(r"^\[.*\]$")


def _starts_with_dir(path_str, prefix):
    return path_str == prefix or path_str.startswith(prefix + "/")


def parse_remote_uri(uri):
    """Parse a remote workspace URI (such as vscode-remote://) into structured fields."""
    parsed = urlsplit(uri)
    scheme = parsed.scheme or "remote"
    authority = unquote(parsed.netloc or "")
    remote_path = unquote(parsed.path or "")
    if remote_path != "/" and remote_path.endswith("/"):
        remote_path = remote_path.rstrip("/")
    protocol = scheme
    raw_host = authority
    if "+" in authority:
        protocol, raw_host = authority.split("+", 1)
    host = raw_host
    if "@" in host:
        host = host.split("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    group_key = remote_path or uri
    name = Path(remote_path).name if remote_path and remote_path != "/" else (host or uri)
    return {
        "protocol": protocol,
        "authority": authority,
        "host": host or raw_host or scheme,
        "remote_path": remote_path or uri,
        "group_key": group_key,
        "name": name,
    }


def _sanitize_remote_url(raw_url):
    """Strip embedded userinfo credentials from HTTP(S) Git remote URLs."""
    url = (raw_url or "").strip()
    if not url:
        return None
    lower = url.lower()
    if lower.startswith(("http://", "https://")):
        try:
            parts = urlsplit(url)
            if "@" in parts.netloc:
                hostport = parts.netloc.rsplit("@", 1)[1]
                return urlunsplit(
                    (parts.scheme, hostport, parts.path, parts.query, parts.fragment)
                )
        except ValueError:
            return url
    return url


def _resolve_git_entry(dir_path):
    """Inspect <dir_path>/.git and return (kind, git_dir, common_dir, parent_repo) or None."""
    dot_git = dir_path / ".git"
    try:
        if dot_git.is_dir():
            return "repo", dot_git, dot_git, None
        if not dot_git.is_file():
            return None
        first_line = ""
        with dot_git.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    first_line = stripped
                    break
    except OSError:
        return None

    if not first_line.lower().startswith("gitdir:"):
        return None
    raw_target = first_line[len("gitdir:") :].strip()
    if not raw_target:
        return None
    git_dir = Path(raw_target)
    if not git_dir.is_absolute():
        git_dir = dir_path / git_dir
    try:
        git_dir = git_dir.resolve() if git_dir.exists() else Path(os.path.normpath(str(git_dir)))
    except OSError:
        git_dir = Path(os.path.normpath(str(git_dir)))

    commondir_file = git_dir / "commondir"
    try:
        has_commondir = commondir_file.is_file()
    except OSError:
        has_commondir = False
    is_worktree_dir = has_commondir or (
        git_dir.parent.name == "worktrees" and git_dir.parent.parent.name == ".git"
    )
    if is_worktree_dir:
        common_dir = git_dir.parent.parent if git_dir.parent.name == "worktrees" else git_dir
        if has_commondir:
            try:
                raw_common = commondir_file.read_text(encoding="utf-8", errors="ignore").strip()
                if raw_common:
                    cand = Path(raw_common)
                    if not cand.is_absolute():
                        cand = git_dir / cand
                    common_dir = cand.resolve() if cand.exists() else Path(os.path.normpath(str(cand)))
            except OSError:
                pass
        parent_repo = str(common_dir.parent) if common_dir.name == ".git" else str(common_dir)
        return "worktree", git_dir, common_dir, parent_repo

    if "modules" in git_dir.parts:
        parent_repo = None
        for anc in git_dir.parents:
            if anc.name == ".git":
                parent_repo = str(anc.parent)
                break
        return "submodule", git_dir, git_dir, parent_repo

    return "repo", git_dir, git_dir, None


def _read_git_head(git_dir):
    """Read branch name and detached state from <git_dir>/HEAD."""
    head_file = git_dir / "HEAD"
    try:
        line = head_file.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except (OSError, IndexError):
        return None, False
    if line.startswith("ref:"):
        ref = line[4:].strip()
        if ref.startswith("refs/heads/"):
            return ref[len("refs/heads/") :], False
        return ref or None, False
    if _HEX_SHA_RE.match(line):
        return line[:7], True
    return None, False


def _read_git_remote(common_dir):
    """Parse <common_dir>/config for the primary remote (preferring origin)."""
    cfg_file = common_dir / "config"
    try:
        lines = cfg_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None, None
    remotes = {}
    order = []
    current_remote = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if _SECTION_HEADER_RE.match(line):
            match = _REMOTE_SECTION_RE.match(line)
            current_remote = match.group(1) if match else None
            if current_remote and current_remote not in remotes:
                order.append(current_remote)
            continue
        if current_remote and "=" in line:
            key, _, val = line.partition("=")
            if key.strip().lower() == "url" and current_remote not in remotes:
                cleaned = _sanitize_remote_url(val)
                if cleaned:
                    remotes[current_remote] = cleaned
    if "origin" in remotes:
        return "origin", remotes["origin"]
    for name in order:
        if name in remotes:
            return name, remotes[name]
    return None, None


def detect_git_info(path_str, *, status=None, home=None):
    """Inspect local directory Git metadata without invoking git subprocesses."""
    if not path_str or (status is not None and status != "directory"):
        return None
    target = Path(path_str)
    try:
        if not target.is_dir():
            return None
    except OSError:
        return None

    resolved = _resolve_git_entry(target)
    if resolved is not None:
        kind, git_dir, common_dir, parent_repo = resolved
    else:
        home_resolved = Path(home or Path.home()).resolve()
        kind = git_dir = common_dir = parent_repo = None
        cur = target.parent
        while cur != cur.parent:
            if cur == home_resolved:
                break
            parent_entry = _resolve_git_entry(cur)
            if parent_entry is not None:
                _, git_dir, common_dir, _ = parent_entry
                kind = "subdir"
                parent_repo = str(cur)
                break
            cur = cur.parent
        if kind is None:
            return {"is_git": False, "kind": "none"}

    branch, detached = _read_git_head(git_dir)
    remote_name, remote_url = _read_git_remote(common_dir)
    return {
        "is_git": True,
        "kind": kind,
        "branch": branch,
        "detached": detached,
        "remote_name": remote_name,
        "remote_url": remote_url,
        "parent_repo": parent_repo,
    }


def _classify_details(project, home=None, *, git_info=None):
    """Classify a project and lazily inspect Git metadata only for non-noise directories."""
    path_str = project.get("path") or ""
    status = project.get("status") or ""
    promoted = bool(project.get("promoted", False))

    if status == "remote":
        remote_info = parse_remote_uri(path_str)
        rpath = remote_info["remote_path"]
        if rpath in _REMOTE_TEMP_EXACT or rpath.startswith(_REMOTE_TEMP_PREFIXES):
            return "noise", "remote_temp", remote_info, None
        return "remote", "remote_workspace", remote_info, None

    home_path = Path(home or Path.home()).resolve()
    path_obj = Path(path_str)
    try:
        rel_parts = path_obj.relative_to(home_path).parts
        in_home = True
    except ValueError:
        rel_parts = ()
        in_home = False

    # System root and generic top-level user directories
    if path_str == "/" or (in_home and rel_parts in _GENERIC_HOME_DIRS):
        return "noise", "system_dir", None, None

    # OS temporary and cache directories outside the user's home directory
    if not in_home and any(_starts_with_dir(path_str, prefix) for prefix in _TEMP_PREFIXES):
        return "noise", "temp_cache", None, None

    # Trash and cache directories inside the user's home directory
    if in_home and rel_parts:
        if rel_parts[0] in (".Trash", ".cache"):
            return "noise", "temp_cache", None, None
        if len(rel_parts) >= 2 and rel_parts[0] == "Library":
            if rel_parts[1] in ("Caches", "Application Support"):
                return "noise", "temp_cache", None, None
            if rel_parts[1] == "Containers" and "Caches" in rel_parts:
                return "noise", "temp_cache", None, None

    # Determine whether the directory is an ephemeral git worktree or Agent sandbox
    path_parts = rel_parts if in_home else path_obj.parts
    is_worktree = any(seg in _WORKTREE_SEGMENTS for seg in path_parts)
    resolved_git = None
    if status == "directory":
        resolved_git = (
            git_info
            if git_info is not None
            else detect_git_info(path_str, status=status, home=home)
        )
        if resolved_git and resolved_git.get("kind") == "worktree":
            is_worktree = True

    is_sandbox = False
    if in_home and rel_parts:
        if (
            len(rel_parts) >= 2
            and rel_parts[0] == "Documents"
            and rel_parts[1] == "Codex"
            and (len(rel_parts) == 2 or bool(_DATE_DIR_RE.match(rel_parts[2])))
        ):
            is_sandbox = True
        elif (
            len(rel_parts) == 2
            and rel_parts[0] in _SANDBOX_AGENT_DIRS
            and bool(_TIMESTAMP_DIR_RE.match(rel_parts[1]))
        ):
            is_sandbox = True
        elif rel_parts[-1] == "default-workspace" and any(
            kw in "/".join(rel_parts).lower() for kw in _HARNESS_KEYWORDS
        ):
            is_sandbox = True

    if status == "missing":
        if is_worktree:
            return "noise", "deleted_worktree", None, None
        if is_sandbox:
            return "noise", "deleted_sandbox", None, None
        if in_home and rel_parts and rel_parts[0] == "Downloads":
            return "noise", "deleted_download", None, None
        return "project", "missing_project", None, None

    if status in ("inaccessible", "not-directory"):
        if is_worktree or is_sandbox:
            return "noise", "invalid_ephemeral", None, None
        return "project", "needs_attention", None, None

    if promoted:
        reason = "promoted_sandbox" if (is_sandbox or is_worktree) else "local_project"
        return "project", reason, None, resolved_git

    if is_worktree:
        return "sandbox", "active_worktree", None, resolved_git
    if is_sandbox:
        return "sandbox", "agent_sandbox", None, resolved_git

    return "project", "local_project", None, resolved_git


def classify_project(project, home=None, *, git_info=None):
    """Classify a discovered project into project, sandbox, remote, or noise.

    Returns a tuple of (asset_kind, asset_reason, remote_info).
    """
    asset_kind, asset_reason, remote_info, _ = _classify_details(
        project, home=home, git_info=git_info
    )
    return asset_kind, asset_reason, remote_info


def annotate_project(project, home=None):
    """Attach asset_kind, asset_reason, remote metadata, and Git info to a project dict."""
    asset_kind, asset_reason, remote_info, git_info = _classify_details(
        project, home=home
    )
    project["asset_kind"] = asset_kind
    project["asset_reason"] = asset_reason
    if remote_info is not None:
        project["remote"] = remote_info
    else:
        project.pop("remote", None)
    if git_info is not None:
        project["git"] = git_info
    else:
        project.pop("git", None)
    return project
