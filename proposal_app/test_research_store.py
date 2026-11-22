import sqlite3, unittest
from copy import deepcopy
try:
    from . import research_service as service, research_store as store, workflow
except ImportError:
    import research_service as service, research_store as store, workflow

def fixture():
    c=sqlite3.connect(':memory:');store.init_schema(c)
    card=dict(id='P',student_id='U',activity={'version':1},current_step=1,status='active',version=1,quality={'records':[]},steps=[dict(number=i+1,title=t[0],data={},status='active' if i==0 else 'pending') for i,t in enumerate(workflow.TASKS)])
    service.enrich(c,card);return c,card,dict(id='U',role='student',name='Student')
def create(c,card,user,oid,kind='topic',content=None):
    service.mutate(c,card,'research-objects',{'objects':[dict(id=oid,kind=kind,expected_revision=0,content=content or {'title':'主题','exploration_reason':'实际观察'})]},user)
def accept(c,card,user,oid,patch=None,relations=None):
    obj=store.get(c,card['id'],oid)
    p=service.object_proposal(card,{'record':dict(target_object_id=oid,expected_revision=obj['revision'],text='核对',reason='本人选择',content_patch=patch or {'set':{},'remove':[]},relation_changes=relations or {},proposed_status='confirmed')},user)
    card['quality']['records'].append(p)
    service.decide(c,card,dict(record_id=p['id'],decision='accepted',reason='同意理由',confirmed=True),user)
    return p
