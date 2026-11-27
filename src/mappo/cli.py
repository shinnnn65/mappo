#!/usr/bin/env python3
"""Mappo command line."""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from mappo import APP_VERSION  # noqa: E402
from mappo.core.classify import annotate_project, detect_git_info  # noqa: E402
from mappo.core.engine import scan  # noqa: E402
from mappo.core.models import path_state  # noqa: E402
from mappo.host.hygiene import scan_hygiene  # noqa: E402
from mappo.host.launcher import (  # noqa: E402
    VALID_TARGETS,
    build_launch_command,
    launch_target,
    pick_preferred_editor,
)
from mappo.host.web_server import OPEN_ERROR_MESSAGES, serve_web  # noqa: E402
from mappo.providers.registry import merged_registry  # noqa: E402
from mappo.query.search import filter_rows, since_time  # noqa: E402
from mappo.storage.local_index import LocalIndex, scope_key  # noqa: E402

META_COMMANDS = ("star", "unstar", "hide", "unhide", "tag", "untag")
OPEN_WITH_CHOICES = ("auto", *sorted(VALID_TARGETS))


def _resolve_project_for_open(projects, query):
    exact_id = [p for p in projects if p["id"] == query]
    if exact_id:
        return exact_id[0], None
    needle = query.casefold()
    visible = [p for p in projects if not p.get("hidden")]
    pool = visible or projects

    def _names(proj):
        items = [n for n in proj.get("names") or () if n]
        base = Path(proj["path"]).name if proj.get("path") else ""
        if base and base not in items:
            items.append(base)
        return items

    exact_name = [
        p for p in pool if any(n.casefold() == needle for n in _names(p))
    ]
    if len(exact_name) == 1:
        return exact_name[0], None
    if len(exact_name) > 1:
        dirs = [p for p in exact_name if p.get("status") == "directory"]
        if len(dirs) == 1:
            return dirs[0], None
        return None, exact_name

    fuzzy = [
        p
        for p in pool
        if needle in (p.get("path") or "").casefold()
        or any(needle in n.casefold() for n in _names(p))
    ]
    if len(fuzzy) == 1:
        return fuzzy[0], None
    if len(fuzzy) > 1:
        dirs = [p for p in fuzzy if p.get("status") == "directory"]
        if len(dirs) == 1:
            return dirs[0], None
        return None, fuzzy
    return None, []


