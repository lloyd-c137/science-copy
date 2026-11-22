"""Regressions from the native-model A-F rehearsal; no production database."""
import unittest
from copy import deepcopy
from proposal_app import workflow, research_service as service, research_store as store
from proposal_app.test_research_store import fixture, create, accept

class LiveAFFixes(unittest.TestCase):
    def setUp(self):
        self.c,self.card,self.user=fixture();self.addCleanup(self.c.close)

    def test_confirmed_relation_only_keeps_revision_and_completed_upstream(self):
        create(self.c,self.card,self.user,'P','problem',dict(puzzle='困惑',grouping_reason='归组',candidate_explanations='解释'))
        accept(self.c,self.card,self.user,'P')
        create(self.c,self.card,self.user,'Q','question',dict(wording='问题',question_type='open',importance='重要'))
        accept(self.c,self.card,self.user,'Q')
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='group',from_ref=dict(type='object',id='Q',revision=2),to_ref=dict(type='object',id='P',revision=2),relation='groups_into',reason='归组')]},self.user)
        accept(self.c,self.card,self.user,'P',relations={'activate_draft_ids':['group']})
        revision=store.get(self.c,'P','P')['revision']
        self.card['steps'][0]['status']=self.card['steps'][1]['status']='complete'
        self.card['steps'][2]['status']='active';self.card['current_step']=3
        self.card['materials']=[dict(id='S',url='https://example.test',title='来源')]
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='support',from_ref=dict(type='source',id='S'),to_ref=dict(type='object',id='P',revision=revision),relation='supports',reason='补充依据')]},self.user)
        create(self.c,self.card,self.user,'R','rq',dict(population_or_object='本人',conditions='固定',question='有何差别',scope='描述',promised_conclusion='局部'))
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='frames',from_ref=dict(type='object',id='P',revision=revision),to_ref=dict(type='object',id='R',revision=1),relation='frames',reason='形成问题')]},self.user)
        pending=service.object_proposal(self.card,{'record':dict(target_object_id='R',expected_revision=1,text='核对问题',reason='本人选择',relation_changes={'activate_draft_ids':['frames']})},self.user)
        self.card['quality']['records'].append(pending)
        before=deepcopy(self.card['steps'][:2])
        accept(self.c,self.card,self.user,'P',relations={'activate_draft_ids':['support']})
        self.assertEqual(store.get(self.c,'P','P')['revision'],revision)
        self.assertEqual(self.card['current_step'],3)
        self.assertEqual(self.card['steps'][:2],before)
        self.assertFalse(store.get(self.c,'P','P').get('needs_review'))
        self.assertFalse(next(l for l in self.card['research']['links'] if l['id']=='group').get('needs_review'))
        self.assertEqual(self.card['quality']['records'][-1]['status'],'accepted')
        service.decide(self.c,self.card,dict(record_id=pending['id'],decision='accepted',confirmed=True,reason='核对后续问题'),self.user)
        self.assertEqual(self.card['current_step'],3)
        self.assertEqual(next(l for l in self.card['research']['links'] if l['id']=='frames')['status'],'confirmed')
        accept(self.c,self.card,self.user,'P',{'set':{'puzzle':'真正改题'}})
        self.assertEqual(store.get(self.c,'P','P')['revision'],revision+1)
        self.assertEqual(self.card['current_step'],2)

    def test_publication_state_uses_exact_submitted_revision(self):
        from proposal_app.research_service import publication_status
        card={'submissions':[{'id':'D','revision':1},{'id':'D','revision':2}],
              'prior_reviews':[{'decision':'supplement','deliverable_ref':{'id':'D','revision':1}}],
              'review':{'decision':'approve','deliverable_ref':{'id':'D','revision':2}}}
        self.assertEqual(publication_status(card,{'id':'D','revision':1}),'supplement')
        self.assertEqual(publication_status(card,{'id':'D','revision':2}),'approved')
        self.assertEqual(publication_status(card,{'id':'D','revision':3,'status':'prepared'}),'prepared')
        card['review']=None
        self.assertEqual(publication_status(card,{'id':'D','revision':2}),'submitted')

    def test_unconfirmed_draft_saves_without_confirming_or_advancing(self):
        body=dict(step=1,workflow_version=workflow.VERSION,complete=False,confirmed=False,data={'summary':'从已有对话整理'})
        workflow.save_progress(self.card,body,self.user)
        self.assertFalse(self.card['steps'][0]['confirmed'])
        self.assertEqual(self.card['current_step'],1)
        self.assertEqual(self.card['steps'][0]['status'],'active')
        with self.assertRaisesRegex(ValueError,'核对'):workflow.save_progress(self.card,dict(body,complete=True),self.user)

    def pair(self):
        create(self.c,self.card,self.user,'R','rq',dict(population_or_object='本人',conditions='固定条件',question='有何差别',scope='描述',promised_conclusion='局部差异'))
        create(self.c,self.card,self.user,'H','hypothesis',dict(explanation='暂定解释',alternatives='其他解释',scope='局部',not_applicable_reason='描述性'))
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='L',from_ref=dict(type='object',id='H',revision=1),to_ref=dict(type='object',id='R',revision=1),relation='explains',reason='解释问题')]},self.user)
        p=service.object_proposal(self.card,{'record':dict(target_object_id='H',expected_revision=1,text='确认解释',reason='核对',relation_changes={'activate_draft_ids':['L']})},self.user)
        self.card['quality']['records'].append(p);return p

    def test_dependent_candidate_survives_content_identical_confirmation(self):
        p=self.pair();accept(self.c,self.card,self.user,'R')
        service.decide(self.c,self.card,dict(record_id=p['id'],decision='accepted',confirmed=True,reason='本人核对'),self.user)
        link=next(l for l in self.card['research']['links'] if l['id']=='L')
        self.assertEqual(link['to_ref']['revision'],2)
        self.assertEqual(link['status'],'confirmed')

    def test_semantic_change_stays_blocked_and_is_visible_before_click(self):
        p=self.pair();accept(self.c,self.card,self.user,'R',{'set':{'question':'改了问题'}})
        self.assertTrue(any(i['kind']=='pending_choice' and i['status']=='incomplete' for i in workflow.review_readiness(self.card)['items']))
        before=deepcopy(self.card)
        with self.assertRaisesRegex(ValueError,'关联对象版本'):
            service.decide(self.c,self.card,dict(record_id=p['id'],decision='accepted',confirmed=True,reason='核对'),self.user)
        self.assertEqual(self.card,before)

    def test_draft_check_cannot_be_superseded_at_save_or_proposal(self):
        create(self.c,self.card,self.user,'T')
        scope=[dict(type='object',id='T',revision=1)]
        create(self.c,self.card,self.user,'OLD','check',dict(scope_refs=scope))
        replacement=dict(scope_refs=scope,supersedes=dict(type='object',id='OLD',revision=1))
        with self.assertRaisesRegex(ValueError,'已确认'):
            create(self.c,self.card,self.user,'NEW','check',replacement)
        create(self.c,self.card,self.user,'NEW','check',dict(scope_refs=scope))
        with self.assertRaisesRegex(ValueError,'已确认'):
            service.object_proposal(self.card,{'record':dict(target_object_id='NEW',expected_revision=1,text='错误替代',reason='理由',content_patch={'set':replacement})},self.user)

    def test_publication_preserves_optional_review_fields_and_history(self):
        self.card.update(status='review',submitted_deliverable=dict(id='D',revision=1,activity_version=1))
        self.card['research']['deliverables']=[dict(id='D',revision=1,object_refs=[])]
        body=dict(decision='supplement',step=5,value='价值',feasibility='可行性',deliverable='补表',owner='学生',due='2027-01-01',standard='逐行可复算',evidence='已读原表',gaps='缺分母',arbitrary='不应复制')
        workflow.review(self.card,body,dict(role='teacher',name='老师'))
        for k in ('standard','evidence','gaps'):self.assertEqual(self.card['review'][k],body[k])
        self.assertNotIn('arbitrary',self.card['review'])
        self.assertEqual(self.card['current_step'],5)

if __name__=='__main__':unittest.main()
