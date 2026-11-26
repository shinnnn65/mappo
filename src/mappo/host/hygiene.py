"""On-demand workspace hygiene scanner, duplicate detector, Git safety check, and safe Trash mover."""

import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from mappo.host.launcher import remote_web_url

UNCONDITIONAL_ARTIFACTS = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        ".next",
        ".nuxt",
        ".turbo",
        ".parcel-cache",
        ".vite",
        ".svelte-kit",
        ".angular",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".gradle",
        "Pods",
    }
)

CONTEXTUAL_ARTIFACTS = {
    "dist": frozenset(
        {
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "vite.config.js",
            "vite.config.mjs",
            "webpack.config.js",
            "rollup.config.js",
            "pyproject.toml",
            "setup.py",
        }
    ),
    "build": frozenset(
        {
            "package.json",
            "pyproject.toml",
            "setup.py",
            "build.gradle",
            "build.gradle.kts",
            "CMakeLists.txt",
            "Makefile",
            "pubspec.yaml",
        }
    ),
    "target": frozenset(
        {
            "Cargo.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
        }
    ),
}

ALL_ARTIFACT_NAMES = UNCONDITIONAL_ARTIFACTS | frozenset(CONTEXTUAL_ARTIFACTS)
MONOREPO_CONTAINERS = frozenset(
    {"packages", "apps", "services", "modules", "workspaces", "plugins", "extensions"}
)
ENV_IGNORE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".schema")


def _is_forbidden_root(path, home_dir=None):
    try:
        resolved = Path(path).resolve()
    except OSError:
        return True
    home = Path(home_dir or Path.home()).resolve()
    if resolved == Path("/") or resolved == home:
        return True
    if resolved in home.parents:
        return True
    if str(resolved) in ("/Users", "/Applications", "/System", "/Library", "/tmp", "/var"):
        return True
    return False