def main():
    parser = argparse.ArgumentParser(description="盘点本机 Coding Agent 工作区")
    parser.add_argument(
        "command",
        choices=[
            "scan",
            "agents",
            "projects",
            "workspaces",
            "inspect",
            "open",
            "hygiene",
            "doctor",
            "link",
            "unlink",
            "web",
            *META_COMMANDS,
        ],
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="inspect/open/star/hide 使用项目 ID（open 也支持名称片段）；link 使用两个 ID；tag 使用项目 ID 与标签名",
    )
    parser.add_argument("--agent", choices=sorted(merged_registry()[0]))
    parser.add_argument(
        "--path", action="append", default=[], help="额外扫描的代码目录，可重复指定"
    )
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--version", action="version", version=f"mappo {APP_VERSION}")
    parser.add_argument(
        "--indexed", action="store_true", help="读取相同范围上一次保存的索引"
    )
    parser.add_argument("--index-file", help="指定 SQLite 索引位置")
    parser.add_argument("--no-index", action="store_true", help="扫描时跳过保存索引")
    parser.add_argument(
        "--status",
        choices=["directory", "missing", "remote", "not-directory", "inaccessible"],
    )
    parser.add_argument(
        "--historical", action="store_true", help="仅查看已从最新扫描消失的项目"
    )
    parser.add_argument("--name", help="按项目名或工作区名称搜索")
    parser.add_argument("--path-contains", help="按路径片段过滤，可与 --path 补扫组合")
    parser.add_argument(
        "--since", type=since_time, help="筛选指定日期或最近时段，如 2026-11-01、7d"
    )
    parser.add_argument(
        "--recent", action="store_true", help="列出有活动时间的结果，最近的排在前面"
    )
    parser.add_argument("--favorite", action="store_true", help="仅查看已收藏的项目")
    parser.add_argument(
        "--tag", action="append", default=[], help="按标签筛选项目，可重复指定"
    )
    parser.add_argument("--hidden", action="store_true", help="仅查看已隐藏的项目")
    parser.add_argument(
        "--include-hidden", action="store_true", help="在项目列表中包含已隐藏项"
    )
    parser.add_argument(
        "--port", type=int, help="web 本地服务端口（默认优先 4318，被占用自动分配）"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="启动 web 服务但不自动打开浏览器"
    )
    parser.add_argument(
        "--with",
        dest="open_with",
        choices=OPEN_WITH_CHOICES,
        help="open 打开方式（默认 auto：优先最近使用过的编辑器或桌面 Agent，回退访达）",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="open 时仅输出将执行的打开方式，不实际启动"
    )
    args = parser.parse_args()

    if any(
        (args.name, args.path_contains, args.since, args.recent)
    ) and args.command not in ("projects", "workspaces"):
        parser.error("列表过滤参数只适用于 projects 和 workspaces")
    if any(
        (args.favorite, args.tag, args.hidden, args.include_hidden)
    ) and args.command != "projects":
        parser.error("--favorite、--tag、--hidden 和 --include-hidden 只适用于 projects")
    if args.hidden and args.include_hidden:
        parser.error("--hidden 和 --include-hidden 不能同时使用")
    if (args.port is not None or args.no_open) and args.command != "web":
        parser.error("--port 和 --no-open 只适用于 web")
    if args.port is not None and not (0 <= args.port <= 65535):
        parser.error("--port 必须在 0 到 65535 之间")
    if (args.open_with is not None or args.dry_run) and args.command != "open":
        parser.error("--with 和 --dry-run 只适用于 open")

    linking = args.command in ("link", "unlink")
    tagging = args.command in ("tag", "untag")
    single_target = args.command in (
        "inspect",
        "open",
        "star",
        "unstar",
        "hide",
        "unhide",
    )
    if tagging:
        if len(args.targets) < 2:
            parser.error("tag 和 untag 需要一个项目 ID 以及至少一个标签")
    elif linking:
        if len(args.targets) != 2:
            parser.error("link 和 unlink 需要两个项目 ID")
    elif single_target:
        if len(args.targets) != 1:
            parser.error(f"{args.command} 需要一个 ID")
    elif args.targets:
        parser.error(f"{args.command} 不接受位置参数")

    if args.historical and not args.indexed:
        parser.error("--historical 需要 --indexed")
    if (args.status or args.historical) and args.command != "projects":
        parser.error("--status 和 --historical 只适用于 projects")
    if args.indexed and (
        args.command in ("scan", "web") or linking or args.command in META_COMMANDS
    ):
        parser.error("--indexed 用于查询已保存的结果")
    if args.no_index and args.command != "scan":
        parser.error("--no-index 只适用于 scan")

    index = LocalIndex(args.index_file)
    scope = scope_key(args.agent, args.path)

    if args.command == "web":
        try:
            serve_web(
                index=index,
                selected_agent=args.agent,
                paths=args.path,
                port=args.port,
                open_browser=not args.no_open,
            )
        except OSError as error:
            parser.exit(1, f"启动本地 Web 服务失败。{error}\n")
        return

    try:
        if linking:
            first, second = args.targets
            index.change_link(
                scope, first, second, remove=args.command == "unlink"
            )
            if args.json:
                print(
                    json.dumps(
                        dict(
                            projects=[first, second],
                            linked=args.command == "link",
                        ),
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"{args.command} {first} {second}")
            return
        if args.command in META_COMMANDS:
            project_id = args.targets[0]
            kwargs = {}
            if args.command in ("star", "unstar"):
                kwargs["favorite"] = args.command == "star"
            elif args.command in ("hide", "unhide"):
                kwargs["hidden"] = args.command == "hide"
            elif args.command == "tag":
                kwargs["add_tags"] = args.targets[1:]
            elif args.command == "untag":
                kwargs["remove_tags"] = args.targets[1:]
            updated = index.update_meta(scope, project_id, **kwargs)
            if args.json:
                print(json.dumps(updated, indent=2, ensure_ascii=False))
            else:
                tag_text = ",".join(updated["tags"]) or "—"
                print(
                    f"{updated['project_id']}\tfavorite={updated['favorite']}\thidden={updated['hidden']}\ttags={tag_text}"
                )
            return
        result = (
            index.load(scope)
            if args.indexed
            else scan(selected=args.agent, paths=args.path)
        )
        if args.command == "scan" and not args.no_index:
            result = index.save(scope, result)
        elif not args.indexed and args.command in (
            "projects",
            "inspect",
            "open",
            "hygiene",
        ):
            result = index.hydrate_live(result)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"本地索引 {index.path} 处理失败。{error}\n")

    if args.command == "hygiene":
        home_dir = str(Path.home())
        visible = []
        for proj in result.get("projects", []):
            row = dict(proj)
            annotate_project(row, home=home_dir)
            if row.get("asset_kind") == "noise":
                continue
            visible.append(row)
        report = scan_hygiene(visible, home_dir=home_dir)
        by_id = {p["id"]: p for p in visible}
        reclaimable = []
        for pid, info in report.get("by_project", {}).items():
            size = info.get("reclaimable_bytes", 0)
            if size <= 0 or pid not in by_id:
                continue
            proj = by_id[pid]
            reclaimable.append(
                {
                    "project_id": pid,
                    "path": proj["path"],
                    "asset_kind": proj.get("asset_kind"),
                    "last_activity": proj.get("last_activity"),
                    "agents": proj.get("agents", []),
                    "reclaimable_bytes": size,
                    "artifacts": info.get("artifacts", []),
                }
            )
        reclaimable.sort(key=lambda item: (-item["reclaimable_bytes"], item["path"]))
        if args.json:
            payload = {
                "scanned_at": report.get("scanned_at"),
                "duration_ms": report.get("duration_ms"),
                "summary": report.get("summary", {}),
                "reclaimable": reclaimable,
                "duplicate_groups": report.get("duplicate_groups", []),
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return

        def _fmt_bytes(num):
            if num < 1024:
                return f"{num} B"
            if num < 1024**2:
                return f"{num / 1024:.1f} KB"
            if num < 1024**3:
                return f"{num / 1024**2:.1f} MB"
            return f"{num / 1024**3:.2f} GB"

        summary = report.get("summary", {})
        print(
            f"可瘦身空间 {_fmt_bytes(summary.get('total_reclaimable_bytes', 0))}"
            f"（{summary.get('reclaimable_project_count', 0)} 个目录）  "
            f"同仓库多副本 {summary.get('duplicate_group_count', 0)} 组  "
            f"临时沙箱 {summary.get('sandbox_count', 0)} 个"
        )
        if reclaimable:
            print("SIZE\tLAST ACTIVITY (UTC)\tARTIFACTS\tPATH")
            for item in reclaimable[:20]:
                arts = ",".join(a["rel_path"] for a in item["artifacts"][:4])
                print(
                    _fmt_bytes(item["reclaimable_bytes"]),
                    item["last_activity"] or "—",
                    arts,
                    item["path"],
                    sep="\t",
                )
        dup_groups = report.get("duplicate_groups", [])
        if dup_groups:
            print("\nDUPLICATE REPOS\tCOPIES\tPATHS")
            for grp in dup_groups:
                paths_str = " | ".join(
                    by_id[pid]["path"] for pid in grp.get("project_ids", []) if pid in by_id
                )
                print(grp["name"], grp["count"], paths_str, sep="\t")
        return

    if args.command == "open":
        query = args.targets[0]
        project, candidates = _resolve_project_for_open(result["projects"], query)
        if project is None:
            if candidates:
                lines = ["匹配到多个项目，请改用更精确的名称或项目 ID："]
                for item in candidates[:8]:
                    lines.append(f"  {item['id']}\t{item['path']}")
                parser.exit(1, "\n".join(lines) + "\n")
            parser.exit(1, "未找到匹配的项目，请确认名称/ID 以及扫描范围\n")
        target = args.open_with or "auto"
        if target == "auto":
            target = (
                pick_preferred_editor(project, result.get("workspaces", []))
                or "finder"
            )
        path = project["path"]
        state = path_state(path)
        remote_url = None
        if target == "remote":
            git_meta = detect_git_info(path, status=state)
            remote_url = (
                git_meta.get("remote_url") if isinstance(git_meta, dict) else None
            )
        elif state != "directory" or not os.path.isabs(path):
            parser.exit(
                1,
                f"{OPEN_ERROR_MESSAGES.get(state, '该路径当前无法打开')}：{path}\n",
            )
        try:
            if args.dry_run:
                cmd, label, opened = build_launch_command(
                    path, target, remote_url=remote_url
                )
                payload = {
                    "ok": True,
                    "dry_run": True,
                    "project_id": project["id"],
                    "path": path,
                    "target": target,
                    "label": label,
                    "opened": opened,
                    "command": cmd,
                }
            else:
                launched = launch_target(path, target, remote_url=remote_url)
                payload = {
                    "ok": True,
                    "project_id": project["id"],
                    "path": path,
                    **launched,
                }
        except ValueError as error:
            _, _, message = str(error).partition("|")
            parser.exit(1, f"{message or error}\n")
        except (OSError, subprocess.SubprocessError) as error:
            parser.exit(1, f"无法打开项目：{error}\n")
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            prefix = "[dry-run] " if args.dry_run else ""
            print(f"{prefix}已通过 {payload['label']} 打开 {payload['opened']}")
        return

    if args.command == "inspect":
        target_id = args.targets[0]
        matches = [
            r
            for key in ("projects", "workspaces")
            for r in result[key]
            if r["id"] == target_id
        ]
        if not matches:
            parser.exit(1, "未找到该 ID，请使用相同的 --path 和 --agent 扫描范围\n")
        record = matches[0]
        output = (
            dict(
                record,
                evidence=[
                    w for w in result["workspaces"] if w["id"] in record["workspaces"]
                ],
            )
            if "workspaces" in record
            else record
        )
    elif args.command == "scan":
        output = result
    else:
        output = result["diagnostics" if args.command == "doctor" else args.command]
    if args.command in ("projects", "workspaces"):
        # The scan scope already selects the requested Agent and any explicit
        # filesystem roots. Keep both in the combined view.
        if args.status:
            output = [r for r in output if r["status"] == args.status]
        if args.historical:
            output = [r for r in output if r["index_state"] == "historical"]
        hidden_mode = (
            "only"
            if args.hidden
            else "include"
            if args.include_hidden
            else "exclude"
        )
        output = filter_rows(
            output,
            args.name,
            args.path_contains,
            args.since,
            args.recent,
            favorite=args.favorite,
            tags=args.tag,
            hidden_mode=hidden_mode if args.command == "projects" else "include",
        )
    if args.json or args.command == "inspect":
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return
    if args.command == "scan":
        print(
            "  ".join(
                f"{len(result[name])} {name}"
                for name in ("agents", "workspaces", "projects", "diagnostics")
            )
        )
        output = result["agents"]
    if args.command in ("scan", "agents"):
        print("AGENT\t安装状态\t工作区记录\t扫描状态")
        for r in output:
            state = (
                "已安装"
                if r["installed"]
                else "仅发现数据"
                if r["data"]
                else "未探测到"
            )
            print(r["agent"], state, r["records"], r["status"], sep="\t")
    elif args.command == "projects":
        show_meta = bool(
            args.favorite
            or args.tag
            or args.hidden
            or args.include_hidden
            or any(r.get("favorite") or r.get("tags") for r in output)
        )
        columns = "ID\tAGENTS\tSTATUS\tLAST ACTIVITY (UTC)\tPATH"
        if args.indexed:
            columns += "\tINDEX STATE\tRELATED PROJECTS"
        if show_meta:
            columns += "\tFAVORITE\tTAGS"
        print(columns)
        for r in output:
            print(
                r["id"],
                ",".join(r["agents"]),
                r["status"],
                r["last_activity"] or "—",
                r["path"],
                *(
                    [r["index_state"], ",".join(r.get("related_projects", []))]
                    if args.indexed
                    else []
                ),
                *(
                    ["★" if r.get("favorite") else "—", ",".join(r.get("tags", []))]
                    if show_meta
                    else []
                ),
                sep="\t",
            )
    elif args.command == "workspaces":
        print("ID\tAGENT\tTYPE\tNAME\tLAST ACTIVITY (UTC)\tROOTS")
        for r in output:
            print(
                r["id"],
                r["agent"],
                r["kind"],
                r["name"] or "",
                r["last_activity"] or "—",
                " | ".join(r["roots"]),
                sep="\t",
            )
    else:
        print("AGENT\tCODE\tSOURCE\tREASON")
        for r in output:
            print(r["agent"], r["code"], r["source"], r["reason"], sep="\t")


def run():
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