class ResearchStoreTests(unittest.TestCase):
    def setUp(self): self.c,self.card,self.user=fixture()
    def tearDown(self): self.c.close()
    def test_updates_keep_object_and_link_order(self):
        for oid in ('first','middle','last'):create(self.c,self.card,self.user,oid)
        order=lambda table:[r['id'] for r in store.rows(self.c,table,'P')]
        expected=order('research_objects')
        accept(self.c,self.card,self.user,'first',{'set':{'title':'修改第一项'},'remove':[]})
        accept(self.c,self.card,self.user,'middle')
        accept(self.c,self.card,self.user,'first',{'set':{'title':'再次修改第一项'},'remove':[]})
        self.assertEqual(order('research_objects'),expected)
        self.assertEqual(store.get(self.c,'P','first',1)['content']['title'],'主题')
        for lid in ('link-first','link-last'):store.save_link(self.c,dict(project_id='P',id=lid,status='draft'))
        store.save_link(self.c,dict(project_id='P',id='link-first',status='confirmed'))
        self.assertEqual(order('research_links'),['link-first','link-last'])
    def test_search_envelope_is_not_silently_saved_as_empty_draft(self):
        before=deepcopy(self.card)
        with self.assertRaisesRegex(ValueError,'payload.content'):
            service.mutate(self.c,self.card,'research-search',{'entry':{'query':'实际检索词'}},self.user)
        self.assertEqual(self.card,before)
        self.assertEqual(store.rows(self.c,'research_objects','P'),[])
        payload=deepcopy(self.card['research']['contract']['search_save'])
        payload['content']['reading_scope']='abstract'
        service.mutate(self.c,self.card,'research-search',payload,self.user)
        obj=self.card['research']['objects'][0]
        self.assertEqual(obj['content']['query'],'实际检索式')
        self.assertEqual(obj['status'],'draft')
    def test_batch_rolls_back_and_card_is_unchanged(self):
        original=deepcopy(self.card)
        with self.assertRaises(ValueError): service.mutate(self.c,self.card,'research-objects',{'objects':[dict(id='A',kind='topic',expected_revision=0,content={}),dict(id='B',kind='bad',expected_revision=0,content={})]},self.user)
        self.assertEqual(self.card,original);self.assertEqual(store.rows(self.c,'research_objects','P'),[])
    def test_caller_rollback_includes_service_mutation(self):
        create(self.c,self.card,self.user,'A');self.assertTrue(self.c.in_transaction)
        self.c.rollback();self.assertEqual(store.rows(self.c,'research_objects','P'),[])
    def test_patch_preserves_fields_and_confirmed_guard(self):
        create(self.c,self.card,self.user,'A');accept(self.c,self.card,self.user,'A',{'set':{'title':'新主题'},'remove':[]})
        o=store.get(self.c,'P','A');self.assertEqual(o['content']['exploration_reason'],'实际观察')
        with self.assertRaises(ValueError): service.mutate(self.c,self.card,'research-objects',{'objects':[dict(id='A',expected_revision=2,content_patch={'set':{'title':'绕过'}})]},self.user)
        self.assertEqual(store.get(self.c,'P','A',1)['content']['title'],'主题')
    def test_stale_proposal_and_relation_activation(self):
        create(self.c,self.card,self.user,'A','question',dict(wording='问题',question_type='open',importance='重要'))
        create(self.c,self.card,self.user,'B','problem',dict(puzzle='困惑',grouping_reason='归组',candidate_explanations='解释'))
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='L',from_ref={'type':'object','id':'A','revision':1},to_ref={'type':'object','id':'B','revision':1},relation='groups_into',reason='源于问题')]},self.user)
        self.assertEqual(self.card['research']['links'][0]['status'],'draft')
        accept(self.c,self.card,self.user,'A',relations={'activate_draft_ids':['L']})
        self.assertEqual(self.card['research']['links'][0]['status'],'confirmed')
        accept(self.c,self.card,self.user,'A',{'set':{'title':'变化'}})
        self.assertTrue(store.get(self.c,'P','B')['needs_review'])
        self.assertFalse(store.get(self.c,'P','A')['needs_review'])
    def test_snapshot_preserves_old_registered_source(self):
        self.card['materials']=[{'id':'S','url':'https://example.test/paper','title':'旧'}]
        one=store.snapshot(self.c,self.card,{'type':'source','id':'S'})
        self.card['materials'][0]['title']='新'
        two=store.snapshot(self.c,self.card,{'type':'source','id':'S'})
        self.assertNotEqual(one['snapshot_id'],two['snapshot_id'])
        self.assertEqual(store.rows(self.c,'research_reference_snapshots','P')[0]['content']['title'],'旧')
        with self.assertRaises(ValueError): store.snapshot(self.c,self.card,{'type':'source','id':'S','content':{'title':'伪造'}})
    def test_student_quote_cannot_be_forged_by_patch(self):
        service.mutate(self.c,self.card,'research-objects',{'objects':[dict(id='C',kind='curiosity',expected_revision=0,content={'observation':'看见现象','why_care':'想知道','student_quote_ref':'M','student_quote':'伪造'})]},self.user,student_messages={'M':'实际学生原话'})
        payload={'record':dict(target_object_id='C',expected_revision=1,text='确认',reason='理由',content_patch={'set':{'student_quote':'另一伪造'}},proposed_status='confirmed')}
        p=service.object_proposal(self.card,payload,self.user,student_messages={'M':'实际学生原话'})
        self.assertEqual(p['candidate_content']['student_quote'],'实际学生原话')
        self.card['quality']['records'].append(p)
        service.decide(self.c,self.card,dict(record_id=p['id'],decision='accepted',reason='本人理由',confirmed=True),self.user,student_messages={'M':'实际学生原话'})
        self.assertEqual(store.get(self.c,'P','C')['content']['student_quote'],'实际学生原话')
    def test_new_check_replaces_old_only_after_student_accepts(self):
        create(self.c,self.card,self.user,'A');accept(self.c,self.card,self.user,'A')
        content=dict(scope_refs=[{'type':'object','id':'A','revision':2}],reasoned_findings=[{'finding':'合成核对'}],unresolved=[],reviewer_response='核对说明')
        create(self.c,self.card,self.user,'OLD','check',content);accept(self.c,self.card,self.user,'OLD')
        accept(self.c,self.card,self.user,'A',{'set':{'title':'变化'}})
        self.assertTrue(store.get(self.c,'P','OLD')['needs_review'])
        fresh=dict(content,scope_refs=[{'type':'object','id':'A','revision':3}],supersedes={'type':'object','id':'OLD','revision':2})
        create(self.c,self.card,self.user,'NEW','check',fresh)
        self.assertEqual(store.get(self.c,'P','OLD')['status'],'confirmed')
        accept(self.c,self.card,self.user,'NEW')
        self.assertEqual(store.get(self.c,'P','OLD')['status'],'superseded')
        self.assertEqual(store.get(self.c,'P','OLD',2)['status'],'confirmed')
        self.assertEqual(store.get(self.c,'P','NEW')['content']['mechanical_findings'],[{'finding':'missing_chain_scope','kinds':['rq','hypothesis','method']}])

    def test_relationship_cannot_fake_question_grouping_with_source(self):
        create(self.c,self.card,self.user,'P','problem',dict(puzzle='困惑',grouping_reason='归组',candidate_explanations='解释'))
        self.card['materials']=[{'id':'S','title':'文献','url':'https://example.test/source'}]
        with self.assertRaisesRegex(ValueError,'关系方向'):
            service.mutate(self.c,self.card,'research-objects',{'links':[dict(from_ref={'type':'source','id':'S'},to_ref={'type':'object','id':'P','revision':1},relation='groups_into',reason='不是问题归组')]},self.user)
        self.assertEqual(store.rows(self.c,'research_links','P'),[])
        self.assertEqual(store.rows(self.c,'research_reference_snapshots','P'),[])
    def test_target_edit_exposes_recheck_and_rejects_unreviewed_upstream(self):
        create(self.c,self.card,self.user,'Q','question',dict(wording='问题',question_type='open',importance='重要'));accept(self.c,self.card,self.user,'Q')
        create(self.c,self.card,self.user,'B','problem',dict(puzzle='困惑',grouping_reason='归组',candidate_explanations='解释'))
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='L',from_ref={'type':'object','id':'Q','revision':2},to_ref={'type':'object','id':'B','revision':1},relation='groups_into',reason='同一困惑')]},self.user)
        accept(self.c,self.card,self.user,'B',relations={'activate_draft_ids':['L']})
        accept(self.c,self.card,self.user,'B',{'set':{'puzzle':'更精确困惑'}})
        self.assertTrue(store.get(self.c,'P','B')['needs_review'])
        upstream=store.get(self.c,'P','Q');upstream['needs_review']=True;store.pointer(self.c,upstream)
        body=dict(object_id='B',expected_revision=3,reason='核对依据',link_ids=['L'])
        with self.assertRaisesRegex(ValueError,'上游'):service.mutate(self.c,self.card,'research-recheck',body,self.user)
        self.assertTrue(store.get(self.c,'P','B')['needs_review'])
        upstream['needs_review']=False;store.pointer(self.c,upstream)
        service.mutate(self.c,self.card,'research-recheck',body,self.user)
        self.assertFalse(store.get(self.c,'P','B')['needs_review'])
        self.assertEqual(next(l for l in self.card['research']['links'] if l['status']=='confirmed')['to_ref']['revision'],3)

    def test_ai_draft_preserves_actual_actor_identity(self):
        service.mutate(self.c,self.card,'research-objects',{'objects':[dict(id='AI',kind='topic',expected_revision=0,content={'title':'草案'})]},self.user,coach=True)
        actor=store.get(self.c,'P','AI')['created_by']
        self.assertEqual(actor['actor_type'],'ai');self.assertEqual(actor['id'],self.user['id'])
        self.assertEqual(actor['name'],'AI 导师')

    def test_other_student_cannot_mutate(self):
        with self.assertRaises(PermissionError): create(self.c,self.card,dict(id='OTHER',role='student'),'A')
if __name__=='__main__': unittest.main()
