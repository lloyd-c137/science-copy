import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proposal_app import server, coach_mcp
from proposal_app.project_archive import ProjectArchive, visible_messages, atomic_json
from proposal_app.coach_launcher import CoachLauncher


class Stages(unittest.TestCase):
    def card(self):
        card = server.make_card("P1", "A1", "U1", "学生")
        card["activity"] = {"version": 1}
        return card

    def test_future_draft_is_not_completion_and_cannot_overwrite_current_action(self):
        card = self.card()
        user = {"role": "student", "id":"U1"}
        body = {"workflow_version":"tanyue-v1", "step": 4, "data": {"scope": "比较两种条件"}, "complete": False, "confirmed": True, "next_action": "跳到小试"}
        server.save_progress(card, body, user)
        self.assertEqual(card["current_step"], 1)
        self.assertEqual(card["steps"][3]["data"]["scope"], "比较两种条件")
        self.assertEqual(card["steps"][3]["status"], "pending")
        self.assertNotEqual(card["next_action"], "跳到小试")
        with self.assertRaises(server.Problem):
            server.save_progress(card, dict(body, complete=True), user)
        # Synthetic confirmed objects isolate navigation without bypassing its checks.
        card['research']={'objects':[dict(id='C',kind='curiosity',status='confirmed',revision=1,content={'observation':'合成观察','student_quote_ref':'M'}),dict(id='Q',kind='question',status='confirmed',revision=1,content={'wording':'合成问题'})]}
        data = {field["key"]: "学生确认的依据" for field in card["steps"][0]["fields"]}
        data['summary']='选定了一项可比较的问题'
        server.save_progress(card, {"workflow_version":"tanyue-v1","step":1,"data":data,"complete":True,"confirmed":True}, user)
        self.assertEqual(card["current_step"],2)
        self.assertEqual(card["milestone"]["summary"],"选定了一项可比较的问题")
        self.assertEqual(card["steps"][3]["data"]["scope"],"比较两种条件")

    def test_old_chat_cannot_complete_new_stage(self):
        card=self.card(); card["current_step"]=2
        args={"workflow_version":"tanyue-v1","project_id":"P1","step":2,"data":{},"complete":True,"confirmed":True,"version":1,"requirement_version":1,"request_id":"one"}
        with patch.dict("os.environ",{"PROPOSAL_STAGE":"1"}), patch.object(coach_mcp.Client,"load") as load:
            load.return_value.request.return_value=card
            load.return_value.origin="http://127.0.0.1:8765"
            with self.assertRaisesRegex(coach_mcp.ToolError,"阶段已经结束|导师只能保存草稿"):
                coach_mcp.run_tool("proposal_submit",args)
            load.return_value.write.assert_not_called()

    def test_stage_workspace_and_reopen_cycle(self):
        with tempfile.TemporaryDirectory() as root:
            launcher=CoachLauncher(root,open_desktop=False)
            card=self.card()
            first=launcher.stage_workspace("U1",card)
            card["current_step"]=2
            self.assertNotEqual(first,launcher.stage_workspace("U1",card))
            server.reopen(card,1)
            self.assertNotEqual(first,launcher.stage_workspace("U1",card))

    def test_materials_context_and_local_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            archive=ProjectArchive(Path(root)/'projects',Path(root)/'sessions')
            card=self.card()
            paper={'title':'论文甲','source':'https://example.org/a','finding':'提供比较方法','limit':'不同场景不能直接外推'}
            card['steps'][1]['data']={'papers':[paper]}
            first=archive.enrich(card)
            self.assertEqual(first['materials'][0]['help'],'提供比较方法')
            self.assertEqual(len(first['reading_items']['files']),1)
            archive.source(card,{'title':'论文甲','url':paper['source'],'help':'补充实际测量方法','limit':'尚需验证','request_id':'source-1'})
            second=archive.enrich(card)
            self.assertEqual(len(second['materials']),1)
            self.assertNotEqual(first['reading_items']['files'],second['reading_items']['files'])
            archive.export(card)
            saved=json.loads((archive.folder(card)/'project.json').read_text('utf-8'))
            self.assertEqual(saved['materials'][0]['help'],'补充实际测量方法')
            self.assertIn('补充实际测量方法',(archive.folder(card)/'交接手记.md').read_text('utf-8'))
            other=self.card();other['id']='P2'
            self.assertEqual(archive.enrich(other)['materials'],[])
            with self.assertRaises(ValueError):
                archive.source(card,{'title':'危险地址','url':'javascript:alert(1)','help':'无','limit':'无'})

    def test_archive_filters_context_reasoning_and_unregistered_chats(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); sessions=root/"sessions"; sessions.mkdir()
            tid="11111111-1111-4111-8111-111111111111"
            rows=[
                {"type":"response_item","payload":{"type":"message","id":"ctx","role":"user","internal_chat_message_metadata_passthrough":{},"content":[{"type":"input_text","text":"# AGENTS.md instructions secret"}]}},
                {"type":"response_item","payload":{"type":"message","id":"ctx2","role":"user","internal_chat_message_metadata_passthrough":{"id":"context"},"content":[{"type":"input_text","text":"# AGENTS.md instructions with metadata"}]}},
                {"type":"response_item","payload":{"type":"reasoning","text":"private"}},
                {"type":"response_item","payload":{"type":"message","id":"u1","role":"user","content":[{"type":"input_text","text":"我想比较两种解释"}]}},
                {"type":"response_item","payload":{"type":"message","id":"a1","role":"assistant","phase":"final_answer","content":[{"type":"output_text","text":"可以，请先预测"}]}},
                {"type":"response_item","payload":{"type":"message","id":"internal","role":"assistant","phase":"analysis","content":[{"type":"output_text","text":"private"}]}}
            ]
            source=sessions/f"rollout-{tid}.jsonl"
            source.write_text("\n".join(json.dumps(row) for row in rows)+"\n{",encoding="utf-8")
            archive=ProjectArchive(root/"projects",sessions)
            card=self.card(); folder=archive.folder(card)
            atomic_json(folder/"stages/1-1/conversation.json",{"thread_id":tid,"step":1,"title":"选题"})
            result=archive.read(card,force=True)
            self.assertEqual([m["id"] for m in result["conversations"][0]["messages"]],["u1","a1"])
            body={"dimension":"提出问题","observation":"主动提出比较","evidence_id":"u1","next_action":"说出比较判据","request_id":"r1"}
            archive.reflect(card,body); archive.reflect(card,body)
            self.assertEqual(len(archive.read(card)["feedback"]),1)
            with self.assertRaises(ValueError): archive.reflect(card,dict(body,evidence_id="a1"))
            other=self.card();other["id"]="P2"
            self.assertEqual(archive.read(other)["conversations"],[])


if __name__ == "__main__": unittest.main()
