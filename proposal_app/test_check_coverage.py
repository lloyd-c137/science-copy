import unittest
from copy import deepcopy
from proposal_app import research_schema as schema, workflow, research_service as service
from proposal_app.test_research_store import fixture, create, accept

class CheckCoverageTests(unittest.TestCase):
    def setUp(self):
        self.c,self.card,self.user=fixture()
        self.data={k:'合成测试依据' for k,_ in workflow.TASKS[3][3]}
        self.objects=[dict(id=k,kind=k,revision=2,status='confirmed',content={}) for k in ('rq','hypothesis','method')]
        self.refs=[dict(type='object',id=o['id'],revision=2) for o in self.objects]
        self.links=[dict(relation=rel,from_ref=self.refs[a],to_ref=self.refs[b],status='confirmed') for rel,a,b in [('explains',1,0),('operationalized_by',0,2)]]
        self.content=dict(scope_refs=deepcopy(self.refs),mechanical_findings=[],reasoned_findings=['仅核对计划'],reviewer_response='本人接受限制',unresolved=[],rq_alignment='分布比较能回答差异问题',alternative_discrimination='观察设计不能排除天气解释',conclusion_limits='仅这两周样本')
        self.card['research'].update(objects=self.objects+[dict(id='check',kind='check',revision=2,status='confirmed',content=self.content)],links=self.links)
    def tearDown(self):self.c.close()
    def test_complete_chain_and_hypothesis_method_route_pass(self):
        workflow.validate_completion(self.card,4,self.data)
        self.links[1]['from_ref']=self.refs[1]
        workflow.validate_completion(self.card,4,self.data)
    def test_method_only_and_disconnected_triple_fail(self):
        self.content['scope_refs']=[self.refs[2]]
        with self.assertRaises(ValueError):workflow.validate_completion(self.card,4,self.data)
        self.content['scope_refs']=deepcopy(self.refs)
        self.links[0]['status']='draft'
        with self.assertRaises(ValueError):workflow.validate_completion(self.card,4,self.data)
    def test_each_scientific_judgment_is_required_only_at_completion(self):
        for key in ('rq_alignment','alternative_discrimination','conclusion_limits'):
            with self.subTest(key=key):
                saved=self.content.pop(key)
                schema.validate('check',self.content,confirmed=True)
                with self.assertRaises(ValueError):workflow.validate_completion(self.card,4,self.data)
                self.content[key]=saved
                with self.assertRaises(ValueError):schema.validate('check',{key:[]})
    def test_stale_unconfirmed_or_reviewed_chain_fails(self):
        for update in ({'status':'draft'},{'needs_review':True},{'revision':3}):
            original=deepcopy(self.objects[1]);self.objects[1].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):workflow.validate_completion(self.card,4,self.data)
            self.objects[1].clear();self.objects[1].update(original)
    def test_chain_links_must_be_current_and_reviewed(self):
        for update in ({'needs_review':True},{'status':'draft'},{'from_ref':dict(self.refs[1],revision=1)}):
            original=deepcopy(self.links[0]);self.links[0].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):workflow.validate_completion(self.card,4,self.data)
            self.links[0].clear();self.links[0].update(original)
    def test_unrelated_operationalization_does_not_supply_chain(self):
        other=dict(id='other',kind='rq',revision=2,status='confirmed',content={})
        self.card['research']['objects'].append(other)
        ref=dict(type='object',id='other',revision=2)
        self.content['scope_refs'].append(ref);self.links[1]['from_ref']=ref
        with self.assertRaises(ValueError):workflow.validate_completion(self.card,4,self.data)
    def test_mechanical_preserves_scientific_judgment_boundary(self):
        create(self.c,self.card,self.user,'topic')
        accept(self.c,self.card,self.user,'topic')
        findings=service.mechanical(self.c,self.card,[dict(type='object',id='topic',revision=2)])
        self.assertEqual(findings,[{'finding':'missing_chain_scope','kinds':['rq','hypothesis','method']}])
    def test_public_contract_matches_required_fields(self):
        contract=self.card['research']['contract']
        self.assertIn('scope',contract['object_types']['hypothesis']['required_on_confirmation'])
        for key in schema.CHECK_JUDGMENTS:self.assertIsInstance(contract['check_save']['content'][key],str)
        self.assertIn('belongs_to',contract['content_schema']['relation_directions'])
        self.assertIn('problem/',contract['content_schema']['relation_directions']['supports/challenges/limits'])
    def test_hypothesis_scope_required_on_confirmation(self):
        content=dict(explanation='解释',alternatives='备择',not_applicable_reason='质性解释路径')
        schema.validate('hypothesis',content)
        with self.assertRaisesRegex(ValueError,'scope'):schema.validate('hypothesis',content,True)
        schema.validate('hypothesis',dict(content,scope='仅适用于本校访谈'),True)
    def test_new_relations_use_normal_confirmation_and_snapshot_lifecycle(self):
        create(self.c,self.card,self.user,'q','question',dict(wording='为何如此',question_type='open',importance='个人困惑'))
        accept(self.c,self.card,self.user,'q')
        create(self.c,self.card,self.user,'t')
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='belongs',from_ref=dict(type='object',id='q',revision=2),to_ref=dict(type='object',id='t',revision=1),relation='belongs_to',reason='同一主题')]},self.user)
        self.assertEqual(self.card['research']['links'][0]['status'],'draft')
        accept(self.c,self.card,self.user,'t',relations={'activate_draft_ids':['belongs']})
        self.assertEqual(self.card['research']['links'][0]['status'],'confirmed')
        create(self.c,self.card,self.user,'p','problem',dict(puzzle='困惑',grouping_reason='共同点',candidate_explanations='解释'))
        self.card['materials']=[dict(id='S',title='合成来源',url='https://example.test/source')]
        service.mutate(self.c,self.card,'research-objects',{'links':[dict(id='challenge',from_ref=dict(type='source',id='S'),to_ref=dict(type='object',id='p',revision=1),relation='challenges',reason='已读片段改变问题前提')]},self.user)
        accept(self.c,self.card,self.user,'p',relations={'activate_draft_ids':['challenge']})
        link=next(l for l in self.card['research']['links'] if l['id']=='challenge')
        self.assertEqual(link['status'],'confirmed')
        self.assertIn('snapshot_id',link['from_ref'])
    def test_new_relations_and_direction_boundaries(self):
        for oid,kind in [('q','question'),('t','topic'),('p','problem')]:create(self.c,self.card,self.user,oid,kind,{'draft':'草稿'})
        ref=lambda oid:dict(type='object',id=oid,revision=1)
        for rel,left,right in [('belongs_to',ref('q'),ref('t'))]+[(r,dict(type='source',id='S'),ref('p')) for r in ('supports','challenges','limits')]:
            service.validate_link(self.c,self.card,left,right,rel)
        self.assertIn('belongs_to',schema.RELATIONS)
        with self.assertRaises(ValueError):service.validate_link(self.c,self.card,ref('t'),ref('q'),'belongs_to')
        with self.assertRaises(ValueError):service.validate_link(self.c,self.card,dict(type='source',id='S'),ref('t'),'supports')

if __name__=='__main__':unittest.main()
