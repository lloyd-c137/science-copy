import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proposal_app import context_archive as ctx, coach_mcp as mcp, project_files


class ContextTests(unittest.TestCase):
    def test_save_deliverable_receipt_identifies_the_fixed_draft(self):
        client = mcp.Client('http://127.0.0.1:8767')
        selected = {'id': 'PV1', 'revision': 2}
        self.card['result_id'] = 'operation-R1'
        self.card['research'].update(selected_deliverable=selected,
                                     deliverables=[dict(selected, sequence=3, chapters={'method': '正文'})])
        with patch.dict(os.environ, {'PROPOSAL_CLIENT_DIR': str(self.root)}), \
             patch.object(client, 'request', return_value=self.card):
            response = client.write('/api/projects/P/research-deliverable', {'request_id': 'new-draft'})
        self.assertEqual(response['deliverable_ref'], dict(selected, sequence=3))
        self.assertEqual(response['result_id'], 'operation-R1')
        self.assertNotIn('research', response)

    def test_direct_reads_are_evidence_links_not_new_coverage(self):
        self.card['quality']['records'].append({'id': 'S1', 'kind': 'support', 'step': 2, 'strategy': '逐句共读'})
        self.archive['conversations'][0]['messages'].append({'id': 'M3', 'role': 'user', 'text': '最新的问题'})
        before = ctx.encode(self.notes)
        paths = ctx.export(self.root, self.card, self.archive, self.notes)
        packet = ctx.packet(self.card, self.archive, self.notes, paths)
        reads = packet['read_first']['items']
        selected = {r['path'] for r in reads}
        supplied = {m['id']:m['text'] for m in packet['recent_messages']['items']}
        self.assertEqual(supplied['M3'], '最新的问题')
        self.assertEqual(supplied['M1'], self.archive['conversations'][0]['messages'][0]['text'])
        self.assertNotIn(paths['catalog']['message/M3'], selected)
        self.assertNotIn(paths['catalog']['message/M1'], selected)
        self.assertIn(paths['catalog']['quality.records/1'], selected)
        self.assertEqual(before, ctx.encode(self.notes))
        self.assertEqual(packet['coverage']['uncovered_count'], 1)
        self.assertLessEqual(len(ctx.encode(packet)), 10000)
        for row in reads:
            self.assertTrue((self.root / row['path']).is_file())

    def test_long_uncovered_message_still_requires_original(self):
        self.archive['conversations'][0]['messages'].append({'id':'LONG','role':'user','text':'不可遗漏的取舍理由。'*400})
        paths=ctx.export(self.root,self.card,self.archive,self.notes)
        packet=ctx.packet(self.card,self.archive,self.notes,paths)
        self.assertIn(paths['catalog']['message/LONG'],{r['path'] for r in packet['read_first']['items']})
        self.assertNotIn('LONG',{m['id'] for m in packet['recent_messages']['items']})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.card = {'id': 'P', 'version': 2, 'current_step': 2, 'status': 'active', 'activity': {'version': 1},
                     'steps': [{'number': 1, 'cycle': 1}, {'number': 2, 'cycle': 1}],
                     'research': {'objects': [{'id': 'O1', 'content': {'text': '成果原文' * 3000}}],
                                  'revisions': [{'id': 'O1', 'text': '旧版不能丢'}]},
                     'quality': {'records': [{'id': 'Q1', 'reason': '放弃简单路线，因为不能评价多轮访谈'}]}}
        self.archive = {'conversations': [{'thread_id': 'T', 'step': 2, 'messages': [
            {'id': 'M1', 'role': 'user', 'text': '选择多轮访谈，因为需要主动获取信息。'},
            {'id': 'M2', 'role': 'assistant', 'text': 'AI反馈正确不能证明训练有效。'}]}]}
        self.body = {'request_id': 'r1', 'revision': 0, 'project_version': 2, 'coverage': {'T': 'M2'}, 'entries': [
            {'kind': 'decision', 'text': '学生选择多轮访谈以训练主动获取信息，训练效果仍待验证。',
             'sources': [{'message_id': 'M1', 'quote': '因为需要主动获取信息'}, {'message_id': 'M2', 'quote': 'AI反馈正确不能证明训练有效'}]}]}
        self.notes = ctx.update_notes(ctx.load_notes(self.root), self.body, self.archive, self.card)

    def test_lossless_individual_sources_and_paging(self):
        paths = ctx.export(self.root, self.card, self.archive, self.notes)
        for key, value in [('research.objects/0', self.card['research']['objects'][0]),
                           ('research.revisions/0', self.card['research']['revisions'][0]),
                           ('quality.records/0', self.card['quality']['records'][0])]:
            path = paths['catalog'][key]
            pieces = []
            offset = 0
            while True:
                part = project_files.read(self.root, path, offset, 1000)
                pieces.append(part['text'])
                if part['next_offset'] is None:
                    break
                offset = part['next_offset']
            self.assertEqual(json.loads(''.join(pieces)), value)
        raw = json.loads((self.root / paths['catalog']['message/M1']).read_text('utf8'))
        self.assertEqual(raw['text'], self.archive['conversations'][0]['messages'][0]['text'])
        self.assertNotIn('成果原文', (self.root / paths['index']).read_text('utf8'))
        before = paths['catalog']['research.objects/0']
        self.card['research']['objects'][0]['content']['text'] = '新版'
        later = ctx.export(self.root, self.card, self.archive, self.notes)
        self.assertNotEqual(before, later['catalog']['research.objects/0'])
        self.assertIn('成果原文', (self.root / before).read_text('utf8'))

    def test_bound_and_critical_decision_with_large_history(self):
        self.card['quality']['records'] *= 1000
        self.card['research']['revisions'] *= 1000
        self.archive['conversations'][0]['messages'].append({'id': 'M3', 'role': 'user', 'text': '长消息' * 20000})
        value = ctx.packet(self.card, self.archive, self.notes)
        self.assertLessEqual(len(ctx.encode(value)), 10000)
        self.assertIn('主动获取信息', ctx.encode(value))
        self.assertEqual(value['coverage']['uncovered_count'], 1)
        self.assertEqual(value['coverage']['first_uncovered'], 'M3')
        self.assertNotIn('quality', value)
        self.assertEqual(value['current_results']['omitted'], 1)

    def test_sources_and_stale_updates_rejected_and_history_retained(self):
        bad = json.loads(ctx.encode(self.body)); bad['entries'][0]['sources'][0]['quote'] = '不存在的原话'
        with self.assertRaises(ValueError): ctx.update_notes(ctx.load_notes(self.root), bad, self.archive, self.card)
        bad['entries'][0]['sources'][0] = {'message_id': 'OTHER_PROJECT', 'quote': '原话'}
        with self.assertRaises(ValueError): ctx.update_notes(ctx.load_notes(self.root), bad, self.archive, self.card)
        self.assertEqual(ctx.update_notes(self.notes, self.body, self.archive, self.card), self.notes)
        changed = dict(self.body, request_id='r2')
        with self.assertRaises(ValueError): ctx.update_notes(self.notes, changed, self.archive, self.card)
        changed['revision'] = 1
        changed['entries'] = [dict(self.body['entries'][0], supersedes=[self.notes['entries'][0]['id']])]
        updated = ctx.update_notes(self.notes, changed, self.archive, self.card)
        self.assertEqual(len(updated['entries']), 2)
        self.assertEqual(len(ctx.active_notes(updated)), 1)
        self.archive['conversations'][0]['messages'][0]['text'] += ' 更正'
        self.assertEqual(ctx.packet(self.card, self.archive, self.notes)['coverage']['uncovered_count'], 1)

    def test_default_mcp_read_and_receipts_do_not_expand_archive(self):
        client = mcp.Client('http://127.0.0.1:8767')
        packet = ctx.packet(self.card, self.archive, self.notes)
        with patch.dict(os.environ, {}, clear=True), patch.object(mcp.Client, 'load', return_value=client), patch.object(client, 'request', return_value=packet) as read:
            value = mcp.run_tool('proposal_read_project', {'project_id': 'P'})
            read.assert_called_once_with('/api/projects/P/context')
            self.assertLessEqual(len(mcp.encode(value)), 10000)
        self.card['result_id'] = 'R1'
        compact = ctx.receipt(self.card)
        self.assertEqual(compact['result_id'], 'R1')
        self.assertNotIn('research', compact)
        self.assertNotIn('quality', compact)

    def test_discussion_query_is_bounded_and_locatable(self):
        self.archive['conversations'][0]['messages'] *= 20
        client = mcp.Client('http://127.0.0.1:8767')
        with patch.dict(os.environ, {}, clear=True), patch.object(mcp.Client, 'load', return_value=client), patch.object(client, 'request', return_value=self.archive):
            page = mcp.run_tool('proposal_discussions', {'project_id': 'P', 'query': '访谈'})
            self.assertLess(len(mcp.encode(page)), 10000)
            self.assertIsNotNone(page['next_offset'])
            self.assertTrue(all(m['id'] == 'M1' for m in page['messages']))

    def test_unknown_student_index_not_overwritten(self):
        path = self.root / ctx.PREFIX / 'INDEX.md'
        path.parent.mkdir(parents=True)
        path.write_text('学生自己写的', 'utf8')
        exported = ctx.export(self.root, self.card, self.archive, self.notes)
        self.assertEqual(path.read_text('utf8'), '学生自己写的')
        self.assertNotEqual(exported['index'], ctx.PREFIX + '/INDEX.md')


