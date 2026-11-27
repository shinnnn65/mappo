"""Local HTTP server for Mappo Web UI."""

import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from mappo import APP_VERSION
from mappo.core.classify import annotate_project, detect_git_info
from mappo.core.engine import scan, sort_project_agents
from mappo.core.models import path_state
from mappo.host.assets import load_asset
from mappo.sessions import (
    build_handoff,
    list_sessions,
    render_handoff_markdown,
)
from mappo.host.hygiene import (
    _dir_size_bytes,
    build_duplicate_groups,
    inspect_git_safety,
    move_to_trash,
    scan_hygiene as run_hygiene_scan,
    scan_project_artifacts,
    validate_artifact_target,
    validate_project_trash_target,
)
from mappo.host.launcher import (
    VALID_TARGETS,
    detect_launchers,
    launch_target,
    project_agent_activity,
    remote_web_url,
)
from mappo.storage.local_index import LocalIndex, scope_key

DEFAULT_PORT = 4318
MAX_BODY_BYTES = 64 * 1024
STATIC_FILES = {
    "/assets/app.css": ("app.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
SUBASSET_PREFIXES = {
    "/assets/js/": ("js", "application/javascript; charset=utf-8", "js"),
    "/assets/css/": ("css", "text/css; charset=utf-8", "css"),
}
SUBASSET_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.(js|css)$")
ICON_ROUTE_PREFIX = "/assets/icons/"
ICON_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.(png|svg|webp)$")
ICON_MIME_TYPES = {
    "png": "image/png",
    "svg": "image/svg+xml; charset=utf-8",
    "webp": "image/webp",
}
OPEN_ERROR_MESSAGES = {
    "missing": "目录已不存在，无法打开",
    "remote": "远程路径不在本机文件系统，无法直接打开",
    "inaccessible": "当前账号没有该目录的访问权限，无法打开",
    "not-directory": "该路径指向文件而非文件夹，无法作为目录打开",
}


def _collect_tags(projects):
    counts = {}
    for project in projects:
        hidden = bool(project.get("hidden", False))
        for tag in project.get("tags", []):
            entry = counts.setdefault(tag, [0, 0])
            entry[1] += 1
            if not hidden:
                entry[0] += 1
    rows = [
        {"tag": tag, "count": visible, "total": total}
        for tag, (visible, total) in counts.items()
    ]
    rows.sort(key=lambda item: (-item["count"], -item["total"], item["tag"].casefold()))
    return rows


class WebApp:
    """Shared application state and API actions backed by LocalIndex and scanner."""

    def __init__(
        self,
        *,
        index=None,
        selected_agent=None,
        paths=None,
        scan_fn=None,
        opener=None,
        trasher=None,
        home_dir=None,
    ):
        self.index = index or LocalIndex()
        self.selected_agent = selected_agent
        self.paths = list(paths or [])
        self.scope = scope_key(self.selected_agent, self.paths)
        self.home_dir = str(home_dir or Path.home())
        self.scan_fn = scan_fn or (
            lambda: scan(selected=self.selected_agent, paths=self.paths)
        )
        self.opener = opener
        self.trasher = trasher
        self.token = secrets.token_urlsafe(24)
        self._scan_lock = threading.Lock()
        self._inflight = None
        self._hygiene_lock = threading.Lock()
        self._hygiene_inflight = None
        self._hygiene_cache = None
        self._hygiene_progress = None

    def format_state(self, result, *, duration_ms=None):
        raw_agents = result.get("agents", [])
        unsupported_agents = {
            a["agent"] for a in raw_agents if a.get("status") == "unsupported"
        }
        visible_agents = [a for a in raw_agents if a.get("status") != "unsupported"]
        visible_diagnostics = [
            d
            for d in result.get("diagnostics", [])
            if d.get("agent") not in unsupported_agents
        ]
        raw_workspaces = result.get("workspaces", [])
        ws_by_id = {w["id"]: w for w in raw_workspaces if w.get("id")}
        visible_projects = []
        filtered_noise_count = 0
        for project in result.get("projects", []):
            row = dict(project)
            annotate_project(row, home=self.home_dir)
            if row.get("asset_kind") == "noise":
                filtered_noise_count += 1
                continue
            proj_workspaces = [
                ws_by_id[wid] for wid in row.get("workspaces", []) if wid in ws_by_id
            ]
            if not proj_workspaces and row.get("historical_evidence"):
                proj_workspaces = row["historical_evidence"]
            row["agents"] = sort_project_agents(
                row.get("agents", []),
                project_agent_activity(row, proj_workspaces),
            )
            git_meta = row.get("git")
            if isinstance(git_meta, dict) and git_meta.get("remote_url"):
                web_url = remote_web_url(git_meta["remote_url"])
                if web_url:
                    git_meta["web_url"] = web_url
            visible_projects.append(row)
        referenced_ws_ids = {
            wid
            for project in visible_projects
            for wid in project.get("workspaces", [])
        }
        visible_workspaces = [
            w
            for w in result.get("workspaces", [])
            if w.get("id") in referenced_ws_ids
        ]
        duplicate_groups = build_duplicate_groups(
            visible_projects,
            by_project=(self._hygiene_cache or {}).get("by_project"),
        )
        payload = {
            "version": APP_VERSION,
            "home_dir": self.home_dir,
            "scope": {"agent": self.selected_agent, "paths": self.paths},
            "indexed_at": result.get("indexed_at"),
            "agents": visible_agents,
            "projects": visible_projects,
            "workspaces": visible_workspaces,
            "diagnostics": visible_diagnostics,
            "all_tags": _collect_tags(visible_projects),
            "filtered_noise_count": filtered_noise_count,
            "launchers": detect_launchers(home=self.home_dir),
            "duplicate_groups": duplicate_groups,
            "hygiene": self.get_hygiene_state(visible_projects),
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return payload

    def get_state(self):
        try:
            return self.format_state(self.index.load(self.scope))
        except ValueError:
            return self.rescan()

    def rescan(self):
        with self._scan_lock:
            if self._inflight is not None:
                event, box = self._inflight
                leader = False
            else:
                event = threading.Event()
                box = {}
                self._inflight = (event, box)
                leader = True
        if not leader:
            event.wait()
            if "error" in box:
                raise box["error"]
            return self.format_state(box["result"], duration_ms=box["duration_ms"])
        started = time.monotonic()
        try:
            snapshot = self.index.save(self.scope, self.scan_fn())
            box["result"] = snapshot
            box["duration_ms"] = int((time.monotonic() - started) * 1000)
        except Exception as error:
            box["error"] = error
            raise
        finally:
            with self._scan_lock:
                self._inflight = None
                event.set()
        return self.format_state(box["result"], duration_ms=box["duration_ms"])

    def update_meta(self, project_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        allowed = {"favorite", "hidden", "promoted", "tags", "add_tags", "remove_tags"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"包含不支持的字段：{', '.join(sorted(unknown))}")
        favorite = payload.get("favorite")
        if favorite is not None and not isinstance(favorite, bool):
            raise ValueError("favorite 必须是布尔值")
        hidden = payload.get("hidden")
        if hidden is not None and not isinstance(hidden, bool):
            raise ValueError("hidden 必须是布尔值")
        promoted = payload.get("promoted")
        if promoted is not None and not isinstance(promoted, bool):
            raise ValueError("promoted 必须是布尔值")
        updated = self.index.update_meta(
            self.scope,
            project_id,
            favorite=favorite,
            hidden=hidden,
            promoted=promoted,
            tags=payload.get("tags"),
            add_tags=payload.get("add_tags"),
            remove_tags=payload.get("remove_tags"),
        )
        snapshot = self.index.load(self.scope)
        formatted = self.format_state(snapshot)
        updated_project = next(
            (row for row in formatted["projects"] if row["id"] == project_id),
            None,
        )
        if updated_project is not None:
            updated["asset_kind"] = updated_project.get("asset_kind")
            updated["asset_reason"] = updated_project.get("asset_reason")
        updated["all_tags"] = formatted["all_tags"]
        return updated

    def open_project(self, project_id, target="finder"):
        if not isinstance(target, str):
            raise ValueError("unsupported_target|打开方式参数无效")
        target = target.strip().lower() or "finder"
        if target not in VALID_TARGETS:
            raise ValueError(f"unsupported_target|不支持的打开方式：{target}")
        snapshot = self.index.load(self.scope)
        project = next(
            (row for row in snapshot.get("projects", []) if row["id"] == project_id),
            None,
        )
        if project is None:
            raise LookupError("未找到该项目记录")
        path = project["path"]
        state = path_state(path)
        remote_url = None
        if target == "remote":
            git_meta = detect_git_info(path, status=state, home=self.home_dir)
            remote_url = git_meta.get("remote_url") if isinstance(git_meta, dict) else None
            web_url = remote_web_url(remote_url)
            if not web_url:
                raise ValueError("no_remote|该项目没有可打开的 Git 远程仓库地址")
            if self.opener is not None:
                try:
                    self.opener(web_url, target)
                except TypeError:
                    self.opener(web_url)
                return {
                    "ok": True,
                    "project_id": project_id,
                    "path": path,
                    "target": target,
                    "label": "Git 仓库",
                    "opened": web_url,
                }
            launched = launch_target(
                path, target, remote_url=remote_url, home=self.home_dir
            )
            return {"ok": True, "project_id": project_id, "path": path, **launched}

        if state != "directory" or not os.path.isabs(path):
            raise ValueError(
                f"{state}|{OPEN_ERROR_MESSAGES.get(state, '该路径当前无法打开')}"
            )
        if self.opener is not None:
            try:
                self.opener(path, target)
            except TypeError:
                self.opener(path)
            return {
                "ok": True,
                "project_id": project_id,
                "path": path,
                "target": target,
                "label": target,
                "opened": path,
            }
        launched = launch_target(path, target, home=self.home_dir)
        return {"ok": True, "project_id": project_id, "path": path, **launched}

    def get_project_sessions(self, project_id, *, agent=None, limit=30):
        snapshot = self.index.load(self.scope)
        project = next(
            (row for row in snapshot.get("projects", []) if row["id"] == project_id),
            None,
        )
        if project is None:
            raise LookupError("未找到该项目记录")
        path = project.get("path")
        rows = (
            list_sessions(
                home=self.home_dir,
                agent=agent or None,
                project_paths=[path],
                limit=limit,
            )
            if path
            else []
        )
        return {
            "project_id": project_id,
            "path": path,
            "sessions": rows,
        }

    def get_sessions(self, *, agent=None, project_query=None, limit=30):
        rows = list_sessions(
            home=self.home_dir,
            agent=agent or None,
            project_query=project_query or None,
            limit=limit,
        )
        return {"sessions": rows}

    def get_session_handoff(self, ref, *, agent=None, turns=6, max_chars=1600):
        payload, candidates = build_handoff(
            ref,
            home=self.home_dir,
            agent=agent or None,
            turns=turns,
            max_chars=max_chars,
            include_git=True,
        )
        if payload is None:
            if candidates:
                raise ValueError("ambiguous|匹配到多个会话，请提供完整 ID 或工具前缀")
            raise LookupError("未找到匹配的本地会话")
        markdown = render_handoff_markdown(payload)
        return {
            "handoff": payload,
            "markdown": markdown,
            "short_prompt": f"请通过 mappo 读取会话 {payload['ref']} 的上下文并接着往下做",
        }

    def change_link(self, first, second, *, remove=False):
        if not isinstance(first, str) or not isinstance(second, str):
            raise ValueError("请提供两个有效的项目 ID")
        self.index.change_link(self.scope, first, second, remove=remove)
        snapshot = self.index.load(self.scope)
        by_id = {row["id"]: row for row in snapshot.get("projects", [])}
        return {
            "projects": [first, second],
            "linked": not remove,
            "related": {
                key: by_id[key].get("related_projects", [])
                for key in (first, second)
                if key in by_id
            },
        }

    def _visible_projects_for_hygiene(self):
        snapshot = self.index.load(self.scope)
        visible = []
        for project in snapshot.get("projects", []):
            row = dict(project)
            annotate_project(row, home=self.home_dir)
            if row.get("asset_kind") == "noise":
                continue
            git_meta = row.get("git")
            if isinstance(git_meta, dict) and git_meta.get("remote_url"):
                web_url = remote_web_url(git_meta["remote_url"])
                if web_url:
                    git_meta["web_url"] = web_url
            visible.append(row)
        return visible

    def get_hygiene_state(self, visible_projects=None):
        projects = (
            visible_projects
            if visible_projects is not None
            else self._visible_projects_for_hygiene()
        )
        with self._hygiene_lock:
            cached = self._hygiene_cache
            scanning = self._hygiene_inflight is not None
            progress = dict(self._hygiene_progress) if self._hygiene_progress else None
            by_project = dict(cached.get("by_project", {})) if cached else {}
        duplicate_groups = build_duplicate_groups(projects, by_project=by_project)
        sandboxes = [
            p
            for p in projects
            if not p.get("hidden")
            and p.get("status") == "directory"
            and p.get("asset_kind") == "sandbox"
        ]
        if not cached:
            return {
                "scanned": False,
                "scanning": scanning,
                "progress": progress,
                "scanned_at": None,
                "duration_ms": None,
                "by_project": {},
                "duplicate_groups": duplicate_groups,
                "summary": {
                    "total_reclaimable_bytes": 0,
                    "reclaimable_project_count": 0,
                    "duplicate_group_count": len(duplicate_groups),
                    "duplicate_project_count": sum(g["count"] for g in duplicate_groups),
                    "sandbox_count": len(sandboxes),
                    "dormant_sandbox_count": 0,
                    "scanned_project_count": 0,
                },
            }
        active_ids = {
            p["id"]
            for p in projects
            if not p.get("hidden") and p.get("status") == "directory"
        }
        filtered_by_project = {
            pid: info for pid, info in by_project.items() if pid in active_ids
        }
        summary = dict(cached.get("summary", {}))
        summary["total_reclaimable_bytes"] = sum(
            info.get("reclaimable_bytes", 0) for info in filtered_by_project.values()
        )
        summary["reclaimable_project_count"] = sum(
            1
            for info in filtered_by_project.values()
            if info.get("reclaimable_bytes", 0) > 0
        )
        summary["duplicate_group_count"] = len(duplicate_groups)
        summary["duplicate_project_count"] = sum(g["count"] for g in duplicate_groups)
        summary["sandbox_count"] = len(sandboxes)
        return {
            "scanned": bool(cached.get("scanned", True)),
            "scanning": scanning,
            "progress": progress,
            "scanned_at": cached.get("scanned_at"),
            "duration_ms": cached.get("duration_ms"),
            "by_project": filtered_by_project,
            "duplicate_groups": duplicate_groups,
            "summary": summary,
        }

    def scan_hygiene(self, *, background=False):
        with self._hygiene_lock:
            if self._hygiene_inflight is not None:
                event, box = self._hygiene_inflight
                leader = False
            else:
                event = threading.Event()
                box = {}
                self._hygiene_inflight = (event, box)
                self._hygiene_progress = {"done": 0, "total": 0}
                leader = True
        if not leader:
            if background:
                return self.get_hygiene_state()
            event.wait()
            if "error" in box:
                raise box["error"]
            return box["result"]

        projects = self._visible_projects_for_hygiene()
        target_count = sum(
            1
            for p in projects
            if not p.get("hidden") and p.get("status") == "directory"
        )
        with self._hygiene_lock:
            self._hygiene_progress = {"done": 0, "total": target_count}
            if self._hygiene_cache is None:
                self._hygiene_cache = {
                    "scanned": False,
                    "scanned_at": None,
                    "duration_ms": None,
                    "by_project": {},
                    "summary": {},
                }

        def _on_progress(pid, info, done, total):
            with self._hygiene_lock:
                if self._hygiene_cache is not None:
                    self._hygiene_cache["by_project"][pid] = info
                self._hygiene_progress = {"done": done, "total": total}

        def _worker():
            try:
                result = run_hygiene_scan(
                    projects, home_dir=self.home_dir, on_progress=_on_progress
                )
                with self._hygiene_lock:
                    self._hygiene_cache = result
                    self._hygiene_progress = None
                box["result"] = result
            except Exception as error:
                with self._hygiene_lock:
                    self._hygiene_progress = None
                box["error"] = error
            finally:
                with self._hygiene_lock:
                    self._hygiene_inflight = None
                    event.set()

        if background:
            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            return self.get_hygiene_state(projects)

        _worker()
        if "error" in box:
            raise box["error"]
        return box["result"]

    def git_safety_check(self, project_id):
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("invalid_project|缺少有效的项目 ID")
        projects = self._visible_projects_for_hygiene()
        project = next((row for row in projects if row["id"] == project_id), None)
        if project is None:
            raise LookupError("未找到该项目记录")
        safety = inspect_git_safety(project["path"])
        artifacts = scan_project_artifacts(project["path"], home_dir=self.home_dir)
        return {
            "project_id": project_id,
            **safety,
            "reclaimable_bytes": artifacts["reclaimable_bytes"],
            "artifacts": artifacts["artifacts"],
        }

    def trash_hygiene(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("invalid_body|请求体必须是 JSON 对象")
        mode = payload.get("mode")
        if mode not in ("artifacts", "project"):
            raise ValueError("invalid_mode|不支持的清理模式")
        projects = self._visible_projects_for_hygiene()
        by_id = {row["id"]: row for row in projects}
        do_trash = self.trasher or move_to_trash

        if mode == "artifacts":
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                raise ValueError("empty_items|请选择至少一个待清理的依赖目录")
            trashed = []
            failed = []
            freed_bytes = 0
            affected_pids = set()
            for entry in items:
                if not isinstance(entry, dict):
                    raise ValueError("invalid_items|清理清单格式无效")
                pid = entry.get("project_id")
                paths = entry.get("paths")
                if pid not in by_id or not isinstance(paths, list) or not paths:
                    raise ValueError("invalid_items|清理清单包含无效的项目或路径")
                project_path = by_id[pid]["path"]
                for raw_path in paths:
                    resolved = validate_artifact_target(
                        project_path, raw_path, home_dir=self.home_dir
                    )
                    size = _dir_size_bytes(resolved)
                    try:
                        do_trash(str(resolved))
                        trashed.append(
                            {
                                "project_id": pid,
                                "path": str(resolved),
                                "name": resolved.name,
                                "bytes": size,
                            }
                        )
                        freed_bytes += size
                        affected_pids.add(pid)
                    except (OSError, subprocess.SubprocessError) as error:
                        failed.append({"path": str(resolved), "error": str(error)})
            if self._hygiene_cache and affected_pids:
                for pid in affected_pids:
                    self._hygiene_cache["by_project"][pid] = scan_project_artifacts(
                        by_id[pid]["path"], home_dir=self.home_dir
                    )
            return {
                "ok": len(failed) == 0,
                "mode": "artifacts",
                "freed_bytes": freed_bytes,
                "trashed": trashed,
                "failed": failed,
                "hygiene": self.get_hygiene_state(projects),
            }

        project_id = payload.get("project_id")
        if not isinstance(project_id, str) or project_id not in by_id:
            raise LookupError("未找到该项目记录")
        project = by_id[project_id]
        resolved = validate_project_trash_target(
            project["path"], home_dir=self.home_dir
        )
        do_trash(str(resolved))
        if self._hygiene_cache:
            self._hygiene_cache["by_project"].pop(project_id, None)
        project["status"] = path_state(project["path"])
        return {
            "ok": True,
            "mode": "project",
            "project_id": project_id,
            "path": str(resolved),
            "status": project["status"],
            "trashed": [str(resolved)],
            "hygiene": self.get_hygiene_state(projects),
        }


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _make_handler(app, bound_port, quiet=True):
    allowed_hosts = {f"127.0.0.1:{bound_port}", f"localhost:{bound_port}"}
    allowed_origins = {f"http://127.0.0.1:{bound_port}", f"http://localhost:{bound_port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            if not quiet:
                super().log_message(fmt, *args)

        def _send_bytes(self, status, body, content_type, cache="no-store"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _send_error_json(self, status, message, *, code=None):
            payload = {"error": message}
            if code:
                payload["code"] = code
            self._send_json(status, payload)

        def _check_host(self):
            host = (self.headers.get("Host") or "").strip().lower()
            if host not in allowed_hosts:
                self._send_error_json(HTTPStatus.FORBIDDEN, "仅允许本机地址访问")
                return False
            return True

        def _check_mutation_guard(self):
            if not self._check_host():
                return False
            origin = (self.headers.get("Origin") or "").strip().lower()
            if origin and origin not in allowed_origins:
                self._send_error_json(HTTPStatus.FORBIDDEN, "拒绝来自外部来源的请求")
                return False
            token = self.headers.get("X-Mappo-Token") or ""
            if not hmac.compare_digest(token, app.token):
                self._send_error_json(
                    HTTPStatus.FORBIDDEN, "会话令牌无效，请刷新页面后重试"
                )
                return False
            return True

        def _read_json_body(self):
            raw_len = self.headers.get("Content-Length")
            if not raw_len:
                return {}
            try:
                length = int(raw_len)
            except ValueError:
                raise ValueError("无效的请求长度") from None
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("请求体过大")
            if length == 0:
                return {}
            data = self.rfile.read(length)
            try:
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError("请求体不是合法 JSON") from None

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._check_host():
                return
            route = urlsplit(self.path).path
            if route in ("/", "/index.html"):
                try:
                    raw_html = load_asset("index.html").decode("utf-8")
                except OSError as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, str(error)
                    )
                    return
                token_meta = (
                    f'<meta name="mappo-token" content="{html.escape(app.token, quote=True)}">'
                )
                rendered = raw_html.replace("<!--MAPPO_TOKEN-->", token_meta, 1)
                self._send_bytes(
                    HTTPStatus.OK,
                    rendered.encode("utf-8"),
                    "text/html; charset=utf-8",
                )
                return
            if route in STATIC_FILES:
                filename, mime = STATIC_FILES[route]
                try:
                    data = load_asset(filename)
                except OSError as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, str(error)
                    )
                    return
                self._send_bytes(HTTPStatus.OK, data, mime, cache="no-cache")
                return
            for prefix, (subdir, mime, expected_ext) in SUBASSET_PREFIXES.items():
                if route.startswith(prefix):
                    asset_name = route[len(prefix) :]
                    match = SUBASSET_FILENAME_RE.match(asset_name)
                    if not match or match.group(1) != expected_ext:
                        self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该静态资源")
                        return
                    try:
                        data = load_asset(f"{subdir}/{asset_name}")
                    except FileNotFoundError:
                        self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该静态资源")
                        return
                    self._send_bytes(HTTPStatus.OK, data, mime, cache="no-cache")
                    return
            if route.startswith(ICON_ROUTE_PREFIX):
                icon_name = route[len(ICON_ROUTE_PREFIX) :]
                match = ICON_FILENAME_RE.match(icon_name)
                if not match:
                    self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该图标")
                    return
                mime = ICON_MIME_TYPES[match.group(1)]
                try:
                    data = load_asset(f"icons/{icon_name}")
                except FileNotFoundError:
                    self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该图标")
                    return
                self._send_bytes(HTTPStatus.OK, data, mime, cache="no-cache")
                return
            if route == "/api/state":
                try:
                    self._send_json(HTTPStatus.OK, app.get_state())
                except (OSError, sqlite3.Error, ValueError) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"加载索引失败：{error}"
                    )
                return
            if route == "/api/hygiene":
                try:
                    self._send_json(HTTPStatus.OK, app.get_hygiene_state())
                except (OSError, sqlite3.Error, ValueError) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"加载空间体检失败：{error}"
                    )
                return
            if route.startswith("/api/projects/") and route.endswith("/sessions"):
                project_id = unquote(
                    route[len("/api/projects/") : -len("/sessions")]
                )
                qs = parse_qs(urlsplit(self.path).query)
                agent_param = (qs.get("agent") or [None])[0]
                raw_limit = (qs.get("limit") or ["30"])[0]
                try:
                    limit = max(1, min(100, int(raw_limit)))
                except ValueError:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "limit 参数必须是整数")
                    return
                try:
                    self._send_json(
                        HTTPStatus.OK,
                        app.get_project_sessions(
                            project_id, agent=agent_param, limit=limit
                        ),
                    )
                except LookupError as error:
                    self._send_error_json(HTTPStatus.NOT_FOUND, str(error))
                except ValueError as error:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"加载项目会话失败：{error}"
                    )
                return
            if route == "/api/sessions":
                qs = parse_qs(urlsplit(self.path).query)
                agent_param = (qs.get("agent") or [None])[0]
                project_param = (qs.get("project") or [None])[0]
                raw_limit = (qs.get("limit") or ["30"])[0]
                try:
                    limit = max(1, min(100, int(raw_limit)))
                except ValueError:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "limit 参数必须是整数")
                    return
                try:
                    self._send_json(
                        HTTPStatus.OK,
                        app.get_sessions(
                            agent=agent_param,
                            project_query=project_param,
                            limit=limit,
                        ),
                    )
                except ValueError as error:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"加载会话列表失败：{error}"
                    )
                return
            if route == "/api/sessions/handoff":
                qs = parse_qs(urlsplit(self.path).query)
                ref_param = (qs.get("ref") or [""])[0]
                agent_param = (qs.get("agent") or [None])[0]
                raw_turns = (qs.get("turns") or ["6"])[0]
                raw_max = (qs.get("max_chars") or ["1600"])[0]
                try:
                    turns = max(0, min(50, int(raw_turns)))
                    max_chars = max(200, min(12000, int(raw_max)))
                except ValueError:
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, "turns 和 max_chars 必须是整数"
                    )
                    return
                try:
                    self._send_json(
                        HTTPStatus.OK,
                        app.get_session_handoff(
                            ref_param,
                            agent=agent_param,
                            turns=turns,
                            max_chars=max_chars,
                        ),
                    )
                except LookupError as error:
                    self._send_error_json(HTTPStatus.NOT_FOUND, str(error))
                except ValueError as error:
                    code, _, message = str(error).partition("|")
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, message or code, code=code or None
                    )
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"生成会话交接包失败：{error}"
                    )
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该路径")

        def do_POST(self):
            if not self._check_mutation_guard():
                return
            route = urlsplit(self.path).path
            if route == "/api/scan":
                try:
                    self._send_json(HTTPStatus.OK, app.rescan())
                except (OSError, sqlite3.Error, ValueError) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"扫描失败：{error}"
                    )
                return
            if route == "/api/hygiene/scan":
                try:
                    body = self._read_json_body()
                    background = bool(isinstance(body, dict) and body.get("background"))
                    self._send_json(
                        HTTPStatus.OK, app.scan_hygiene(background=background)
                    )
                except (OSError, sqlite3.Error, ValueError) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"空间体检失败：{error}"
                    )
                return
            if route == "/api/hygiene/git-check":
                try:
                    body = self._read_json_body()
                    if not isinstance(body, dict):
                        raise ValueError("invalid_body|请求体必须是 JSON 对象")
                    self._send_json(
                        HTTPStatus.OK, app.git_safety_check(body.get("project_id"))
                    )
                except LookupError as error:
                    self._send_error_json(HTTPStatus.NOT_FOUND, str(error))
                except ValueError as error:
                    code, _, message = str(error).partition("|")
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, message or code, code=code or None
                    )
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"Git 安全检查失败：{error}"
                    )
                return
            if route == "/api/hygiene/trash":
                try:
                    body = self._read_json_body()
                    self._send_json(HTTPStatus.OK, app.trash_hygiene(body))
                except LookupError as error:
                    self._send_error_json(HTTPStatus.NOT_FOUND, str(error))
                except ValueError as error:
                    code, _, message = str(error).partition("|")
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, message or code, code=code or None
                    )
                except (OSError, subprocess.SubprocessError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"移入废纸篓失败：{error}"
                    )
                return
            if route.startswith("/api/projects/") and route.endswith("/open"):
                project_id = unquote(route[len("/api/projects/") : -len("/open")])
                try:
                    body = self._read_json_body()
                    if not isinstance(body, dict):
                        raise ValueError("请求体必须是 JSON 对象")
                    target = body.get("target") or "finder"
                    self._send_json(
                        HTTPStatus.OK, app.open_project(project_id, target=target)
                    )
                except LookupError as error:
                    self._send_error_json(HTTPStatus.NOT_FOUND, str(error))
                except ValueError as error:
                    code, _, message = str(error).partition("|")
                    self._send_error_json(
                        HTTPStatus.BAD_REQUEST, message or code, code=code or None
                    )
                except (OSError, subprocess.SubprocessError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"无法打开项目：{error}"
                    )
                return
            if route == "/api/links":
                try:
                    body = self._read_json_body()
                    if not isinstance(body, dict):
                        raise ValueError("请求体必须是 JSON 对象")
                    self._send_json(
                        HTTPStatus.OK,
                        app.change_link(
                            body.get("first"), body.get("second"), remove=False
                        ),
                    )
                except ValueError as error:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"保存关联失败：{error}"
                    )
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该接口")

        def do_PATCH(self):
            if not self._check_mutation_guard():
                return
            route = urlsplit(self.path).path
            if route.startswith("/api/projects/") and route.endswith("/meta"):
                project_id = unquote(route[len("/api/projects/") : -len("/meta")])
                try:
                    body = self._read_json_body()
                    self._send_json(
                        HTTPStatus.OK, app.update_meta(project_id, body)
                    )
                except ValueError as error:
                    status = (
                        HTTPStatus.NOT_FOUND
                        if "未找到该项目" in str(error)
                        else HTTPStatus.BAD_REQUEST
                    )
                    self._send_error_json(status, str(error))
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"更新项目状态失败：{error}"
                    )
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该接口")

        def do_DELETE(self):
            if not self._check_mutation_guard():
                return
            route = urlsplit(self.path).path
            if route == "/api/links":
                try:
                    body = self._read_json_body()
                    if not isinstance(body, dict):
                        raise ValueError("请求体必须是 JSON 对象")
                    self._send_json(
                        HTTPStatus.OK,
                        app.change_link(
                            body.get("first"), body.get("second"), remove=True
                        ),
                    )
                except ValueError as error:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                except (OSError, sqlite3.Error) as error:
                    self._send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR, f"解除关联失败：{error}"
                    )
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "未找到该接口")

    return Handler


def create_server(app, *, port=None, quiet=True):
    """Bind a local-only HTTP server on 127.0.0.1 and return (server, url)."""
    if port is None:
        try:
            server = _ReusableThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), BaseHTTPRequestHandler)
        except OSError:
            server = _ReusableThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    else:
        server = _ReusableThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    bound_port = server.server_address[1]
    server.RequestHandlerClass = _make_handler(app, bound_port, quiet=quiet)
    return server, f"http://127.0.0.1:{bound_port}"


def serve_web(
    *,
    index=None,
    selected_agent=None,
    paths=None,
    port=None,
    open_browser=True,
):
    app = WebApp(index=index, selected_agent=selected_agent, paths=paths)
    server, url = create_server(app, port=port, quiet=True)
    scope_parts = []
    if selected_agent:
        scope_parts.append(f"Agent={selected_agent}")
    if paths:
        scope_parts.append(f"补扫目录={len(paths)} 个")
    scope_note = f"（范围：{', '.join(scope_parts)}）" if scope_parts else ""
    print(f"Mappo 已启动：{url}{scope_note}", flush=True)
    print("仅限本机访问，按 Ctrl+C 停止服务。", flush=True)
    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止服务。", flush=True)
    finally:
        server.server_close()
