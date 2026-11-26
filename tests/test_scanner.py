import json
import sqlite3
import os
import subprocess
import argparse
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from mappo.core.engine import scan
from mappo.providers.registry import SUPPORT
from mappo.query.search import filter_rows, since_time
from mappo.storage.local_index import LocalIndex, scope_key


class InventoryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.repo = self.home / "code" / "项目 one"
        self.repo.mkdir(parents=True)

    def write(self, name, content):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_six_agents_share_a_project_and_retain_evidence(self):
        root = str(self.repo)
        self.write(
            ".codex/.codex-global-state.json",
            json.dumps(
                {
                    "local-projects": {
                        "codex-id": {"rootPaths": [root], "name": "project"}
                    }
                }
            ),
        )
        self.write(
            SUPPORT / "Cursor/User/workspaceStorage/cursor-id/workspace.json",
            json.dumps({"folder": self.repo.as_uri()}),
        )
        self.write(".codebuddy/projects/encoded/first.jsonl", json.dumps({"cwd": root}))
        self.write(".claude.json", json.dumps({"projects": {root: {}}}))
        self.write(
            ".dsh/storages/workspace.json",
            json.dumps(
                {
                    "tables": {
                        "workspaces": {"dsh-id": {"path": root, "title": "project"}}
                    }
                }
            ),
        )
        db = self.home / ".workbuddy/workbuddy.db"
        db.parent.mkdir()
        with closing(sqlite3.connect(db)) as conn:
            conn.executescript(
                "CREATE TABLE workspaces(path);CREATE TABLE sessions(cwd,deleted_at);"
            )
            conn.execute("INSERT INTO workspaces VALUES (?)", (root,))
            conn.commit()
        snapshot = scan(self.home)
        project = next(p for p in snapshot["projects"] if p["path"] == root)
        self.assertEqual(
            set(project["agents"]),
            {"codex", "cursor", "codebuddy", "claude", "dsh", "workbuddy"},
        )
        self.assertEqual(scan(self.home)["projects"], snapshot["projects"])
        self.assertTrue(all(w["sources"] for w in snapshot["workspaces"]))

    def test_multiroot_and_broken_metadata(self):
        remote = "vscode-remote://ssh-remote+test/work"
        config = self.write(
            "multi.code-workspace",
            '{"folders":[/* x */{"path":"code/项目 one"},{"uri":"' + remote + '"},],}',
        )
        base = SUPPORT / "Cursor/User/workspaceStorage"
        self.write(
            base / "good/workspace.json", json.dumps({"workspace": config.as_uri()})
        )
        self.write(base / "bad/workspace.json", "{")
        result = scan(self.home, "cursor")
        self.assertEqual(result["agents"][0]["status"], "partial")
        self.assertEqual(result["workspaces"][0]["roots"], [str(self.repo), remote])
        self.assertEqual(result["projects"][-1]["status"], "remote")

    def test_filesystem_scope(self):
        self.write(self.repo / "package.json", "{}")
        self.write(self.repo / "node_modules/dependency/package.json", "{}")
        self.write("outside/pkg/package.json", "{}")
        (self.repo / "linked").symlink_to(self.home / "outside")
        result = scan(self.home, "cursor", [self.repo, self.repo])
        self.assertEqual([p["path"] for p in result["projects"]], [str(self.repo)])

    def test_index_refresh_retains_moved_paths_and_manual_links(self):
        index = LocalIndex(self.home / "state/index.sqlite")
        scope = scope_key("claude", [str(self.home)])
        old_root = str(self.repo)
        self.write(".claude.json", json.dumps({"projects": {old_root: {}}}))
        (old,) = index.save(scope, scan(self.home, "claude"))["projects"]
        new_root = self.repo.with_name("new")
        self.repo.rename(new_root)
        self.write(".claude.json", json.dumps({"projects": {str(new_root): {}}}))
        refreshed = index.save(scope, scan(self.home, "claude"))
        new = next(
            row for row in refreshed["projects"] if row["index_state"] == "observed"
        )
        index.change_link(scope, old["id"], new["id"])
        index.save(scope, scan(self.home, "claude"))
        history = next(
            row for row in index.load(scope)["projects"] if row["id"] == old["id"]
        )
        self.assertEqual(
            (history["index_state"], history["status"]), ("historical", "missing")
        )
        self.assertEqual(history["last_seen"], old["last_seen"])
        self.assertEqual(history["historical_evidence"][0]["roots"], [old_root])
        self.assertEqual(history["related_projects"], [new["id"]])
        self.assertEqual(index.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            index.load(scope_key("cursor", []))
        index.change_link(scope, old["id"], new["id"], remove=True)
        self.assertTrue(
            all("related_projects" not in row for row in index.load(scope)["projects"])
        )

    def test_antigravity_desktop_ide_and_summary_sources(self):
        root = str(self.repo)
        # 1. Native Antigravity project config
        self.write(
            ".gemini/config/projects/proj-1.json",
            json.dumps(
                {
                    "id": "proj-1",
                    "name": "项目 one",
                    "projectResources": {
                        "resources": [
                            {"gitFolder": {"folderUri": self.repo.as_uri()}}
                        ]
                    },
                }
            ),
        )
        # 2. Conversation summaries DB with last_modified_time
        db = self.home / ".gemini/antigravity/conversation_summaries.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db)) as conn:
            conn.execute(
                "CREATE TABLE conversation_summaries(workspace_uris TEXT, last_modified_time TEXT)"
            )
            conn.execute(
                "INSERT INTO conversation_summaries VALUES (?, ?)",
                (json.dumps([self.repo.as_uri()]), "2026-11-26 06:00:00+00:00"),
            )
            conn.commit()
        # 3. Antigravity IDE VS Code-family workspaceStorage
        self.write(
            SUPPORT / "Antigravity IDE/User/workspaceStorage/ide-ws/workspace.json",
            json.dumps({"folder": self.repo.as_uri()}),
        )

        snapshot = scan(self.home, "antigravity")
        agent = snapshot["agents"][0]
        self.assertEqual(agent["status"], "ok")
        self.assertGreaterEqual(agent["records"], 2)
        project = next(p for p in snapshot["projects"] if p["path"] == root)
        self.assertEqual(project["agents"], ["antigravity"])
        self.assertEqual(project["last_activity"], "2026-11-26T06:00:00.000Z")

    def test_filters_include_aliases_multi_root_and_time_evidence(self):
        config = self.write(
            "MyTeam.code-workspace",
            json.dumps({"folders": [{"path": "code/项目 one"}, {"path": "sibling"}]}),
        )
        user = SUPPORT / "Cursor/User"
        self.write(
            user / "workspaceStorage/a/workspace.json",
            json.dumps({"workspace": config.as_uri()}),
        )
        self.write(
            user / "History/opaque/entries.json",
            json.dumps(
                {
                    "resource": (self.repo / "item").as_uri(),
                    "entries": [
                        {"timestamp": 1735689600000},
                        {"timestamp": 1735000000000},
                    ],
                }
            ),
        )
        env = dict(os.environ, HOME=str(self.home))
        cmd = [
            str(Path(__file__).resolve().parents[1] / "mappo"),
            "projects",
            "--agent",
            "cursor",
            "--json",
        ]
        args = [
            "--name",
            "myteam",
            "--path-contains",
            "项目 ONE",
            "--since",
            "2025-01-01T08:00:00+08:00",
        ]
        (hit,) = json.loads(subprocess.check_output(cmd + args, env=env))
        self.assertEqual(hit["path"], str(self.repo))
        self.assertEqual(hit["last_activity"], "2025-01-01T00:00:00.000Z")
        self.assertIn("entries.timestamp", hit["activity_source"])
        rows = json.loads(subprocess.check_output(cmd, env=env))
        self.assertIsNone(
            next(r for r in rows if r["path"].endswith("/sibling"))["last_activity"]
        )
        self.assertEqual(
            json.loads(
                subprocess.check_output(
                    cmd + ["--since", "2025-01-02T00:00:00Z"], env=env
                )
            ),
            [],
        )
        self.assertEqual(
            len(json.loads(subprocess.check_output(cmd + ["--recent"], env=env))), 1
        )
        self.assertEqual(since_time("2025-01-01T08:00:00+08:00"), hit["last_activity"])
        with self.assertRaises(argparse.ArgumentTypeError):
            since_time("yesterdayish")

    def test_permission_missing_unsupported_and_partial(self):
        def status(agent):
            return scan(self.home, agent)["agents"][0]["status"]

        self.assertEqual(status("workbuddy"), "missing_source")
        self.assertEqual(status("kiro"), "unsupported")
        path = self.write(".claude.json", '{"projects":{}}')
        self.assertEqual(status("claude"), "empty")
        path.chmod(0)
        try:
            if os.access(path, os.R_OK):
                self.skipTest("requires an unprivileged process")
            self.assertEqual(status("claude"), "permission_denied")
            self.write(
                ".claude/history.jsonl",
                json.dumps({"project": str(self.repo), "timestamp": 1735689600000}),
            )
            row = scan(self.home, "claude")["agents"][0]
            self.assertEqual(
                (row["status"], row["issues"]), ("partial", ["permission_denied"])
            )
        finally:
            path.chmod(0o600)

    def test_sqlite_busy_then_retry(self):
        path = self.home / ".workbuddy/workbuddy.db"
        path.parent.mkdir()
        with closing(sqlite3.connect(path)) as writer:
            writer.executescript(
                "CREATE TABLE workspaces(path); CREATE TABLE sessions(cwd,deleted_at); BEGIN EXCLUSIVE;"
            )
            self.assertEqual(
                scan(self.home, "workbuddy")["agents"][0]["status"], "busy"
            )
            writer.rollback()
            self.assertEqual(
                scan(self.home, "workbuddy")["agents"][0]["status"], "empty"
            )
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_codex_desktop_id_and_chatgpt_mirror(self):
        base = self.home / ".codex"
        base.mkdir()
        mirror = base / ".chatgpt-projects/g-p-example"
        with closing(sqlite3.connect(base / "state_5.sqlite")) as db:
            db.executescript(
                "CREATE TABLE projects(id,name,position,updated_at_ms);"
                "CREATE TABLE project_roots(project_id,path,position); CREATE TABLE threads(cwd,updated_at);"
            )
            db.execute("INSERT INTO projects VALUES ('server','Team',1,1735689600000)")
            db.execute(
                "INSERT INTO project_roots VALUES ('server',?,1)", (str(mirror),)
            )
            db.execute("INSERT INTO threads VALUES (?,1735689600)", (str(mirror),))
            db.commit()
        with closing(sqlite3.connect(base / ".codex-global-state.sqlite")) as db:
            db.execute("CREATE TABLE settings(scope,key,value)")
            db.executemany(
                "INSERT INTO settings VALUES ('global',?,?)",
                [
                    ("local-projects", json.dumps({"desktop": {}})),
                    (
                        "app-server-project-id-by-legacy-project-id-by-host",
                        json.dumps({"local:host": {"desktop": "server"}}),
                    ),
                ],
            )
            db.commit()
        result = scan(self.home, "codex")
        (native,) = [r for r in result["workspaces"] if r["kind"] == "native"]
        self.assertEqual(
            (native["desktop_ids"], native["native_id"]), (["desktop"], "server")
        )
        self.assertEqual(native["chatgpt_project_id"], "g-p-example")
        self.assertEqual(result["projects"], [])

    def test_oversize_first_event_falls_back_to_tail(self):
        self.write(
            ".codebuddy/projects/project/a.jsonl",
            json.dumps({"oversize": "x" * 90000})
            + "\n"
            + json.dumps({"cwd": str(self.repo), "timestamp": "2025-01-01T01:00:00Z"}),
        )
        (row,) = scan(self.home, "codebuddy")["projects"]
        self.assertTrue(row["activity_source"].endswith("#last.timestamp"))
        self.assertEqual(row["path"], str(self.repo))

    def test_recent_sort_and_unknown_times(self):
        def row(name, stamp):
            return dict(name=name, roots=["/" + name], last_activity=stamp)

        older = row("older", "2025-01-01T00:00:00.000Z")
        newer = row("newer", "2025-01-02T00:00:00.000Z")
        self.assertEqual(
            filter_rows([older, newer, row("undated", None)], recent=True),
            [newer, older],
        )

    def test_custom_tools_config_extends_registry(self):
        self.write(
            ".config/mappo/custom_tools.json",
            json.dumps(
                {
                    "extensions": {
                        "acme-ext": {
                            "name": "Acme Helper",
                            "extension_id": "acme.helper-ext",
                            "data_dir": ".acme-helper",
                        }
                    },
                    "products": {
                        "acme-cli": {
                            "name": "Acme CLI",
                            "data_dir": ".acme-cli",
                            "limit": "仅探测本地配置",
                        }
                    },
                }
            ),
        )
        self.write(".acme-cli/config.json", "{}")
        self.write(".cursor/extensions/acme.helper-ext-1.0.0/package.json", "{}")
        ws_dir = self.home / SUPPORT / "Cursor/User/workspaceStorage/custom-ext-ws"
        self.write(
            ws_dir / "workspace.json",
            json.dumps({"folder": self.repo.as_uri()}),
        )
        db_path = ws_dir / "state.vscdb"
        with closing(sqlite3.connect(db_path)) as db:
            db.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
            db.execute(
                "INSERT INTO ItemTable VALUES (?, ?)",
                ("acme.helper-ext", "{}"),
            )
            db.commit()

        snapshot = scan(self.home)
        by_agent = {a["agent"]: a for a in snapshot["agents"]}
        self.assertIn("acme-ext", by_agent)
        self.assertEqual(by_agent["acme-ext"]["display_name"], "Acme Helper")
        self.assertEqual(by_agent["acme-ext"]["category"], "extension")
        self.assertEqual(by_agent["acme-ext"]["records"], 1)
        self.assertIn("acme-cli", by_agent)
        self.assertEqual(by_agent["acme-cli"]["status"], "unsupported")
        project = next(p for p in snapshot["projects"] if p["path"] == str(self.repo))
        self.assertIn("acme-ext", project["agents"])


if __name__ == "__main__":
    unittest.main()
