"""Real HTTP regression for a single personal stage-review submission."""
import uuid
from copy import deepcopy
from proposal_app import test_service
from proposal_app.test_research_fixtures import ResearchHTTP
from proposal_app.test_research_store import fixture
from proposal_app import research_service as service, research_store as store
import unittest

class CompactResearchHTTP(ResearchHTTP):
    def confirm(self, oid, links=(), patch=None):
        o = next(o for o in self.card['research']['objects'] if o['id'] == oid)
        return self.write('quality', {'kind':'proposal','record':dict(target_object_id=oid,expected_revision=o['revision'],text='核对本次成果',reason='根据已有讨论选择',content_patch=patch or {'set':{},'remove':[]},proposed_status='confirmed',relation_changes={'activate_draft_ids':list(links),'retire_link_ids':[]})})
    def progress(self, n, data=None, expect=200):
        if expect != 200: return super().progress(n, data, expect)
        self.write('progress',dict(workflow_version='tanyue-v1',step=n,complete=False,confirmed=False,data=data or {'summary':'已讨论并整理的阶段小结'}))
        return self.write('research-review',dict(step=n,complete=True,confirmed=True,edits=[],data={}),web=True)

class StageReviewHTTP(unittest.TestCase):
    setUp=test_service.ServiceFlow.setUp
    api=test_service.ServiceFlow.api
    login=test_service.ServiceFlow.login
    def test_method_edit_is_saved_when_dependent_science_needs_update(self):
        r=CompactResearchHTTP(self);r.stage_a();r.stage_b();r.stage_c()
        # Prepare D without making the personal decision yet.
        def draft(n,data=None,expect=200):
            return r.write('progress',dict(workflow_version='tanyue-v1',step=n,complete=False,confirmed=False,data=data))
        r.progress=draft;r.stage_d()
        r.write('research-review',dict(step=4,complete=True,confirmed=True,edits=[dict(id='method',expected_revision=1,set={'procedure':'只记录同一条路线，比较不同出发时刻'})],data={}),web=True)
        method=next(o for o in r.card['research']['objects'] if o['id']=='method')
        check=next(o for o in r.card['research']['objects'] if o['id']=='check')
        self.assertEqual(method['status'],'confirmed');self.assertIn('不同出发时刻',method['content']['procedure'])
        self.assertTrue(check['needs_review']);self.assertEqual(r.card['current_step'],4)
        self.assertFalse(any(p['status']=='pending' and p.get('target_object_id')=='method' for p in r.card['quality']['records']))
    def test_one_gesture_each_stage_preserves_full_contract(self):
        r=CompactResearchHTTP(self)
        r.ready()
        self.assertEqual(r.card['status'],'review')
        self.assertTrue(all(p['status']!='pending' for p in r.card['quality']['records']))
        self.assertEqual(r.card['submitted_deliverable']['id'],r.card['steps'][4]['data']['deliverable_ref']['id'])
        self.assertEqual(len(r.card['steps'][2]['data']['source_comparisons']),2)

    def test_bearer_cannot_confirm_and_stale_version_rejected(self):
        r=ResearchHTTP(self)
        r.write('research-review',dict(step=1,confirmed=True,complete=False,edits=[],data={}),403)
        body=dict(step=1,confirmed=True,complete=False,version=r.card['version']-1,request_id=uuid.uuid4().hex)
        self.api(self.path+'/research-review','cookie:'+self.student,body,409)