def _dir_size_bytes(directory):
    total = 0
    stack = [str(directory)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _matches_artifact(entry_path, parent_names):
    name = entry_path.name
    if name in UNCONDITIONAL_ARTIFACTS:
        return True
    required = CONTEXTUAL_ARTIFACTS.get(name)
    if required and (parent_names & required):
        return True
    return False


def _collect_artifact_dirs(root_path):
    root = Path(root_path)
    found = []

    def _scan_level(directory, depth):
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError:
            return
        names = {e.name for e in entries}
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            name = entry.name
            if name == ".git":
                continue
            entry_path = Path(entry.path)
            if _matches_artifact(entry_path, names):
                found.append(entry_path)
                continue
            if depth == 0 and name in MONOREPO_CONTAINERS:
                _scan_level(entry_path, 1)
            elif depth == 1:
                _scan_level(entry_path, 2)

    _scan_level(root, 0)
    return found


def _measure_dirs_bytes(dirs):
    """Measure disk usage in bytes for a list of directories using native `du -sk` when available."""
    if not dirs:
        return {}
    str_dirs = [str(d) for d in dirs]
    du_bin = shutil.which("du")
    if du_bin and (sys.platform == "darwin" or sys.platform.startswith("linux")):
        try:
            proc = subprocess.run(
                [du_bin, "-sk", *str_dirs],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            sizes = {}
            for line in proc.stdout.splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2 and parts[0].strip().isdigit():
                    sizes[parts[1]] = int(parts[0].strip()) * 1024
            if sizes:
                for p in str_dirs:
                    if p not in sizes:
                        sizes[p] = _dir_size_bytes(p)
                return sizes
        except (OSError, subprocess.SubprocessError):
            pass
    return {p: _dir_size_bytes(p) for p in str_dirs}


def scan_project_artifacts(project_path, *, home_dir=None):
    """Scan a single local project directory for rebuildable artifact directories."""
    root = Path(project_path)
    if (
        not project_path
        or not os.path.isabs(project_path)
        or _is_forbidden_root(project_path, home_dir=home_dir)
    ):
        return {"reclaimable_bytes": 0, "artifacts": []}
    try:
        if root.is_symlink() or not root.is_dir():
            return {"reclaimable_bytes": 0, "artifacts": []}
    except OSError:
        return {"reclaimable_bytes": 0, "artifacts": []}

    artifact_dirs = _collect_artifact_dirs(root)
    if not artifact_dirs:
        return {"reclaimable_bytes": 0, "artifacts": []}
    sizes_map = _measure_dirs_bytes(artifact_dirs)
    artifacts = []
    total_bytes = 0
    for art_path in artifact_dirs:
        size = sizes_map.get(str(art_path), 0)
        if size <= 0:
            continue
        try:
            rel = str(art_path.relative_to(root))
        except ValueError:
            rel = art_path.name
        artifacts.append(
            {
                "path": str(art_path),
                "rel_path": rel,
                "name": art_path.name,
                "bytes": size,
            }
        )
        total_bytes += size
    artifacts.sort(key=lambda item: (-item["bytes"], item["rel_path"]))
    return {"reclaimable_bytes": total_bytes, "artifacts": artifacts}


def normalize_remote_key(raw_url):
    """Return a stable normalized key for grouping local clones of the same Git remote."""
    if not raw_url:
        return None
    web = remote_web_url(raw_url)
    if web:
        return web.lower().rstrip("/")
    cleaned = raw_url.strip().rstrip("/")
    if cleaned.lower().endswith(".git"):
        cleaned = cleaned[:-4]
    return cleaned.lower() or None


def build_duplicate_groups(projects, by_project=None):
    """Group non-hidden local directory projects/sandboxes that share the same Git remote."""
    buckets = {}
    for proj in projects or ():
        if proj.get("hidden") or proj.get("status") != "directory":
            continue
        git_meta = proj.get("git")
        if not isinstance(git_meta, dict) or not git_meta.get("is_git"):
            continue
        raw_url = git_meta.get("remote_url")
        key = normalize_remote_key(raw_url)
        if not key:
            continue
        entry = buckets.setdefault(
            key,
            {
                "remote_key": key,
                "remote_url": raw_url,
                "web_url": git_meta.get("web_url") or remote_web_url(raw_url),
                "items": [],
            },
        )
        entry["items"].append(proj)

    groups = []
    for entry in buckets.values():
        items = entry["items"]
        if len(items) < 2:
            continue
        items.sort(
            key=lambda p: (
                bool(p.get("last_activity")),
                p.get("last_activity") or "",
                p.get("path") or "",
            ),
            reverse=True,
        )
        repo_name = entry["remote_key"].rstrip("/").split("/")[-1] or Path(items[0]["path"]).name
        total_reclaimable = 0
        if by_project:
            total_reclaimable = sum(
                by_project.get(p["id"], {}).get("reclaimable_bytes", 0) for p in items
            )
        groups.append(
            {
                "remote_key": entry["remote_key"],
                "remote_url": entry["remote_url"],
                "web_url": entry["web_url"],
                "name": repo_name,
                "count": len(items),
                "project_ids": [p["id"] for p in items],
                "latest_activity": items[0].get("last_activity"),
                "reclaimable_bytes": total_reclaimable,
            }
        )

    groups.sort(
        key=lambda g: (
            -g["count"],
            -g["reclaimable_bytes"],
            g["name"].casefold(),
        )
    )
    return groups


def scan_hygiene(projects, *, home_dir=None, max_workers=8, on_progress=None):
    """Concurrently scan reclaimable artifact sizes across local projects and sandboxes."""
    started = time.monotonic()
    targets = [
        p
        for p in (projects or ())
        if not p.get("hidden") and p.get("status") == "directory"
    ]
    by_project = {}
    total_targets = len(targets)
    done_count = 0
    if targets:
        workers = max(1, min(max_workers, len(targets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    scan_project_artifacts, p["path"], home_dir=home_dir
                ): p["id"]
                for p in targets
            }
            for fut in as_completed(futures):
                pid = futures[fut]
                try:
                    info = fut.result()
                except OSError:
                    info = {"reclaimable_bytes": 0, "artifacts": []}
                by_project[pid] = info
                done_count += 1
                if on_progress is not None:
                    on_progress(pid, info, done_count, total_targets)

    duplicate_groups = build_duplicate_groups(projects, by_project=by_project)
    total_reclaimable = sum(
        info.get("reclaimable_bytes", 0) for info in by_project.values()
    )
    reclaimable_projects = sum(
        1 for info in by_project.values() if info.get("reclaimable_bytes", 0) > 0
    )
    now = datetime.now(timezone.utc)
    sandboxes = [
        p
        for p in targets
        if p.get("asset_kind") == "sandbox"
    ]
    dormant_sandboxes = 0
    for sb in sandboxes:
        ts = sb.get("last_activity")
        if not ts:
            dormant_sandboxes += 1
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if (now - dt).days >= 14:
                dormant_sandboxes += 1
        except ValueError:
            dormant_sandboxes += 1

    return {
        "scanned": True,
        "scanned_at": now.isoformat(),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "by_project": by_project,
        "duplicate_groups": duplicate_groups,
        "summary": {
            "total_reclaimable_bytes": total_reclaimable,
            "reclaimable_project_count": reclaimable_projects,
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_project_count": sum(g["count"] for g in duplicate_groups),
            "sandbox_count": len(sandboxes),
            "dormant_sandbox_count": dormant_sandboxes,
            "scanned_project_count": len(targets),
        },
    }


def _find_local_env_files(directory):
    found = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                if not name.startswith(".env"):
                    continue
                lower = name.lower()
                if any(lower.endswith(sfx) for sfx in ENV_IGNORE_SUFFIXES):
                    continue
                try:
                    if entry.is_file(follow_symlinks=False):
                        found.append(name)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(found)


def _run_git(directory, args, timeout=3.0):
    try:
        proc = subprocess.run(
            ["git", "-C", str(directory), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.SubprocessError):
        return -1, "", ""


def inspect_git_safety(project_path):
    """On-demand safety inspection before trashing an entire project or sandbox directory."""
    root = Path(project_path)
    if not project_path or not root.is_dir():
        raise ValueError("missing|目录已不存在")

    env_files = _find_local_env_files(root)
    git_marker = root / ".git"
    if not git_marker.exists():
        warnings = ["该目录不是 Git 仓库，删除后无法从远端恢复"]
        if env_files:
            warnings.append(f"包含本地配置文件：{', '.join(env_files[:4])}")
        return {
            "path": str(root),
            "is_git": False,
            "safe_to_trash": False,
            "level": "local_only",
            "dirty_count": 0,
            "untracked_count": 0,
            "unpushed_count": 0,
            "stash_count": 0,
            "has_remote": False,
            "env_files": env_files,
            "warnings": warnings,
        }

    warnings = []
    dirty_count = 0
    untracked_count = 0
    rc, out, _ = _run_git(root, ["status", "--porcelain=v1"])
    if rc == 0:
        for line in out.splitlines():
            if len(line) < 2:
                continue
            if line[:2] == "??":
                untracked_count += 1
            else:
                dirty_count += 1
    else:
        warnings.append("无法读取 Git 工作区状态，请删除前自行确认")

    rc_rem, out_rem, _ = _run_git(root, ["remote"])
    remotes = [line.strip() for line in out_rem.splitlines() if line.strip()] if rc_rem == 0 else []
    has_remote = bool(remotes)

    unpushed_count = 0
    if has_remote:
        rc_up, out_up, _ = _run_git(root, ["rev-list", "--count", "@{u}..HEAD"])
        if rc_up == 0 and out_up.strip().isdigit():
            unpushed_count = int(out_up.strip())
        else:
            # No upstream configured on current branch: check commits unreachable from any remote ref.
            rc_any, out_any, _ = _run_git(root, ["rev-list", "--count", "HEAD", "--not", "--remotes"])
            if rc_any == 0 and out_any.strip().isdigit():
                unpushed_count = int(out_any.strip())

    rc_st, out_st, _ = _run_git(root, ["stash", "list"])
    stash_count = len([line for line in out_st.splitlines() if line.strip()]) if rc_st == 0 else 0

    if not has_remote:
        warnings.append("未配置 Git 远程仓库，删除后无法从远端恢复")
    if dirty_count > 0:
        warnings.append(f"有 {dirty_count} 处未提交的本地修改")
    if untracked_count > 0:
        warnings.append(f"有 {untracked_count} 个未跟踪的新文件")
    if unpushed_count > 0:
        warnings.append(f"有 {unpushed_count} 个尚未推送到远端的提交")
    if stash_count > 0:
        warnings.append(f"有 {stash_count} 条未应用的 git stash 暂存")
    if env_files:
        warnings.append(f"包含被忽略的本地配置文件：{', '.join(env_files[:4])}")

    safe_to_trash = rc == 0 and not warnings
    return {
        "path": str(root),
        "is_git": True,
        "safe_to_trash": safe_to_trash,
        "level": "safe" if safe_to_trash else "caution",
        "dirty_count": dirty_count,
        "untracked_count": untracked_count,
        "unpushed_count": unpushed_count,
        "stash_count": stash_count,
        "has_remote": has_remote,
        "env_files": env_files,
        "warnings": warnings,
    }


def move_to_trash(path, *, platform=None, runner=None):
    """Move an existing file or directory to the OS Trash (never rm -rf)."""
    plat = platform or sys.platform
    target = str(path)
    run_fn = runner or (
        lambda argv: subprocess.run(
            argv,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    )
    if plat == "darwin":
        trash_bin = shutil.which("trash")
        if not trash_bin and Path("/usr/bin/trash").is_file():
            trash_bin = "/usr/bin/trash"
        if trash_bin:
            run_fn([trash_bin, target])
            return
        escaped = target.replace("\\", "\\\\").replace('"', '\\"')
        run_fn(
            [
                "osascript",
                "-e",
                f'tell application "Finder" to delete POSIX file "{escaped}"',
            ]
        )
        return
    if plat.startswith("linux"):
        gio = shutil.which("gio")
        if gio:
            run_fn([gio, "trash", target])
            return
    raise OSError("当前操作系统未找到安全的废纸篓命令")


def validate_artifact_target(project_path, artifact_path, *, home_dir=None):
    """Strictly validate that artifact_path is a real rebuildable artifact dir inside project_path."""
    if not project_path or not artifact_path:
        raise ValueError("invalid_path|清理路径无效")
    if _is_forbidden_root(project_path, home_dir=home_dir) or _is_forbidden_root(
        artifact_path, home_dir=home_dir
    ):
        raise ValueError("forbidden_path|拒绝操作受保护的系统或主目录")
    root = Path(project_path).resolve()
    art = Path(artifact_path)
    if art.is_symlink():
        raise ValueError("symlink_rejected|跳过符号链接目录")
    if not art.exists():
        raise ValueError("missing|目标目录已不存在")
    if not art.is_dir():
        raise ValueError("not_directory|目标不是目录")
    resolved = art.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("outside_project|清理路径必须位于项目目录内部") from error
    if not rel.parts:
        raise ValueError("outside_project|不能将项目根目录作为依赖产物清理")
    if resolved.name not in ALL_ARTIFACT_NAMES:
        raise ValueError(f"unsupported_artifact|不支持清理非依赖目录：{resolved.name}")
    parent = resolved.parent
    try:
        parent_names = {p.name for p in parent.iterdir()}
    except OSError as error:
        raise ValueError(f"read_error|无法读取父目录：{error}") from error
    if not _matches_artifact(resolved, parent_names):
        raise ValueError(f"unsupported_artifact|该目录缺少对应的构建清单，拒绝清理：{resolved.name}")
    return resolved


def validate_project_trash_target(project_path, *, home_dir=None):
    """Strictly validate that project_path is safe to move to Trash as a whole project."""
    if not project_path or not os.path.isabs(project_path):
        raise ValueError("invalid_path|项目路径无效")
    if _is_forbidden_root(project_path, home_dir=home_dir):
        raise ValueError("forbidden_path|拒绝删除受保护的系统或主目录")
    target = Path(project_path)
    if target.is_symlink():
        raise ValueError("symlink_rejected|拒绝直接删除符号链接")
    if not target.exists():
        raise ValueError("missing|目录已不存在")
    if not target.is_dir():
        raise ValueError("not_directory|目标不是文件夹")
    return target.resolve()