class ContextHTTPTests(unittest.TestCase):
    from proposal_app.test_service import ServiceFlow
    setUp = ServiceFlow.setUp
    api = ServiceFlow.api
    login = ServiceFlow.login

    def test_teacher_web_comment_immediately_enters_context(self):
        before=self.api(self.path+'/context',self.student)
        self.api(self.path+'/comments',self.teacher,{'text':'先做小样本验证，不开展大规模实验','step':1})
        after=self.api(self.path+'/context',self.student)
        self.assertNotEqual(ctx.digest(before),ctx.digest(after))
        self.assertIn('先做小样本验证',ctx.encode(after['website_updates']))

    def test_context_authorization_and_continuity_roundtrip(self):
        from proposal_app.project_archive import atomic_json
        card = self.api(self.path, self.student)
        folder = self.srv.project_archive.folder(card)
        archive = {'conversations': [{'thread_id': 'test', 'step': 1, 'messages': [{'id': 'M1', 'role': 'user', 'text': '先研究延误，因为早晨反复发生。'}]}]}
        atomic_json(folder / 'discussions.json', archive)
        body = {'request_id': 'note1', 'revision': 0, 'project_version': card['version'], 'coverage': {'test': 'M1'},
                'entries': [{'kind': 'decision', 'text': '先研究早晨反复发生的延误。', 'sources': [{'message_id': 'M1', 'quote': '因为早晨反复发生'}]}]}
        self.api(self.path + '/continuity', self.other, body, expect=404)
        saved = self.api(self.path + '/continuity', self.student, body)
        self.assertTrue(saved['saved'])
        brief = self.api(self.path + '/context', self.student)
        self.assertLessEqual(len(ctx.encode(brief)), 10000)
        self.assertEqual(brief['continuity_revision'], 1)
        self.assertEqual(brief['coverage']['uncovered_count'], 0)
        self.api(self.path + '/context', self.other, expect=404)
        index = self.api(self.path + '/read-project-file', self.student, {'path': brief['index'], 'limit': 3000})
        self.assertNotIn('先研究延误', index['text'])
        self.assertEqual(self.api(self.path, self.student)['version'], card['version'])


if __name__ == '__main__':
    unittest.main()
