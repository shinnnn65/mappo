import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mappo.core.engine import scan
from mappo.host.web_server import WebApp, create_server
from mappo.storage.local_index import LocalIndex, scope_key


class WebAndMetadataTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.repo_a = self.home / "code" / "alpha"
        self.repo_b = self.home / "code" / "beta"
        self.repo_a.mkdir(parents=True)
        self.repo_b.mkdir(parents=True)
        self.missing_path = self.home / "code" / "gone"
        (self.home / ".claude.json").write_text(
            json.dumps(
                {
                    "projects": {
                        str(self.repo_a): {},
                        str(self.repo_b): {},
                        str(self.missing_path): {},
                    }
                }
            ),
            encoding="utf-8",
        )
        self.index = LocalIndex(self.home / "state" / "index.sqlite")

    def _request(self, url, method="GET", body=None, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(url, data=data, method=method, headers=headers or {})
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8"), resp.headers
        except HTTPError as err:
            return err.code, err.read().decode("utf-8"), err.headers

    def test_cli_and_index_metadata_consistency(self):
        env = dict(os.environ, HOME=str(self.home))
        mappo = str(Path(__file__).resolve().parents[1] / "mappo")
        index_arg = ["--index-file", str(self.index.path)]
        subprocess.check_output([mappo, "scan", "--agent", "claude", *index_arg], env=env)
        projects = json.loads(
            subprocess.check_output(
                [mappo, "projects", "--agent", "claude", "--indexed", "--json", *index_arg],
                env=env,
            )
        )
        alpha = next(p for p in projects if p["path"] == str(self.repo_a))
        beta = next(p for p in projects if p["path"] == str(self.repo_b))

        subprocess.check_output(
            [mappo, "star", alpha["id"], "--agent", "claude", *index_arg], env=env
        )
        subprocess.check_output(
            [mappo, "tag", alpha["id"], "核心", "Frontend", "frontend", "--agent", "claude", *index_arg],
            env=env,
        )
        subprocess.check_output(
            [mappo, "hide", beta["id"], "--agent", "claude", *index_arg], env=env
        )

        # Live projects query hydrates metadata and excludes hidden by default
        live = json.loads(
            subprocess.check_output(
                [mappo, "projects", "--agent", "claude", "--json", *index_arg], env=env
            )
        )
        self.assertNotIn(beta["id"], [p["id"] for p in live])
        favs = json.loads(
            subprocess.check_output(
                [mappo, "projects", "--agent", "claude", "--indexed", "--favorite", "--tag", "frontend", "--json", *index_arg],
                env=env,
            )
        )
        self.assertEqual([p["id"] for p in favs], [alpha["id"]])
        self.assertEqual(favs[0]["tags"], ["Frontend", "核心"])

        hidden_only = json.loads(
            subprocess.check_output(
                [mappo, "projects", "--agent", "claude", "--indexed", "--hidden", "--json", *index_arg],
                env=env,
            )
        )
        self.assertEqual([p["id"] for p in hidden_only], [beta["id"]])

        # Unhide and untag work cleanly
        subprocess.check_output(
            [mappo, "unhide", beta["id"], "--agent", "claude", *index_arg], env=env
        )
        subprocess.check_output(
            [mappo, "untag", alpha["id"], "FRONTEND", "--agent", "claude", *index_arg],
            env=env,
        )
        inspected = json.loads(
            subprocess.check_output(
                [mappo, "inspect", alpha["id"], "--agent", "claude", "--indexed", *index_arg],
                env=env,
            )
        )
        self.assertTrue(inspected["favorite"])
        self.assertEqual(inspected["tags"], ["核心"])

    def test_web_server_api_security_open_and_singleflight(self):
        opened = []
        scan_calls = []

        def slow_scan():
            scan_calls.append(1)
            time.sleep(0.08)
            return scan(self.home, "claude")

        app = WebApp(
            index=self.index,
            selected_agent="claude",
            scan_fn=slow_scan,
            opener=opened.append,
            home_dir=self.home,
        )
        server, url = create_server(app, port=0, quiet=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        # HTML injects session token and static assets load cleanly
        status, html_text, _ = self._request(f"{url}/")
        self.assertEqual(status, 200)
        self.assertIn("<title>Mappo</title>", html_text)
        self.assertIn("/assets/icons/mappo.svg", html_text)
        self.assertIn(f'content="{app.token}"', html_text)
        css_status, css_text, _ = self._request(f"{url}/assets/app.css")
        self.assertEqual(css_status, 200)
        self.assertIn("--ease-snappy", css_text)

        # Cold-start GET /api/state auto-scans and saves index
        status, state_raw, _ = self._request(f"{url}/api/state")
        self.assertEqual(status, 200)
        state = json.loads(state_raw)
        self.assertEqual(len(state["projects"]), 3)
        self.assertEqual(len(scan_calls), 1)
        alpha = next(p for p in state["projects"] if p["path"] == str(self.repo_a))
        beta = next(p for p in state["projects"] if p["path"] == str(self.repo_b))
        missing = next(p for p in state["projects"] if p["path"] == str(self.missing_path))

        # CSRF protection rejects missing/invalid token or foreign Origin
        status, _, _ = self._request(
            f"{url}/api/projects/{alpha['id']}/meta",
            method="PATCH",
            body={"favorite": True},
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)
        status, _, _ = self._request(
            f"{url}/api/projects/{alpha['id']}/meta",
            method="PATCH",
            body={"favorite": True},
            headers={
                "Content-Type": "application/json",
                "X-Mappo-Token": app.token,
                "Origin": "https://evil.example",
            },
        )
        self.assertEqual(status, 403)

        auth = {"Content-Type": "application/json", "X-Mappo-Token": app.token}
        # Valid meta update persists favorite, tags, hidden
        status, body, _ = self._request(
            f"{url}/api/projects/{alpha['id']}/meta",
            method="PATCH",
            body={"favorite": True, "add_tags": ["主力", "AI"]},
            headers=auth,
        )
        self.assertEqual(status, 200)
        updated = json.loads(body)
        self.assertTrue(updated["favorite"])
        self.assertEqual(updated["tags"], ["AI", "主力"])

        # Open directory succeeds for valid directory, rejects missing path
        status, _, _ = self._request(
            f"{url}/api/projects/{alpha['id']}/open",
            method="POST",
            headers={"X-Mappo-Token": app.token},
        )
        self.assertEqual(status, 200)
        self.assertEqual(opened, [str(self.repo_a)])

        status, err_raw, _ = self._request(
            f"{url}/api/projects/{missing['id']}/open",
            method="POST",
            headers={"X-Mappo-Token": app.token},
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(err_raw)["code"], "missing")

        # Manual links via API
        status, link_raw, _ = self._request(
            f"{url}/api/links",
            method="POST",
            body={"first": alpha["id"], "second": beta["id"]},
            headers=auth,
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(link_raw)["related"][alpha["id"]], [beta["id"]])

        # Single-flight scan coalesces concurrent POST /api/scan
        before = len(scan_calls)
        results = []
        workers = [
            threading.Thread(
                target=lambda: results.append(
                    self._request(
                        f"{url}/api/scan",
                        method="POST",
                        headers={"X-Mappo-Token": app.token},
                    )[0]
                )
            )
            for _ in range(3)
        ]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        self.assertEqual(results, [200, 200, 200])
        self.assertEqual(len(scan_calls) - before, 1)

        # Reloading index from LocalIndex confirms persistence
        reloaded = self.index.load(scope_key("claude", []))
        reloaded_alpha = next(p for p in reloaded["projects"] if p["id"] == alpha["id"])
        self.assertTrue(reloaded_alpha["favorite"])
        self.assertEqual(reloaded_alpha["tags"], ["AI", "主力"])
        self.assertEqual(reloaded_alpha["related_projects"], [beta["id"]])

        # Non-object JSON body and invalid tag payload types return 400
        for bad_body in (["not", "dict"], "plain"):
            status, _, _ = self._request(
                f"{url}/api/links",
                method="POST",
                body=bad_body,
                headers=auth,
            )
            self.assertEqual(status, 400)
        for bad_tags in ({"add_tags": "abc"}, {"add_tags": 123}, {"remove_tags": "x"}):
            status, _, _ = self._request(
                f"{url}/api/projects/{alpha['id']}/meta",
                method="PATCH",
                body=bad_tags,
                headers=auth,
            )
            self.assertEqual(status, 400)

        # Multi-space tag normalization matches consistently in filter_rows
        status, body, _ = self._request(
            f"{url}/api/projects/{alpha['id']}/meta",
            method="PATCH",
            body={"add_tags": ["my   team"]},
            headers=auth,
        )
        self.assertEqual(status, 200)
        self.assertIn("my team", json.loads(body)["tags"])
        from mappo.query.search import filter_rows

        matched = filter_rows(
            self.index.load(scope_key("claude", []))["projects"],
            tags=["MY    TEAM"],
        )
        self.assertEqual([p["id"] for p in matched], [alpha["id"]])

    def test_asset_classification_noise_filtering_and_sandbox_promotion(self):
        from mappo.core.classify import classify_project, parse_remote_uri

        fake_home = Path("/Users/tester")
        self.assertEqual(
            classify_project({"path": "/private/tmp/cache-run", "status": "missing"}, home=fake_home)[:2],
            ("noise", "temp_cache"),
        )
        self.assertEqual(
            classify_project({"path": "/", "status": "directory"}, home=fake_home)[:2],
            ("noise", "system_dir"),
        )
        self.assertEqual(
            classify_project({"path": "/Users/tester/Downloads", "status": "directory"}, home=fake_home)[:2],
            ("noise", "system_dir"),
        )
        self.assertEqual(
            classify_project(
                {"path": "/Users/tester/.codex/worktrees/1a2b/app", "status": "missing"},
                home=fake_home,
            )[:2],
            ("noise", "deleted_worktree"),
        )
        self.assertEqual(
            classify_project(
                {"path": "/Users/tester/Code/app", "status": "missing"},
                home=fake_home,
            )[:2],
            ("project", "missing_project"),
        )
        self.assertEqual(
            classify_project(
                {"path": "/Users/tester/Documents/Codex/2026-06-08/new-chat", "status": "directory"},
                home=fake_home,
            )[:2],
            ("sandbox", "agent_sandbox"),
        )
        self.assertEqual(
            classify_project(
                {"path": "/Users/tester/Code/app/.worktrees/feat", "status": "directory"},
                home=fake_home,
            )[:2],
            ("sandbox", "active_worktree"),
        )
        remote_uri = "vscode-remote://ssh-remote%2Broot@dev1.example.com:36000/data/workspace/demo"
        parsed = parse_remote_uri(remote_uri)
        self.assertEqual(parsed["host"], "dev1.example.com")
        self.assertEqual(parsed["remote_path"], "/data/workspace/demo")
        self.assertEqual(parsed["group_key"], "/data/workspace/demo")
        self.assertEqual(
            classify_project({"path": "vscode-remote://ssh-remote%2Bdev1/tmp", "status": "remote"}, home=fake_home)[:2],
            ("noise", "remote_temp"),
        )

        # End-to-end WebApp noise filtering and sandbox promotion
        sandbox_dir = self.home / "WorkBuddy" / "2026-11-10-17-34-47"
        sandbox_dir.mkdir(parents=True)
        downloads_dir = self.home / "Downloads"
        downloads_dir.mkdir(parents=True)
        deleted_wt = self.home / ".codex" / "worktrees" / "abc1" / "alpha"
        (self.home / ".claude.json").write_text(
            json.dumps(
                {
                    "projects": {
                        str(self.repo_a): {},
                        str(sandbox_dir): {},
                        str(downloads_dir): {},
                        str(deleted_wt): {},
                        str(self.missing_path): {},
                    }
                }
            ),
            encoding="utf-8",
        )
        app = WebApp(
            index=LocalIndex(self.home / "state" / "classify.sqlite"),
            selected_agent="claude",
            scan_fn=lambda: scan(self.home, "claude"),
            home_dir=self.home,
        )
        state = app.get_state()
        self.assertEqual(state["filtered_noise_count"], 2)
        by_path = {p["path"]: p for p in state["projects"]}
        self.assertNotIn(str(downloads_dir), by_path)
        self.assertNotIn(str(deleted_wt), by_path)
        self.assertEqual(by_path[str(self.repo_a)]["asset_kind"], "project")
        self.assertEqual(by_path[str(sandbox_dir)]["asset_kind"], "sandbox")
        self.assertEqual(by_path[str(self.missing_path)]["asset_kind"], "project")
        self.assertEqual(by_path[str(self.missing_path)]["asset_reason"], "missing_project")

        # Promote sandbox to formal project and verify persistence
        sb_id = by_path[str(sandbox_dir)]["id"]
        updated = app.update_meta(sb_id, {"promoted": True})
        self.assertTrue(updated["promoted"])
        self.assertEqual(updated["asset_kind"], "project")
        self.assertEqual(updated["asset_reason"], "promoted_sandbox")

        reloaded = app.get_state()
        sb_reloaded = next(p for p in reloaded["projects"] if p["id"] == sb_id)
        self.assertTrue(sb_reloaded["promoted"])
        self.assertEqual(sb_reloaded["asset_kind"], "project")

    def test_git_detection_and_worktree_pointer_classification(self):
        from mappo.core.classify import detect_git_info

        # Standard git repository with branch and credential-bearing remote URL
        main_repo = self.home / "code" / "main-repo"
        git_dir = main_repo / ".git"
        (git_dir / "worktrees" / "wt-alpha").mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/feat/git-filter\n", encoding="utf-8")
        (git_dir / "config").write_text(
            '[core]\n\trepositoryformatversion = 0\n'
            '[remote "origin"]\n\turl = https://user:secret@git.example.com/org/main-repo.git\n',
            encoding="utf-8",
        )
        repo_info = detect_git_info(str(main_repo), status="directory", home=self.home)
        self.assertEqual(
            repo_info,
            {
                "is_git": True,
                "kind": "repo",
                "branch": "feat/git-filter",
                "detached": False,
                "remote_name": "origin",
                "remote_url": "https://git.example.com/org/main-repo.git",
                "parent_repo": None,
            },
        )

        # Subdirectory inside parent git repository
        sub_pkg = main_repo / "packages" / "web"
        sub_pkg.mkdir(parents=True)
        sub_info = detect_git_info(str(sub_pkg), status="directory", home=self.home)
        self.assertTrue(sub_info["is_git"])
        self.assertEqual(sub_info["kind"], "subdir")
        self.assertEqual(sub_info["parent_repo"], str(main_repo.resolve()))
        self.assertEqual(sub_info["branch"], "feat/git-filter")
        self.assertEqual(sub_info["remote_url"], "https://git.example.com/org/main-repo.git")

        # Worktree located under a custom directory name without ".worktrees" or "worktrees" segment
        wt_dir = self.home / "code" / "main-repo-worktrees" / "wt-alpha"
        wt_dir.mkdir(parents=True)
        wt_git_dir = git_dir / "worktrees" / "wt-alpha"
        (wt_git_dir / "HEAD").write_text("ref: refs/heads/chore/sync\n", encoding="utf-8")
        (wt_git_dir / "commondir").write_text("../..\n", encoding="utf-8")
        (wt_dir / ".git").write_text(f"gitdir: {wt_git_dir}\n", encoding="utf-8")

        # Plain local directory without any .git
        plain_dir = self.home / "code" / "plain-notes"
        plain_dir.mkdir(parents=True)
        plain_info = detect_git_info(str(plain_dir), status="directory", home=self.home)
        self.assertEqual(plain_info, {"is_git": False, "kind": "none"})

        # End-to-end WebApp verification
        (self.home / ".claude.json").write_text(
            json.dumps(
                {
                    "projects": {
                        str(main_repo): {},
                        str(sub_pkg): {},
                        str(wt_dir): {},
                        str(plain_dir): {},
                    }
                }
            ),
            encoding="utf-8",
        )
        app = WebApp(
            index=LocalIndex(self.home / "state" / "git-detect.sqlite"),
            selected_agent="claude",
            scan_fn=lambda: scan(self.home, "claude"),
            home_dir=self.home,
        )
        state = app.get_state()
        by_path = {p["path"]: p for p in state["projects"]}
        self.assertEqual(by_path[str(main_repo)]["asset_kind"], "project")
        self.assertEqual(by_path[str(main_repo)]["git"]["kind"], "repo")
        self.assertEqual(by_path[str(sub_pkg)]["asset_kind"], "project")
        self.assertEqual(by_path[str(sub_pkg)]["git"]["kind"], "subdir")
        self.assertEqual(by_path[str(plain_dir)]["asset_kind"], "project")
        self.assertFalse(by_path[str(plain_dir)]["git"]["is_git"])
        self.assertEqual(by_path[str(wt_dir)]["asset_kind"], "sandbox")
        self.assertEqual(by_path[str(wt_dir)]["asset_reason"], "active_worktree")
        self.assertEqual(by_path[str(wt_dir)]["git"]["kind"], "worktree")
        self.assertEqual(by_path[str(wt_dir)]["git"]["branch"], "chore/sync")
        self.assertEqual(
            by_path[str(wt_dir)]["git"]["parent_repo"], str(main_repo.resolve())
        )

    def test_release_zipapp_contains_current_assets(self):
        import zipfile

        root = Path(__file__).resolve().parents[1]
        out = self.home / "mappo.pyz"
        subprocess.check_call(
            ["python3", "-B", str(root / "scripts" / "build_release.py"), str(out)]
        )
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(
                archive.read("mappo/host/web_server.py"),
                (root / "src" / "mappo" / "host" / "web_server.py").read_bytes(),
            )
            for asset in (
                "index.html",
                "app.css",
                "app.js",
                "icons/mappo.svg",
                "icons/cursor.png",
                "icons/gemini.svg",
            ):
                self.assertEqual(
                    archive.read(f"mappo/_web_assets/{asset}"),
                    (root / "apps" / "web" / asset).read_bytes(),
                )
        icon_bytes = subprocess.check_output(
            [
                "python3",
                "-B",
                "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from mappo.host.assets import load_asset; "
                "print(len(load_asset('icons/cursor.png')))",
                str(out),
            ],
            text=True,
        ).strip()
        self.assertEqual(
            int(icon_bytes),
            (root / "apps" / "web" / "icons" / "cursor.png").stat().st_size,
        )
        env = dict(os.environ, HOME=str(self.home))
        version = subprocess.check_output(
            ["python3", "-B", str(out), "--version"],
            cwd=str(self.home),
            env=env,
            text=True,
        ).strip()
        self.assertTrue(version.startswith("mappo "))

    def test_icon_assets_endpoint(self):
        app = WebApp(
            index=LocalIndex(self.home / "state" / "icons.sqlite"),
            selected_agent="claude",
            scan_fn=lambda: scan(self.home, "claude"),
            home_dir=self.home,
        )
        server, base = create_server(app, port=0, quiet=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with urlopen(f"{base}/assets/icons/cursor.png", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/png")
            self.assertTrue(resp.read().startswith(b"\x89PNG"))
        with urlopen(f"{base}/assets/icons/mappo.svg", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("image/svg+xml", resp.headers.get("Content-Type", ""))
            self.assertIn(b"<svg", resp.read())
        with urlopen(f"{base}/assets/icons/gemini.svg", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("image/svg+xml", resp.headers.get("Content-Type", ""))
            self.assertIn(b"<svg", resp.read())
        for bad in ("nonexistent.png", "../app.js", "cursor.exe"):
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"{base}/assets/icons/{bad}", timeout=5)
            self.assertEqual(ctx.exception.code, 404)

    def test_launcher_targets_api_and_cli_open(self):
        from mappo.host.launcher import (
            build_launch_command,
            pick_preferred_editor,
            remote_web_url,
        )

        # Remote URL normalization
        self.assertEqual(
            remote_web_url("git@github.com:org/demo.git"),
            "https://github.com/org/demo",
        )
        self.assertEqual(
            remote_web_url("ssh://git@gitlab.example.com/team/app.git"),
            "https://gitlab.example.com/team/app",
        )
        self.assertEqual(
            remote_web_url("https://github.com/org/demo.git/"),
            "https://github.com/org/demo",
        )
        self.assertIsNone(remote_web_url("file:///tmp/local"))

        # Preferred editor picks most recently active available editor
        launchers = [
            {"id": "cursor", "kind": "editor", "available": True},
            {"id": "vscode", "kind": "editor", "available": True},
            {"id": "trae", "kind": "editor", "available": False},
        ]
        proj = {"agents": ["claude", "vscode", "cursor"], "workspaces": ["w1", "w2"]}
        workspaces = [
            {"id": "w1", "agent": "vscode", "last_activity": "2026-11-20T08:00:00Z"},
            {"id": "w2", "agent": "cursor", "last_activity": "2026-11-24T08:00:00Z"},
        ]
        self.assertEqual(pick_preferred_editor(proj, workspaces, launchers), "cursor")

        # Command builder handles CLI fallback and rejects unknown targets
        cmd, label, opened = build_launch_command(
            str(self.repo_a),
            "vscode",
            platform="linux",
            which=lambda name: "/usr/bin/code" if name == "code" else None,
        )
        self.assertEqual(cmd, ["/usr/bin/code", str(self.repo_a)])
        self.assertEqual(label, "VS Code")
        self.assertEqual(opened, str(self.repo_a))
        with self.assertRaises(ValueError):
            build_launch_command(str(self.repo_a), "unknown-ide", platform="darwin")

        # Prepare Git remote on repo_a for web_url & remote launch verification
        git_dir = self.repo_a / ".git"
        git_dir.mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (git_dir / "config").write_text(
            '[remote "origin"]\n\turl = git@github.com:acme/alpha.git\n',
            encoding="utf-8",
        )

        # Web API multi-target open + launchers metadata
        calls = []
        app = WebApp(
            index=LocalIndex(self.home / "state" / "launch.sqlite"),
            selected_agent="claude",
            scan_fn=lambda: scan(self.home, "claude"),
            opener=lambda path, target: calls.append((path, target)),
            home_dir=self.home,
        )
        server, url = create_server(app, port=0, quiet=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        status, state_raw, _ = self._request(f"{url}/api/state")
        self.assertEqual(status, 200)
        state = json.loads(state_raw)
        self.assertTrue(any(item["id"] == "finder" for item in state["launchers"]))
        alpha = next(p for p in state["projects"] if p["path"] == str(self.repo_a))
        self.assertEqual(alpha["git"]["web_url"], "https://github.com/acme/alpha")

        auth = {"Content-Type": "application/json", "X-Mappo-Token": app.token}
        for target, expected_opened in (
            ("terminal", str(self.repo_a)),
            ("cursor", str(self.repo_a)),
            ("remote", "https://github.com/acme/alpha"),
        ):
            status, body, _ = self._request(
                f"{url}/api/projects/{alpha['id']}/open",
                method="POST",
                body={"target": target},
                headers=auth,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["target"], target)
            self.assertEqual(calls[-1], (expected_opened, target))

        status, err_raw, _ = self._request(
            f"{url}/api/projects/{alpha['id']}/open",
            method="POST",
            body={"target": "not-a-tool"},
            headers=auth,
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(err_raw)["code"], "unsupported_target")

        # CLI open --dry-run resolves by project name and ID
        env = dict(os.environ, HOME=str(self.home))
        mappo = str(Path(__file__).resolve().parents[1] / "mappo")
        index_arg = ["--index-file", str(self.index.path)]
        subprocess.check_output([mappo, "scan", "--agent", "claude", *index_arg], env=env)
        opened_cli = json.loads(
            subprocess.check_output(
                [
                    mappo,
                    "open",
                    "alpha",
                    "--with",
                    "remote",
                    "--indexed",
                    "--dry-run",
                    "--json",
                    "--agent",
                    "claude",
                    *index_arg,
                ],
                env=env,
                text=True,
            )
        )
        self.assertTrue(opened_cli["dry_run"])
        self.assertEqual(opened_cli["target"], "remote")
        self.assertEqual(opened_cli["opened"], "https://github.com/acme/alpha")

    def test_desktop_agent_launchers_and_recent_agent_ordering(self):
        import plistlib
        from mappo.core.engine import sort_project_agents
        from mappo.host.launcher import (
            build_launch_command,
            detect_launchers,
            pick_preferred_launcher,
        )

        # Fake user Applications folder with ChatGPT.app (com.openai.codex),
        # Trae CN.app, WorkBuddy.app, Claude.app, and DeepSeek Harness.app.
        fake_home = self.home / "fake-home"
        apps_dir = fake_home / "Applications"
        for app_name, bundle_id in (
            ("ChatGPT.app", "com.openai.codex"),
            ("Trae CN.app", "com.trae.cn"),
            ("WorkBuddy.app", "com.example.workbuddy"),
            ("Claude.app", "com.anthropic.claudefordesktop"),
            ("Antigravity IDE.app", "com.google.antigravity-ide"),
            ("Antigravity.app", "com.google.antigravity"),
            ("DeepSeek Harness.app", "ai.deepseek.harness"),
        ):
            plist_dir = apps_dir / app_name / "Contents"
            plist_dir.mkdir(parents=True, exist_ok=True)
            with (plist_dir / "Info.plist").open("wb") as fh:
                plistlib.dump({"CFBundleIdentifier": bundle_id}, fh)

        # Build commands for desktop agents & Trae CN (using fake_home on darwin)
        cmd_wb, label_wb, opened_wb = build_launch_command(
            str(self.repo_a), "workbuddy", home=fake_home, platform="darwin"
        )
        self.assertEqual(cmd_wb[0:2], ["open", "-a"])
        self.assertEqual(cmd_wb[-1], str(self.repo_a))
        self.assertEqual(label_wb, "WorkBuddy")
        self.assertEqual(opened_wb, str(self.repo_a))

        cmd_dsh, label_dsh, opened_dsh = build_launch_command(
            str(self.repo_a), "dsh", home=fake_home, platform="darwin"
        )
        self.assertEqual(len(cmd_dsh), 3)
        self.assertEqual(cmd_dsh[0:2], ["open", "-a"])
        self.assertEqual(label_dsh, "DeepSeek Harness")
        self.assertTrue(opened_dsh.endswith("DeepSeek Harness.app"))

        # Verify bundle_id gating: non-codex ChatGPT.app must NOT match codex
        other_home = self.home / "other-home"
        other_plist = other_home / "Applications" / "ChatGPT.app" / "Contents"
        other_plist.mkdir(parents=True)
        with (other_plist / "Info.plist").open("wb") as fh:
            plistlib.dump({"CFBundleIdentifier": "com.openai.chat"}, fh)
        # Only verify when /Applications doesn't already provide Codex/ChatGPT-codex
        launchers_fake = {
            item["id"]: item
            for item in detect_launchers(home=fake_home, platform="darwin", which=lambda _: None)
        }
        self.assertTrue(launchers_fake["codex"]["available"])
        self.assertEqual(launchers_fake["codex"]["kind"], "coding_agent")
        self.assertTrue(launchers_fake["codex"]["opens_path"])
        self.assertTrue(launchers_fake["workbuddy"]["available"])
        self.assertTrue(launchers_fake["claude"]["available"])
        self.assertTrue(launchers_fake["antigravity"]["available"])
        self.assertTrue(launchers_fake["antigravity"]["opens_path"])
        self.assertTrue(launchers_fake["dsh"]["available"])
        self.assertFalse(launchers_fake["dsh"]["opens_path"])
        self.assertTrue(launchers_fake["trae"]["available"])

        cmd_agy, label_agy, opened_agy = build_launch_command(
            str(self.repo_a), "antigravity", home=fake_home, platform="darwin"
        )
        self.assertEqual(cmd_agy[0:2], ["open", "-a"])
        self.assertEqual(cmd_agy[-1], str(self.repo_a))
        self.assertEqual(label_agy, "Antigravity IDE")
        self.assertEqual(opened_agy, str(self.repo_a))

        # Preferred launcher picks most recently active desktop agent (codex > older cursor)
        mock_launchers = [
            {"id": "cursor", "kind": "editor", "available": True, "opens_path": True},
            {"id": "codex", "kind": "coding_agent", "available": True, "opens_path": True},
            {"id": "dsh", "kind": "coding_agent", "available": True, "opens_path": False},
        ]
        proj = {
            "path": "/tmp/demo",
            "agents": ["cursor", "codex", "dsh"],
            "workspaces": ["w1", "w2", "w3"],
        }
        workspaces = [
            {"id": "w1", "agent": "cursor", "last_activity": "2026-11-20T08:00:00Z"},
            {"id": "w2", "agent": "codex", "last_activity": "2026-11-25T10:00:00Z"},
            {"id": "w3", "agent": "dsh", "last_activity": "2026-11-26T09:00:00Z"},
        ]
        # dsh has opens_path=False so codex (most recent path-opening launcher) wins
        self.assertEqual(pick_preferred_launcher(proj, workspaces, mock_launchers), "codex")

        # Per-project agent ordering: primary agents sorted by recency desc, extensions after
        ordered = sort_project_agents(
            ["cursor", "continue", "codex", "claude", "copilot"],
            {
                "cursor": "2026-11-20T00:00:00Z",
                "codex": "2026-11-25T12:00:00Z",
                "claude": "2026-11-24T00:00:00Z",
                "continue": "2026-11-26T01:00:00Z",
                "copilot": "2026-11-22T00:00:00Z",
            },
        )
        self.assertEqual(ordered, ["codex", "claude", "cursor", "continue", "copilot"])

    def test_hygiene_scan_duplicates_git_safety_and_safe_trash(self):
        from mappo.host.hygiene import (
            inspect_git_safety,
            scan_project_artifacts,
            validate_artifact_target,
        )

        # Create a real local bare remote + two clones (one clean & pushed, one dirty + .env)
        bare_remote = self.home / "remotes" / "demo.git"
        bare_remote.parent.mkdir(parents=True)
        subprocess.check_call(
            ["git", "init", "--bare", str(bare_remote)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        clone1 = self.home / "code" / "demo-main"
        clone2 = self.home / "code" / "demo-copy"
        for target in (clone1, clone2):
            target.mkdir(parents=True)
            subprocess.check_call(
                ["git", "init", "-b", "main", str(target)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.check_call(
                ["git", "-C", str(target), "config", "user.email", "dev@example.com"]
            )
            subprocess.check_call(
                ["git", "-C", str(target), "config", "user.name", "Dev"]
            )
            subprocess.check_call(
                ["git", "-C", str(target), "remote", "add", "origin", str(bare_remote)]
            )

        (clone1 / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
        (clone1 / ".gitignore").write_text("node_modules/\ndist/\n.env\n", encoding="utf-8")
        (clone1 / "src").mkdir()
        (clone1 / "src" / "main.js").write_bytes(b"z" * 512)
        subprocess.check_call(["git", "-C", str(clone1), "add", "."])
        subprocess.check_call(
            ["git", "-C", str(clone1), "commit", "-m", "init"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "-C", str(clone1), "push", "-u", "origin", "main"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Populate rebuildable artifacts on clone1 (node_modules + contextual dist)
        (clone1 / "node_modules" / "pkg").mkdir(parents=True)
        (clone1 / "node_modules" / "pkg" / "index.js").write_bytes(b"x" * 2048)
        (clone1 / "dist").mkdir()
        (clone1 / "dist" / "bundle.js").write_bytes(b"y" * 1024)

        art_scan = scan_project_artifacts(str(clone1), home_dir=self.home)
        self.assertGreaterEqual(art_scan["reclaimable_bytes"], 3072)
        self.assertEqual(
            {a["name"] for a in art_scan["artifacts"]}, {"node_modules", "dist"}
        )

        # Contextual 'dist' without build manifest is NOT matched
        plain_no_manifest = self.home / "code" / "plain-docs"
        (plain_no_manifest / "dist").mkdir(parents=True)
        (plain_no_manifest / "dist" / "notes.txt").write_bytes(b"a" * 500)
        self.assertEqual(
            scan_project_artifacts(str(plain_no_manifest), home_dir=self.home)["reclaimable_bytes"],
            0,
        )

        # Clean & pushed clone1 passes Git safety check
        safe_check = inspect_git_safety(str(clone1))
        self.assertTrue(safe_check["safe_to_trash"])
        self.assertEqual(safe_check["level"], "safe")
        self.assertEqual(safe_check["warnings"], [])

        # clone2 has uncommitted/untracked + .env -> caution
        (clone2 / "draft.txt").write_text("wip", encoding="utf-8")
        (clone2 / ".env.local").write_text("SECRET=1", encoding="utf-8")
        caution_check = inspect_git_safety(str(clone2))
        self.assertFalse(caution_check["safe_to_trash"])
        self.assertEqual(caution_check["level"], "caution")
        self.assertEqual(caution_check["untracked_count"], 2)
        self.assertIn(".env.local", caution_check["env_files"])

        # Non-git directory -> local_only
        non_git_check = inspect_git_safety(str(plain_no_manifest))
        self.assertFalse(non_git_check["safe_to_trash"])
        self.assertEqual(non_git_check["level"], "local_only")

        # Strict artifact validator rejects non-artifact dir ('src') and outside paths
        with self.assertRaises(ValueError):
            validate_artifact_target(str(clone1), str(clone1 / "src"), home_dir=self.home)
        with self.assertRaises(ValueError):
            validate_artifact_target(str(clone1), str(self.home), home_dir=self.home)

        # End-to-end WebApp hygiene API test with injectable trasher
        (self.home / ".claude.json").write_text(
            json.dumps(
                {
                    "projects": {
                        str(clone1): {},
                        str(clone2): {},
                        str(plain_no_manifest): {},
                    }
                }
            ),
            encoding="utf-8",
        )
        trashed_paths = []

        def fake_trash(path):
            trashed_paths.append(path)
            shutil.rmtree(path)

        app = WebApp(
            index=LocalIndex(self.home / "state" / "hygiene.sqlite"),
            selected_agent="claude",
            scan_fn=lambda: scan(self.home, "claude"),
            trasher=fake_trash,
            home_dir=self.home,
        )
        server, url = create_server(app, port=0, quiet=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        status, state_raw, _ = self._request(f"{url}/api/state")
        self.assertEqual(status, 200)
        state_data = json.loads(state_raw)
        # Duplicate group detected immediately from remote_url
        self.assertEqual(len(state_data["duplicate_groups"]), 1)
        self.assertEqual(state_data["duplicate_groups"][0]["count"], 2)
        p_clone1 = next(p for p in state_data["projects"] if p["path"] == str(clone1))

        auth = {"Content-Type": "application/json", "X-Mappo-Token": app.token}
        status, scan_raw, _ = self._request(
            f"{url}/api/hygiene/scan", method="POST", body={}, headers=auth
        )
        self.assertEqual(status, 200)
        hygiene_data = json.loads(scan_raw)
        self.assertTrue(hygiene_data["scanned"])
        self.assertGreaterEqual(hygiene_data["summary"]["total_reclaimable_bytes"], 3072)

        # Git safety check endpoint
        status, chk_raw, _ = self._request(
            f"{url}/api/hygiene/git-check",
            method="POST",
            body={"project_id": p_clone1["id"]},
            headers=auth,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(chk_raw)["safe_to_trash"])

        # Trash artifacts only -> source untouched, artifacts removed via trasher
        status, trash_raw, _ = self._request(
            f"{url}/api/hygiene/trash",
            method="POST",
            body={
                "mode": "artifacts",
                "items": [
                    {
                        "project_id": p_clone1["id"],
                        "paths": [str(clone1 / "node_modules")],
                    }
                ],
            },
            headers=auth,
        )
        self.assertEqual(status, 200)
        trash_res = json.loads(trash_raw)
        self.assertGreaterEqual(trash_res["freed_bytes"], 2048)
        self.assertFalse((clone1 / "node_modules").exists())
        self.assertTrue((clone1 / "src" / "main.js").exists())
        self.assertGreaterEqual(
            trash_res["hygiene"]["by_project"][p_clone1["id"]]["reclaimable_bytes"],
            1024,
        )
        self.assertEqual(
            [
                a["name"]
                for a in trash_res["hygiene"]["by_project"][p_clone1["id"]]["artifacts"]
            ],
            ["dist"],
        )

        # Reject non-artifact path via API
        status, bad_raw, _ = self._request(
            f"{url}/api/hygiene/trash",
            method="POST",
            body={
                "mode": "artifacts",
                "items": [
                    {
                        "project_id": p_clone1["id"],
                        "paths": [str(clone1 / "src")],
                    }
                ],
            },
            headers=auth,
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(bad_raw)["code"], "unsupported_artifact")

        # CLI `mappo hygiene --indexed --json` read-only report
        env = dict(os.environ, HOME=str(self.home))
        mappo_bin = str(Path(__file__).resolve().parents[1] / "mappo")
        idx_path = self.home / "state" / "cli-hygiene.sqlite"
        subprocess.check_output(
            [mappo_bin, "scan", "--agent", "claude", "--index-file", str(idx_path)],
            env=env,
        )
        hygiene_cli = json.loads(
            subprocess.check_output(
                [
                    mappo_bin,
                    "hygiene",
                    "--indexed",
                    "--json",
                    "--agent",
                    "claude",
                    "--index-file",
                    str(idx_path),
                ],
                env=env,
                text=True,
            )
        )
        self.assertEqual(hygiene_cli["summary"]["duplicate_group_count"], 1)
        self.assertGreaterEqual(hygiene_cli["summary"]["total_reclaimable_bytes"], 1024)
        self.assertEqual(len(hygiene_cli["reclaimable"]), 1)
        self.assertEqual(hygiene_cli["reclaimable"][0]["path"], str(clone1))


if __name__ == "__main__":
    unittest.main()
