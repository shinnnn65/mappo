import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from mappo.providers.registry import EDITORS, SUPPORT
from mappo.sessions import (
    build_handoff,
    list_sessions,
    parse_session_ref,
    render_handoff_markdown,
    resolve_session,
)


class SessionsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.repo = self.home / "Code" / "demo-app"
        self.repo.mkdir(parents=True)

    def write(self, rel_path, content):
        path = self.home / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _seed_codex(self, tid="01a2170d-4a3f-7893-80a8-73f1ab793f8a", with_history=True):
        db = self.home / ".codex" / "state_5.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        rollout = (
            self.home
            / ".codex"
            / "sessions"
            / "2026"
            / "11"
            / "26"
            / f"rollout-2026-11-26T16-51-16-{tid}.jsonl"
        )
        rollout.parent.mkdir(parents=True, exist_ok=True)
        rollout.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "response_item",
                            "timestamp": "2026-11-26T08:51:16Z",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": "<environment_context>noise</environment_context>"}
                                ],
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "response_item",
                            "timestamp": "2026-11-26T08:52:00Z",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": "Fix the login retry bug"}
                                ],
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "response_item",
                            "timestamp": "2026-11-26T08:53:00Z",
                            "payload": {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": "Updated retry backoff in auth.py"}
                                ],
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with closing(sqlite3.connect(db)) as conn:
            conn.executescript(
                """
                CREATE TABLE threads(
                    id TEXT PRIMARY KEY,
                    rollout_path TEXT,
                    cwd TEXT,
                    title TEXT,
                    preview TEXT,
                    first_user_message TEXT,
                    created_at_ms INTEGER,
                    updated_at_ms INTEGER,
                    archived INTEGER,
                    git_branch TEXT,
                    model TEXT,
                    source TEXT,
                    attached_thread_parent_id TEXT
                );
                """
            )
            conn.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    tid,
                    str(rollout),
                    str(self.repo),
                    "Hub message card audit",
                    "Audited 8 card types",
                    "Audit message cards",
                    1795700000000,
                    1795765000000,
                    0,
                    "main",
                    "gpt-6-luna",
                    "vscode",
                    None,
                ),
            )
            conn.commit()

        if with_history:
            hdb = self.home / ".codex" / "thread_history_1.sqlite"
            with closing(sqlite3.connect(hdb)) as conn:
                conn.executescript(
                    """
                    CREATE TABLE thread_items(
                        thread_id TEXT,
                        turn_id TEXT,
                        item_id TEXT,
                        rollout_ordinal INTEGER,
                        created_at_ms INTEGER,
                        item_type TEXT,
                        item_json TEXT
                    );
                    """
                )
                items = [
                    (
                        tid,
                        "t1",
                        "i1",
                        1,
                        1795764000000,
                        "userMessage",
                        json.dumps(
                            {
                                "type": "userMessage",
                                "content": [{"type": "text", "text": "Analyze message cards"}],
                            }
                        ),
                    ),
                    (
                        tid,
                        "t1",
                        "i2",
                        2,
                        1795764100000,
                        "fileChange",
                        json.dumps(
                            {
                                "type": "fileChange",
                                "changes": [{"path": str(self.repo / "docs/cards.md")}],
                            }
                        ),
                    ),
                    (
                        tid,
                        "t1",
                        "i3",
                        3,
                        1795764200000,
                        "agentMessage",
                        json.dumps(
                            {
                                "type": "agentMessage",
                                "text": "Documented 8 card types in docs/cards.md",
                            }
                        ),
                    ),
                ]
                conn.executemany(
                    "INSERT INTO thread_items VALUES (?,?,?,?,?,?,?)", items
                )
                conn.commit()

            mdb = self.home / ".codex" / "memories_v2_1.sqlite"
            with closing(sqlite3.connect(mdb)) as conn:
                conn.executescript(
                    """
                    CREATE TABLE stage1_outputs(
                        thread_id TEXT,
                        rollout_summary TEXT,
                        raw_memory TEXT,
                        rollout_slug TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO stage1_outputs VALUES (?,?,?,?)",
                    (tid, "Native memory summary for Hub cards.", "", "hub_cards"),
                )
                conn.commit()

    def _seed_antigravity(self, cid="b666995d-6c50-407f-845e-9a5c0843b6e7"):
        base = self.home / ".gemini" / "antigravity"
        db = base / "conversation_summaries.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db)) as conn:
            conn.executescript(
                """
                CREATE TABLE conversation_summaries(
                    conversation_id TEXT,
                    title TEXT,
                    preview TEXT,
                    workspace_uris TEXT,
                    last_modified_time TEXT,
                    last_user_input_time TEXT,
                    parent_conversation_id TEXT,
                    step_count INTEGER
                );
                """
            )
            conn.execute(
                "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?,?)",
                (
                    cid,
                    "Mappo session handoff design",
                    "Explored cross-agent handoff",
                    json.dumps([self.repo.as_uri()]),
                    "2026-11-27T07:50:00Z",
                    "2026-11-27T07:49:00Z",
                    None,
                    12,
                ),
            )
            conn.execute(
                "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?,?)",
                (
                    "subagent-1111-2222-3333-444455556666",
                    "Subagent run",
                    "Hidden by default",
                    json.dumps([self.repo.as_uri()]),
                    "2026-11-27T07:55:00Z",
                    None,
                    cid,
                    3,
                ),
            )
            conn.commit()
        transcript = (
            base / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"
        )
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "USER_INPUT",
                            "created_at": "2026-11-27T07:49:00Z",
                            "content": (
                                "<USER_REQUEST>\nBuild mappo sessions\n</USER_REQUEST>\n"
                                "<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-27.\n</ADDITIONAL_METADATA>"
                            ),
                        }
                    ),
                    json.dumps(
                        {
                            "type": "PLANNER_RESPONSE",
                            "created_at": "2026-11-27T07:49:30Z",
                            "model": "gemini-4-neon",
                            "tool_calls": [{"name": "read_file"}],
                        }
                    ),
                    json.dumps(
                        {
                            "type": "PLANNER_RESPONSE",
                            "created_at": "2026-11-27T07:50:00Z",
                            "model": "gemini-4-neon",
                            "content": "Implemented read-only session handoff.",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.write(f".gemini/antigravity/brain/{cid}/plan.md", "# Plan\n")

    def _seed_cursor(self, cid="fe155621-a9ec-43f1-b26c-cc043384f9a1"):
        wid = "ws-cursor-01"
        self.write(
            SUPPORT / EDITORS["cursor"] / f"User/workspaceStorage/{wid}/workspace.json",
            json.dumps({"folder": self.repo.as_uri()}),
        )
        db = (
            self.home
            / SUPPORT
            / EDITORS["cursor"]
            / "User/globalStorage/state.vscdb"
        )
        db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db)) as conn:
            conn.executescript(
                """
                CREATE TABLE composerHeaders(
                    composerId TEXT,
                    workspaceId TEXT,
                    createdAt INTEGER,
                    lastUpdatedAt INTEGER,
                    isArchived INTEGER,
                    isSubagent INTEGER,
                    value TEXT
                );
                CREATE TABLE cursorDiskKV(key TEXT PRIMARY KEY, value TEXT);
                """
            )
            conn.execute(
                "INSERT INTO composerHeaders VALUES (?,?,?,?,?,?,?)",
                (
                    cid,
                    wid,
                    1795760000000,
                    1795764500000,
                    0,
                    0,
                    json.dumps(
                        {
                            "composerId": cid,
                            "name": "Cursor UI polish",
                            "subtitle": "Tweaked header spacing",
                            "unifiedMode": "agent",
                        }
                    ),
                ),
            )
            conn.commit()
        slug = re.sub(r"[^A-Za-z0-9]+", "-", str(self.repo).lstrip("/")).strip("-")
        tpath = (
            self.home
            / ".cursor"
            / "projects"
            / slug
            / "agent-transcripts"
            / cid
            / f"{cid}.jsonl"
        )
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "role": "user",
                            "message": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "<timestamp>Fri Nov 27</timestamp>\n<user_query>Tighten sidebar padding</user_query>",
                                    }
                                ]
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "role": "assistant",
                            "message": {
                                "content": [
                                    {"type": "text", "text": "Reduced sidebar padding to 12px."}
                                ]
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def _seed_codebuddy(
        self,
        cli_id="ba04b13b-0cba-4fbd-b893-b7626124e60a",
        ide_id="1de0098755d541e1bc6cb6d8cc9b8bd6",
    ):
        cli_jsonl = (
            self.home
            / ".codebuddy"
            / "projects"
            / "demo-app"
            / f"{cli_id}.jsonl"
        )
        cli_jsonl.parent.mkdir(parents=True, exist_ok=True)
        cli_jsonl.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "message",
                            "role": "user",
                            "cwd": str(self.repo),
                            "sessionId": cli_id,
                            "timestamp": "2026-11-27T06:00:00Z",
                            "content": [{"type": "text", "text": "Inspect build script"}],
                        }
                    ),
                    json.dumps(
                        {
                            "type": "message",
                            "role": "assistant",
                            "cwd": str(self.repo),
                            "sessionId": cli_id,
                            "timestamp": "2026-11-27T06:01:00Z",
                            "content": [{"type": "text", "text": "Verified zipapp build."}],
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        cb_support = self.home / SUPPORT / EDITORS["codebuddy"]
        vscdb = cb_support / "codebuddy-sessions.vscdb"
        vscdb.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(vscdb)) as conn:
            conn.execute("CREATE TABLE ItemTable(key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO ItemTable VALUES (?,?)",
                (
                    f"session:{ide_id}",
                    json.dumps(
                        {
                            "conversationId": ide_id,
                            "title": "CodeBuddy IDE refactor",
                            "cwd": str(self.repo),
                            "createdAt": 1795750000000,
                            "updatedAt": 1795762000000,
                            "status": "completed",
                        }
                    ),
                ),
            )
            conn.commit()
        self.write(
            SUPPORT
            / EDITORS["codebuddy"]
            / f"User/globalStorage/tencent-cloud.coding-copilot/edit-sessions/{ide_id}.json",
            json.dumps(
                {
                    "conversationId": ide_id,
                    "fileDiffs": {
                        str(self.repo / "src/app.ts"): {"content": "new", "oldContent": "old"}
                    },
                }
            ),
        )

    def test_parse_session_ref_variants(self):
        r1 = parse_session_ref("codex://threads/01a2170d-4a3f-7893-80a8-73f1ab793f8a")
        self.assertEqual((r1.agent, r1.session_id), ("codex", "01a2170d-4a3f-7893-80a8-73f1ab793f8a"))

        r2 = parse_session_ref(
            "cd '/Users/test/ftp-ai-dev' && codex resume 01a2170d-4a3f-7893-80a8-73f1ab793f8a"
        )
        self.assertEqual(r2.agent, "codex")
        self.assertEqual(r2.session_id, "01a2170d-4a3f-7893-80a8-73f1ab793f8a")
        self.assertEqual(r2.cwd_hint, "/Users/test/ftp-ai-dev")

        r3 = parse_session_ref("conversation://b666995d-6c50-407f-845e-9a5c0843b6e7")
        self.assertEqual((r3.agent, r3.session_id), ("antigravity", "b666995d-6c50-407f-845e-9a5c0843b6e7"))

        r4 = parse_session_ref("cursor:fe155621")
        self.assertEqual((r4.agent, r4.session_id), ("cursor", "fe155621"))

        r5 = parse_session_ref("mappo://session/codebuddy/ba04b13b")
        self.assertEqual((r5.agent, r5.session_id), ("codebuddy", "ba04b13b"))

        with self.assertRaises(ValueError):
            parse_session_ref("not a valid ref at all")

    def test_list_and_handoff_all_four_agents(self):
        self._seed_codex()
        self._seed_antigravity()
        self._seed_cursor()
        self._seed_codebuddy()

        rows = list_sessions(home=self.home, project_query="demo-app", limit=10)
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            {r["agent"] for r in rows},
            {"codex", "antigravity", "cursor", "codebuddy"},
        )

        # Codex handoff via pasted resume command
        codex_h, err = build_handoff(
            f"cd '{self.repo}' && codex resume 01a2170d-4a3f-7893-80a8-73f1ab793f8a",
            home=self.home,
            include_git=False,
        )
        self.assertIsNone(err)
        self.assertEqual(codex_h["agent"], "codex")
        self.assertEqual(codex_h["coverage"], "full")
        self.assertIn("Native memory summary", codex_h["summary"])
        self.assertEqual(len(codex_h["messages"]), 2)
        self.assertEqual(codex_h["changed_files"], [str(self.repo / "docs/cards.md")])
        md = render_handoff_markdown(codex_h)
        self.assertIn("# 跨 Agent 会话交接：Hub message card audit", md)
        self.assertIn("Native memory summary", md)

        # Antigravity handoff via conversation:// URI
        agy_h, _ = build_handoff(
            "conversation://b666995d-6c50-407f-845e-9a5c0843b6e7",
            home=self.home,
            include_git=False,
        )
        self.assertEqual(agy_h["agent"], "antigravity")
        self.assertEqual(agy_h["model"], "gemini-4-neon")
        self.assertEqual(agy_h["messages"][0]["text"], "Build mappo sessions")
        self.assertEqual(len(agy_h["artifacts"]), 1)

        # Cursor handoff via short ref
        cur_h, _ = build_handoff("cursor:fe155621", home=self.home, include_git=False)
        self.assertEqual(cur_h["agent"], "cursor")
        self.assertEqual(cur_h["messages"][0]["text"], "Tighten sidebar padding")
        self.assertEqual(cur_h["messages"][1]["text"], "Reduced sidebar padding to 12px.")

        # CodeBuddy CLI handoff (full) vs IDE handoff (meta_and_diffs)
        cb_cli, _ = build_handoff("codebuddy:ba04b13b", home=self.home, include_git=False)
        self.assertEqual(cb_cli["coverage"], "full")
        self.assertEqual(cb_cli["messages"][0]["text"], "Inspect build script")

        cb_ide, _ = build_handoff("1de0098755d541e1", home=self.home, include_git=False)
        self.assertEqual(cb_ide["coverage"], "meta_and_diffs")
        self.assertEqual(cb_ide["changed_files"], [str(self.repo / "src/app.ts")])
        self.assertIn("edit-sessions", cb_ide["limitations"])

    def test_codex_rollout_fallback_filters_noise(self):
        self._seed_codex(tid="01a29999-4a3f-7893-80a8-73f1ab793f8a", with_history=False)
        handoff, _ = build_handoff(
            "codex://threads/01a29999-4a3f-7893-80a8-73f1ab793f8a",
            home=self.home,
            include_git=False,
        )
        self.assertEqual(handoff["coverage"], "full")
        self.assertEqual(len(handoff["messages"]), 2)
        self.assertEqual(handoff["messages"][0]["text"], "Fix the login retry bug")

    def test_cli_sessions_and_handoff_e2e(self):
        self._seed_codex()
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, HOME=str(self.home), PYTHONPATH=str(root / "src"))
        res_list = subprocess.run(
            [sys.executable, "-m", "mappo", "sessions", "--json"],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        rows = json.loads(res_list.stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ref"], "codex:01a2170d")

        res_handoff = subprocess.run(
            [
                sys.executable,
                "-m",
                "mappo",
                "handoff",
                "codex://threads/01a2170d-4a3f-7893-80a8-73f1ab793f8a",
                "--no-git",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        self.assertIn("Hub message card audit", res_handoff.stdout)
        self.assertIn("Documented 8 card types", res_handoff.stdout)

        # Ensure resolve_session returns empty list when missing
        found, candidates = resolve_session("deadbeef1234", home=self.home)
        self.assertIsNone(found)
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