class StageReviewAtomicTests(unittest.TestCase):
    def setUp(self):
        self.c,self.card,self.user=fixture();self.addCleanup(self.c.close)
        self.messages={'M':'我想了解早晨路线的差异'}
        service.mutate(self.c,self.card,'research-objects',{'objects':[
            dict(id='C',kind='curiosity',expected_revision=0,content=dict(observation='两条路线用时不同',why_care='希望准时',student_quote_ref='M')),
            dict(id='Q',kind='question',expected_revision=0,content=dict(wording='两条路线哪条更稳定？',importance='减少迟到',question_type='measurement'))]},self.user,student_messages=self.messages)
        self.card['steps'][0]['data']=dict(summary='比较通勤路线',selection_reason='先关注稳定性')
    def submit(self,**kw):
        return service.mutate(self.c,self.card,'research-review',dict(step=1,confirmed=True,complete=True,edits=[],data={},**kw),self.user,student_messages=self.messages)
    def test_direction_handoff_keeps_unselected_questions_in_exploration(self):
        direction=dict(observation_id='C',main_question_id='Q',subquestion_ids=['timing'])
        objects=[dict(id=oid,kind='question',expected_revision=0,
                      content=dict(wording=wording,importance='研究数字人的互动表现',question_type='open'))
                 for oid,wording in [('timing','表情出现的时机会影响认真倾听的感觉吗？'),
                                     ('candidate','表情要不要随措辞变化？')]]
        tentative = dict(target_object_id='candidate', expected_revision=1, text='试聊候选',
                         reason='先想一想不同措辞', content_patch={'set':{},'remove':[]}, proposed_status='confirmed')
        service.mutate(self.c,self.card,'research-handoff',dict(step=1,objects=objects,proposals=[tentative],data=dict(
            direction=direction,technical_plan='同一个数字人对比固定规则和实时调整，两版都可以用渐变。',
            first_validation='用户停顿后继续说，检查能否撤回准备开口的动作。')),
            self.user,coach=True,student_messages=self.messages)
        with self.assertRaises(store.Conflict):
            service.mutate(self.c,self.card,'research-review',dict(step=1,scope='item',confirmed=True,
                edits=[dict(id='candidate',expected_revision=1,set={'wording':'改写未选问题'})]),self.user)
        service.mutate(self.c,self.card,'research-review',dict(step=1,scope='item',confirmed=True,
            data={'technical_plan':'两版都用相同的声音、表情和渐变。'}),self.user)
        self.submit()
        step=self.card['steps'][0]['data']
        self.assertEqual(step['direction'],direction)
        self.assertEqual(step['technical_plan'],'两版都用相同的声音、表情和渐变。')
        self.assertEqual({ref['id'] for ref in step['object_refs']},{'C','Q','timing'})
        self.assertEqual(store.get(self.c,'P','candidate')['status'],'draft')
        self.assertEqual(next(p['status'] for p in self.card['quality']['records']
                              if p.get('target_object_id') == 'candidate'),'superseded')
    def test_handoff_rejects_unknown_or_repeated_direction_objects(self):
        for subquestions in (['missing'], ['Q']):
            with self.subTest(subquestions=subquestions), self.assertRaises(ValueError):
                service.mutate(self.c,self.card,'research-handoff',dict(step=1,data={
                    'direction':dict(observation_id='C',main_question_id='Q',subquestion_ids=subquestions)}),
                    self.user,coach=True)
        self.assertNotIn('direction',self.card['steps'][0]['data'])
    def test_edit_and_complete_without_another_confirmation(self):
        service.mutate(self.c,self.card,'research-review',dict(step=1,confirmed=True,complete=True,edits=[dict(id='Q',expected_revision=1,set={'wording':'哪个路线的用时波动更小？'})],data={}),self.user,student_messages=self.messages)
        self.assertEqual(self.card['current_step'],2)
        obj=store.get(self.c,'P','Q')
        self.assertEqual(obj['status'],'confirmed');self.assertEqual(obj['content']['question_type'],'measurement')
        self.assertEqual(obj['content']['wording'],'哪个路线的用时波动更小？')
        self.assertEqual(store.get(self.c,'P','C')['content']['student_quote'],self.messages['M'])
        self.assertFalse(any(r['status']=='pending' for r in self.card['quality']['records']))
    def test_failure_rolls_back_all_confirmations(self):
        self.card['steps'][0]['data'].pop('selection_reason')
        before=deepcopy(self.card);rows=store.rows(self.c,'research_objects','P')
        with self.assertRaises(ValueError):self.submit()
        self.assertEqual(self.card,before);self.assertEqual(store.rows(self.c,'research_objects','P'),rows)
        self.assertEqual(store.rows(self.c,'research_events','P'),before['research']['events'])
    def test_coach_cannot_use_new_path(self):
        with self.assertRaises(PermissionError):service.mutate(self.c,self.card,'research-review',dict(step=1,confirmed=True,complete=True),self.user,coach=True)
    def test_stale_edit_does_not_partially_confirm(self):
        before=deepcopy(self.card)
        with self.assertRaises(store.Conflict):service.mutate(self.c,self.card,'research-review',dict(step=1,confirmed=True,edits=[dict(id='Q',expected_revision=99,set={'wording':'新问题'})]),self.user)
        self.assertEqual(self.card,before)
    def test_partial_review_skips_unprepared_supporting_record(self):
        service.mutate(self.c,self.card,'research-objects',{'objects':[dict(id='C',expected_revision=1,content_patch={'set':{},'remove':['why_care']})]},self.user,student_messages=self.messages)
        service.mutate(self.c,self.card,'research-review',dict(step=1,confirmed=True,complete=False,edits=[dict(id='Q',expected_revision=1,set={'wording':'哪条路线迟到更少？'})]),self.user,student_messages=self.messages)
        self.assertEqual(store.get(self.c,'P','Q')['status'],'confirmed')
        self.assertEqual(store.get(self.c,'P','C')['status'],'draft')
        self.assertEqual(self.card['current_step'],1)
    def test_item_save_leaves_other_items_and_stage_unconfirmed(self):
        original=store.get(self.c,'P','C')
        service.mutate(self.c,self.card,'research-review',dict(step=1,scope='item',confirmed=True,complete=False,edits=[dict(id='Q',expected_revision=1,set={'wording':'哪条路线更准时？'})]),self.user,student_messages=self.messages)
        saved=store.get(self.c,'P','Q')
        self.assertEqual(saved['status'],'confirmed');self.assertEqual(store.get(self.c,'P','C'),original)
        self.assertEqual(self.card['current_step'],1);self.assertEqual(self.card['steps'][0]['status'],'active')
        service.mutate(self.c,self.card,'research-review',dict(step=1,scope='item',confirmed=True,complete=False,data={'selection_reason':'我想减少迟到'}),self.user,student_messages=self.messages)
        self.assertEqual(store.get(self.c,'P','C'),original)
        self.assertEqual(self.card['steps'][0]['data']['selection_reason'],'我想减少迟到')
        self.submit()
        self.assertEqual(store.get(self.c,'P','Q')['revision'],saved['revision'])
        self.assertEqual(self.card['current_step'],2)
    def test_item_save_cannot_complete_stage(self):
        before=deepcopy(self.card)
        with self.assertRaises(ValueError):
            service.mutate(self.c,self.card,'research-review',dict(step=1,scope='item',confirmed=True,complete=True,edits=[dict(id='Q',expected_revision=1,set={'wording':'误提交'})]),self.user,student_messages=self.messages)
        self.assertEqual(self.card,before)

if __name__=='__main__':unittest.main()
