import unittest
from copy import deepcopy
from proposal_app.test_research_store import fixture, create, accept
from proposal_app import research_service as service, research_store as store, workflow
from proposal_app.test_stage_review import StageReviewAtomicTests
from proposal_app import test_service
from proposal_app.test_research_fixtures import ResearchHTTP


class HandoffRepairTests(StageReviewAtomicTests):
    def test_handoff_keeps_rejected_choices_protected(self):
        self.card['steps'][0]['data']['title']='已选方向'
        before=deepcopy(self.card)
        with self.assertRaises(ValueError):
            service.mutate(self.c,self.card,'research-handoff',dict(step=1,data={'title':'导师偷换方向'}),self.user,coach=True,student_messages=self.messages)
        self.assertEqual(self.card,before)

    def test_handoff_invalid_relation_rolls_back_its_object_edit(self):
        before=deepcopy(self.card);obj=store.get(self.c,'P','Q')
        with self.assertRaises(ValueError):
            service.mutate(self.c,self.card,'research-handoff',dict(step=1,objects=[dict(id='Q',expected_revision=1,content_patch={'set':{'wording':'新问法'},'remove':[]})],activate_link_ids=['missing']),self.user,coach=True,student_messages=self.messages)
        self.assertEqual(self.card,before);self.assertEqual(store.get(self.c,'P','Q'),obj)

    def test_handoff_saves_drafts_and_returns_exact_readiness(self):
        service.mutate(self.c,self.card,'research-handoff',dict(step=1,data={'selection_reason':'关注稳定性'},objects=[],links=[]),self.user,coach=True,student_messages=self.messages)
        self.assertTrue(self.card['research']['review_readiness']['prepared'])
        self.assertEqual(self.card['current_step'],1)
        self.assertEqual(store.get(self.c,'P','Q')['status'],'draft')

    def test_preview_has_no_writes_and_matches_actual_completion(self):
        from proposal_app import stage_review
        before=deepcopy(self.card); rows=store.rows(self.c,'research_events','P')
        result=stage_review.preview(self.c,self.card,self.messages)
        self.assertTrue(result['prepared'])
        self.assertEqual(self.card,before);self.assertEqual(store.rows(self.c,'research_events','P'),rows)
        self.submit();self.assertEqual(self.card['current_step'],2)

    def test_preview_works_on_query_only_connection(self):
        from proposal_app import stage_review
        self.c.execute('PRAGMA query_only=ON')
        try:self.assertTrue(stage_review.preview(self.c,self.card,self.messages)['prepared'])
        finally:self.c.execute('PRAGMA query_only=OFF')


class RelationshipImpactTests(unittest.TestCase):
    def test_stale_check_is_replaced_in_one_confirmation(self):
        from proposal_app.test_research_fixtures import CONTENTS
        from proposal_app import stage_review
        c,card,user=fixture();self.addCleanup(c.close)
        for kind in ('rq','method'):
            create(c,card,user,kind,kind,CONTENTS[kind]);accept(c,card,user,kind)
        create(c,card,user,'h','hypothesis',dict(explanation='灯控导致波动',alternatives='天气',scope='本人',mechanism='等待',prediction='等待增加用时'));accept(c,card,user,'h')
        ref=lambda oid:dict(type='object',id=oid,revision=store.get(c,'P',oid)['revision'])
        for lid,a,b,rel in [('e','h','rq','explains'),('m','rq','method','operationalized_by')]:
            service.mutate(c,card,'research-objects',{'links':[dict(id=lid,from_ref=ref(a),to_ref=ref(b),relation=rel,reason='已有讨论')]},user)
            accept(c,card,user,b,relations={'activate_draft_ids':[lid]})
        content=dict(scope_refs=[ref(k) for k in ('rq','h','method')],rq_alignment='描述性比较',alternative_discrimination='不识别因果',conclusion_limits='仅样本',reasoned_findings=['已核对'],reviewer_response='保留限制',unresolved=[])
        create(c,card,user,'old','check',content);accept(c,card,user,'old')
        old=store.get(c,'P','old');old['needs_review']=True;store.pointer(c,old)
        create(c,card,user,'new','check',dict(content,supersedes=ref('old')))
        card['current_step']=4
        for st in card['steps'][:3]:st['status']='complete'
        card['steps'][3]['status']='active';card['steps'][3]['data']={k:'依据保留' for k,_ in workflow.TASKS[3][3]}
        service.enrich(c,card)
        self.assertTrue(card['research']['review_readiness']['prepared'])
        self.assertEqual(store.get(c,'P','old')['status'],'confirmed')
        service.mutate(c,card,'research-review',dict(step=4,complete=True,confirmed=True),user)
        self.assertEqual(store.get(c,'P','old')['status'],'superseded')
        self.assertEqual(card['current_step'],5)

    def test_adding_explicit_structural_link_does_not_reopen_unchanged_source(self):
        c,card,user=fixture();self.addCleanup(c.close)
        create(c,card,user,'q','question',dict(wording='哪条路线稳定？',importance='准时',question_type='measurement'))
        create(c,card,user,'p','problem',dict(puzzle='速度和准时不一致',grouping_reason='同一困惑',candidate_explanations='灯控'))
        accept(c,card,user,'q');accept(c,card,user,'p')
        for st in card['steps'][:3]:st['status']='complete'
        card['steps'][3]['status']='active';card['current_step']=4
        service.mutate(c,card,'research-objects',{'links':[dict(id='L',from_ref=dict(type='object',id='q',revision=2),to_ref=dict(type='object',id='p',revision=2),relation='groups_into',reason='已有归组理由') ]},user)
        rev=store.get(c,'P','p')['revision']
        accept(c,card,user,'p',relations={'activate_draft_ids':['L']})
        self.assertEqual(card['current_step'],4);self.assertEqual(card['steps'][1]['status'],'complete')
        self.assertEqual(store.get(c,'P','p')['revision'],rev)
        self.assertFalse(store.get(c,'P','p').get('needs_review'))


class CoachAuthorityTests(unittest.TestCase):
    setUp=test_service.ServiceFlow.setUp
    api=test_service.ServiceFlow.api
    login=test_service.ServiceFlow.login
    def test_bearer_cannot_complete_any_stage(self):
        r=ResearchHTTP(self)
        for step in range(1,7):
            r.write('progress',dict(workflow_version='tanyue-v1',step=step,complete=True,confirmed=True,data={'summary':'不应代确认'}),403)

class ContinuityContractTests(unittest.TestCase):
    def test_first_continuity_revision_zero_matches_archive_contract(self):
        from proposal_app import coach_mcp
        coach_mcp.validate(coach_mcp.SCHEMAS['proposal_save_continuity'],dict(project_id='P',revision=0,project_version=1,request_id='first',entries=[],coverage={}))

if __name__=='__main__':unittest.main()
