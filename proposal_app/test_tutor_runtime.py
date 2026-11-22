import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch
import uuid

from proposal_app import tutor_runtime as rt, tutor_environment as env, coach_mcp as mcp
from proposal_app.workspace_store import atomic_json
from proposal_app.project_archive import ProjectArchive


class TutorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        atomic_json(self.root/'.coach/identity.json', {'project':'P1','user':'U1'})
        skill = self.root/'.agents/skills/research-proposal-coach/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('保留取舍原文，导师不能代确认。', 'utf-8')
        self.packet = {'project_id':'P1','version':1,'current_step':1,'status':'active',
                       'steps':[{'cycle':1} for _ in range(6)], 'index':'INDEX.md',
                       'continuity':{'decision':'拒绝路线B，因为不能取得必要材料。'}, 'coverage':{'uncovered_count':0}}
        self.client = Mock()
        self.client.origin = 'http://127.0.0.1:8767'
        self.client.request.side_effect = lambda *a: json.loads(json.dumps(self.packet))
        self.event = {'cwd':str(self.root),'session_id':str(uuid.uuid4()),'hook_event_name':'UserPromptSubmit'}

    def delivered(self, text):
        p = self.root/'transcript.jsonl'
        with p.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'type':'response_item','payload':{'role':'developer','content':[{'text':text}]}},ensure_ascii=False)+'\n')
        self.event['transcript_path'] = str(p)

    def test_new_thread_persistent_binding_and_unchanged_context(self):
        first = rt.hook(self.event, self.client)
        self.delivered(first)
        binding = rt.recover(self.root, self.event['session_id'])
        self.assertIn('拒绝路线B', first)
        second = rt.hook(self.event, self.client)
        self.assertIn('未变化', second)
        self.assertNotIn('拒绝路线B', second)
        self.assertEqual(binding['token'], rt.recover(self.root, self.event['session_id'])['token'])
        records = list(ProjectArchive(self.root).registered(self.root/'.coach'))
        self.assertEqual(records[0]['thread_id'], self.event['session_id'])

    def test_cancelled_delivery_does_not_suppress_context(self):
        rt.hook(self.event, self.client)
        self.assertIn('拒绝路线B',rt.hook(self.event,self.client))

    def test_session_resume_refreshes_context_without_duplicate_guide(self):
        self.delivered(rt.hook(self.event, self.client))
        self.packet['coverage']['uncovered_count'] = 1
        resumed = rt.hook(dict(self.event, hook_event_name='SessionStart', source='resume'), self.client)
        self.assertIn('接续包增量', resumed)
        self.assertNotIn('辅导规则（本轮已加载', resumed)
        self.delivered(resumed)
        self.assertIn('未变化', rt.hook(self.event, self.client))

    def test_discussion_change_without_card_version_and_compaction(self):
        self.delivered(rt.hook(self.event, self.client))
        self.packet['coverage']['uncovered_count'] = 1
        delta=rt.hook(self.event,self.client)
        self.assertIn('接续包增量',delta)
        self.assertNotIn('拒绝路线B',delta)
        compact=rt.hook(dict(self.event,hook_event_name='SessionStart',source='compact'),self.client)
        self.assertIn('辅导规则',compact)
        self.assertIn('拒绝路线B',compact)

    def test_old_stage_never_adopts_new_stage(self):
        rt.hook(self.event, self.client)
        self.packet['current_step'] = 2
        self.assertIn('阶段已结束', rt.hook(self.event, self.client))
        self.assertEqual(rt.recover(self.root,self.event['session_id'])['step'],1)
        other = dict(self.event,session_id=str(uuid.uuid4()))
        rt.hook(other,self.client)
        self.assertEqual(rt.recover(self.root,other['session_id'])['step'],2)

    def test_unregistered_old_chat_fails_closed(self):
        transcript=self.root/'old.jsonl'
        transcript.write_text(json.dumps({'type':'event_msg','payload':{'type':'task_complete'}}))
        text=rt.hook(dict(self.event,transcript_path=str(transcript)),self.client)
        self.assertIn('旧聊天尚未登记',text)
        self.assertIsNone(rt.recover(self.root,self.event['session_id']))

    def test_mcp_unchanged_and_changed_coverage(self):
        with patch.object(mcp.Client,'load',return_value=self.client), patch.dict(os.environ,{'PROPOSAL_PROJECT_ID':'P1','PROPOSAL_STAGE_SESSIONS':''}):
            args={'project_id':'P1','known_hash':rt.fingerprint(self.packet)}
            self.assertTrue(mcp.run_tool('proposal_read_project',args)['unchanged'])
            self.packet['coverage']['uncovered_count']=2
            self.assertNotIn('unchanged',mcp.run_tool('proposal_read_project',args))

    def test_profile_is_local_and_parses_without_global_mutation(self):
        home=self.root/'home'
        config=home/'.codex/config.toml';config.parent.mkdir(parents=True)
        original='[mcp_servers.unrelated]\ncommand="abc"\n[plugins."design@test"]\nenabled=true\n'
        config.write_text(original)
        unrelated=home/'.agents/skills/unrelated/SKILL.md'
        unrelated.parent.mkdir(parents=True);unrelated.write_text('unrelated')
        parsed=tomllib.loads(env.profile(self.root,home))
        self.assertFalse(parsed['mcp_servers']['unrelated']['enabled'])
        self.assertFalse(parsed['plugins']['design@test']['enabled'])
        self.assertFalse(parsed['skills']['include_instructions'])
        self.assertIn('UserPromptSubmit',parsed['hooks'])
        self.assertEqual(config.read_text(),original)
        self.assertEqual(unrelated.read_text(),'unrelated')

    def test_guide_hash_avoids_duplicate_body(self):
        p=self.root/'.agents/skills/research-proposal-coach/SKILL.md'
        with patch.dict(mcp.LESSONS,{'coach':p}):
            value=mcp.run_tool('proposal_guide',{'known_hash':rt.fingerprint(p.read_text('utf-8'))})
            self.assertTrue(value['unchanged'])


if __name__=='__main__': unittest.main()
