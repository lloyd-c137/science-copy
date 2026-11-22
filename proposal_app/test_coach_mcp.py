import json
import os
from pathlib import Path
from queue import Queue
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from proposal_app import coach_mcp as mcp, server, skill_distribution


class CodexTestClient:
    """Drive the installed Codex client with an isolated home and no model turn."""

    def __init__(self, home):
        config = (f"[mcp_servers.proposal_coach]\ncommand = {json.dumps(sys.executable)}\n"
                  f"args = [{json.dumps(str(Path(mcp.__file__).resolve()))}]\n"
                  f"[mcp_servers.proposal_coach.env]\nPROPOSAL_CLIENT_DIR = {json.dumps(str(mcp.client_dir()))}\n")
        config_dir = Path(home) / "codex"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(config, encoding="utf-8")
        binary = shutil.which("codex.cmd" if os.name == "nt" else "codex")
        self.proc = subprocess.Popen([binary, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     env={**os.environ, "CODEX_HOME": str(config_dir)})
        self.replies = Queue()
        self.reader = Thread(target=self.read_replies, daemon=True)
        self.reader.start()
        self.seq = 0

    def read_replies(self):
        for line in self.proc.stdout:
            self.replies.put(json.loads(line))

    def send(self, method, params, notify=False):
        self.seq += 1
        message = {"method": method, "params": params}
        if not notify:
            message["id"] = self.seq
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if notify:
            return
        while True:
            msg = self.replies.get(timeout=18)
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise AssertionError(msg["error"])
                return msg["result"]

    def call(self, thread, tool, args):
        result = self.send("mcpServer/tool/call", {"server": "proposal_coach", "threadId": thread,
                                                   "tool": tool, "arguments": args})
        if result.get("isError"):
            raise AssertionError(result["content"])
        return result["content"][0]["text"]

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=4)
        self.reader.join(timeout=2)
        self.proc.stdout.close()


class TeachingToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, PROPOSAL_CLIENT_DIR=self.tmp.name)
        env.start()
        self.addCleanup(env.stop)
        with patch.object(skill_distribution, 'build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = skill_distribution.bundle()
            skill = skill_distribution.install(self.tmp.name, 'http://localhost:8765')
        skill_env = patch.dict(os.environ, PROPOSAL_SKILL_DIR=str(skill))
        skill_env.start()
        self.addCleanup(skill_env.stop)
        lessons = patch.dict(mcp.LESSONS, {'coach':skill/'SKILL.md', 'yau':skill/'references/yau-review.md', 'yau_examples':skill/'references/yau-awarded-papers.md'})
        lessons.start()
        self.addCleanup(lessons.stop)
        self.client = mcp.Client(mcp.DEFAULT_SERVER, "token", "student")

    def test_relaunch_recovers_ambiguous_write_without_losing_identity_or_version(self):
        original = {"request_id": "work-1", "version": 4, "requirement_version": 1,
                    "confirmed": True, "data": {"reason": "我想知道哪条路线更准时"}}
        path = "/api/projects/1/progress"
        with patch.object(self.client, "request", side_effect=mcp.Offline("断开")):
            with self.assertRaisesRegex(mcp.ToolError, "work-1"):
                self.client.write(path, original)
        other = mcp.Client(mcp.DEFAULT_SERVER, "different token", "student2")
        self.assertEqual(other.pending(), [])
        with self.assertRaises(mcp.ToolError):
            other.retry("work-1")
        recovered = mcp.Client(mcp.DEFAULT_SERVER, "renewed student token", "student")
        self.assertEqual(recovered.pending()[0]["request_id"], "work-1")
        with self.assertRaisesRegex(mcp.ToolError, "另一份小结"):
            recovered.write(path, {**original, "version": 5})
        with patch.object(recovered, "request", return_value={"result_id": "R9"}) as send:
            self.assertEqual(recovered.retry("work-1"), {"result_id": "R9"})
            send.assert_called_once_with(path, original)
        self.assertEqual(recovered.pending(), [])

    def test_unconfirmed_write_and_cross_project_file_are_blocked_before_transfer(self):
        args = {"request_id": "n", "project_id": "P", "step": 2, "complete": True, "workflow_version": "tanyue-v1",
                "version": 1, "requirement_version": 1, "confirmed": False, "data": {}}
        with patch.object(mcp.Client, "load", return_value=self.client):
            with self.assertRaisesRegex(mcp.ToolError, "导师只能保存草稿"):
                mcp.run_tool("proposal_submit", args)
            with patch.object(self.client, "request", return_value={"files": []}) as read:
                with self.assertRaisesRegex(mcp.ToolError, "材料编号"):
                    mcp.run_tool("proposal_open_material", {"project_id": "P", "file_id": "another"})
                read.assert_called_once_with("/api/projects/P")

    def test_read_skill_and_initialize_with_utf8(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18"}}
        self.assertEqual(mcp.dispatch(request)["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("高中生科研开题辅导", mcp.run_tool("proposal_guide", {}))

    def test_student_upload_submit_reconnect_and_other_student_isolation(self):
        with server.serve(Path(self.tmp.name) / "service.sqlite", 0) as api:
            worker = Thread(target=api.serve_forever, daemon=True)
            worker.start()
            try:
                origin = f"http://127.0.0.1:{api.server_port}"
                with patch("getpass.getpass", return_value="yanjiu123"):
                    mcp.connect(origin, "student")
                pid = mcp.run_tool("proposal_list_projects", {})["projects"][0]["id"]
                project = {"project_id": pid}
                card = mcp.run_tool("proposal_read_project", project)
                args = {**project, "step": 1, "complete": False, "confirmed": False, "workflow_version": card["workflow_version"],
                        "data": {"summary": "我骑车上学时常卡在第二个红灯。"},
                        "request_id": "draft-01", "version": card["version"],
                        "requirement_version": card["activity"]["version"]}
                saved = mcp.run_tool("proposal_submit", args)
                self.assertNotIn('steps', saved)
                self.assertFalse(mcp.Client.load().request('/api/projects/' + pid)['steps'][0]['confirmed'])
                replay = mcp.run_tool("proposal_submit", args)
                self.assertEqual(saved["result_id"], replay["result_id"])
                self.assertEqual(saved["version"], replay["version"])
                material = Path(self.tmp.name) / "现场记录.csv"
                material.write_text("时刻,用时\n07:00,20\n", encoding="utf-8")
                uploaded = mcp.run_tool("proposal_upload", {**project, "path": str(material.resolve()),
                                                            "request_id": "upload-01"})
                file_id = uploaded["file"]["id"]
                local = mcp.run_tool("proposal_open_material", {**project, "file_id": file_id})
                self.assertEqual(Path(local["path"]).read_bytes(), material.read_bytes())
                with patch("getpass.getpass", return_value="yanjiu123"):
                    mcp.connect(origin, "student2")
                with self.assertRaises(mcp.ToolError):
                    mcp.run_tool("proposal_read_project", project)
            finally:
                api.shutdown()
                worker.join()

    @unittest.skipUnless(shutil.which("codex.cmd" if os.name == "nt" else "codex"), "Codex CLI 未安装")
    def test_codex_client_can_read_and_write_student_project(self):
        with server.serve(Path(self.tmp.name) / "codex-service.sqlite", 0) as api:
            worker = Thread(target=api.serve_forever, daemon=True)
            worker.start()
            codex = CodexTestClient(self.tmp.name)
            try:
                with patch("getpass.getpass", return_value="yanjiu123"):
                    mcp.connect(f"http://127.0.0.1:{api.server_port}", "student")
                codex.send("initialize", {"clientInfo": {"name": "coach_qa", "version": "1"},
                                          "capabilities": {"experimentalApi": True}})
                codex.send("initialized", {}, notify=True)
                inventory = codex.send("mcpServerStatus/list", {})["data"]
                self.assertEqual(set(inventory[0]["tools"]), set(mcp.SCHEMAS))
                thread = codex.send("thread/start", {"ephemeral": True, "approvalPolicy": "never",
                                                     "sandbox": "read-only"})["thread"]["id"]
                self.assertIn("research-proposal-coach", codex.call(thread, "proposal_guide", {}))
                home = json.loads(codex.call(thread, "proposal_list_projects", {}))
                self.assertEqual(home["user"]["username"], "student")
                pid = home["projects"][0]["id"]
                card = json.loads(codex.call(thread, "proposal_read_project", {"project_id": pid}))
                progress = {"project_id": pid, "step": 1, "complete": False, "confirmed": False, "workflow_version": card["workflow_version"],
                            "request_id": "codex-write", "version": card["version"],
                            "requirement_version": card["activity"]["version"],
                            "data": {"summary": "这周走近路迟到了两次。"}}
                saved = json.loads(codex.call(thread, "proposal_submit", progress))
                self.assertTrue(saved["result_id"])
                self.assertNotIn('steps', saved)
                self.assertEqual(mcp.Client.load().request('/api/projects/' + pid)['steps'][0]['data']['summary'], progress['data']['summary'])
            finally:
                codex.close()
                api.shutdown()
                worker.join()


if __name__ == "__main__":
    unittest.main()
