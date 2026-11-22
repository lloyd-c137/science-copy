"""User-facing continuity scenarios through the real bounded packet and hook."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from proposal_app import context_archive as ctx, tutor_runtime as rt
from proposal_app.workspace_store import atomic_json
from proposal_app.configure_tutor_folder import configure

class Scenarios(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        atomic_json(self.root/'.coach/identity.json',{'project':'P1'})
        skill=self.root/'.agents/skills/research-proposal-coach/SKILL.md'
        skill.parent.mkdir(parents=True);skill.write_text('按原文接续，不能代确认。','utf-8')
        self.card={'id':'P1','version':1,'status':'active','current_step':1,'activity':{'version':1},
            'steps':[{'number':i,'cycle':1} for i in range(1,7)],'comments':[],
            'research':{'objects':[{'id':'O1','kind':'rq','status':'draft','revision':1,
                'content':{'population_or_object':'所有高中生','question':'如何学习手语？'}}]},'quality':{'records':[]}}
        self.archive={'conversations':[]};self.notes=ctx.load_notes(self.root)
        self.client=Mock();self.client.request.side_effect=lambda *args:self.packet()
        self.event={'cwd':str(self.root),'session_id':str(uuid.uuid4()),'hook_event_name':'UserPromptSubmit'}
        self.deliver(rt.hook(self.event,self.client))

    def packet(self):
        paths=ctx.export(self.root,self.card,self.archive,self.notes)
        packet=ctx.packet(self.card,self.archive,self.notes,paths)
        self.assertLessEqual(len(ctx.encode(packet)),10000)
        return packet

    def deliver(self,text):
        path=self.root/'transcript.jsonl'
        with path.open('a',encoding='utf-8') as f:
            f.write(json.dumps({'type':'response_item','payload':{'role':'developer','content':[{'text':text}]}},ensure_ascii=False)+'\n')
        self.event['transcript_path']=str(path)

    def test_web_scope_change_replaces_current_result(self):
        self.card['research']['objects'][0]['content']['population_or_object']='本校高一学生'
        self.card['research']['objects'][0]['revision']=2;self.card['version']=2
        text=rt.hook(self.event,self.client)
        self.assertIn('本校高一学生',text);self.assertNotIn('所有高中生',text)
        self.assertIn('接续包增量',text)

    def test_web_choice_includes_original_reason_without_chat_summary(self):
        self.card['quality']['records']=[{'id':'Q1','kind':'proposal','step':1,'status':'rejected',
            'text':'使用数据手套','decision_reason':'没有设备，保留摄像头方案','decided_at':'2026-11-19'}]
        self.card['version']=2
        text=rt.hook(self.event,self.client)
        self.assertIn('没有设备，保留摄像头方案',text);self.assertIn('rejected',text)

    def test_teacher_instruction_included_and_long_comment_requires_original(self):
        self.card['comments']=[{'id':'C1','step':1,'role':'teacher','created':'2026-11-19',
            'text':'先做小样本可行性验证，不要直接开展大规模实验'}]
        self.card['version']=2
        self.assertIn('先做小样本可行性验证',rt.hook(self.event,self.client))
        self.card['comments'][0]['text']='必须保留的教师依据。'*500
        packet=self.packet();row=packet['website_updates']['items'][0]
        self.assertTrue(row['needs_read'])
        self.assertIn(row['path'],[r['path'] for r in packet['read_first']['items']])
        self.assertEqual(json.loads((self.root/row['path']).read_text('utf-8'))['text'],self.card['comments'][0]['text'])

    def test_stage_advance_preserves_old_binding_and_directs_to_website(self):
        old=rt.recover(self.root,self.event['session_id'])
        self.card['current_step']=2
        text=rt.hook(self.event,self.client)
        self.assertIn('阶段已结束',text);self.assertIn('回网站',text)
        self.assertEqual(rt.recover(self.root,self.event['session_id'])['token'],old['token'])
        self.assertEqual(rt.recover(self.root,self.event['session_id'])['step'],1)

    def test_unchanged_does_not_reload_skill_or_packet(self):
        text=rt.hook(self.event,self.client)
        self.assertIn('未变化',text);self.assertNotIn('如何学习手语',text)
        self.assertNotIn('按原文接续，不能代确认。',text)

    def test_mac_command_quotes_spaces_and_single_quote(self):
        root=self.root/"科研 O'Brien";root.mkdir()
        import shlex
        with patch('proposal_app.configure_tutor_folder.sys.platform','darwin'),patch('proposal_app.configure_tutor_folder.sys.executable','/Applications/Python Tools/python3'):
            configure(root)
        conf=json.loads((root/'.codex/hooks.json').read_text('utf-8'))
        parts=shlex.split(conf['hooks']['SessionStart'][0]['hooks'][0]['command'])
        self.assertEqual(parts[0],'/Applications/Python Tools/python3')
        self.assertEqual(parts[-1],str(root/'.tanyue-coach/runtime/folder_hook.py'))

if __name__=='__main__':unittest.main()
