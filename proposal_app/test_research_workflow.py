import unittest
from copy import deepcopy
try:
    from .test_research_store import fixture,create,accept
    from . import workflow, research_service as service
except ImportError:
    from test_research_store import fixture,create,accept
    import workflow, research_service as service
class WorkflowTests(unittest.TestCase):
    def setUp(self): self.c,self.card,self.user=fixture()
    def tearDown(self): self.c.close()
    def test_no_field_only_completion(self):
        original=deepcopy(self.card)
        with self.assertRaises(ValueError): workflow.save_progress(self.card,dict(step=1,workflow_version=workflow.VERSION,complete=True,confirmed=True,data={'summary':'填满','selection_reason':'选择'}),self.user)
        self.assertEqual(original,self.card)
    def test_draft_ahead_does_not_complete(self):
        workflow.save_progress(self.card,dict(step=4,workflow_version=workflow.VERSION,complete=False,confirmed=True,data={'summary':'方法草稿'}),self.user)
        self.assertEqual(self.card['current_step'],1);self.assertEqual(self.card['steps'][3]['status'],'pending')
    def test_website_only_final_submission(self):
        # Explicit synthetic fixture; does not claim real teaching evidence.
        self.card['current_step']=6
        for st in self.card['steps'][:5]:st['status']='complete'
        d=dict(id='D',revision=1,activity_version=1,object_refs=[])
        self.card['research']['deliverables']=[d];self.card['research']['selected_deliverable']={'id':'D','revision':1}
        self.card['research']['objects']=[dict(id='DEF',kind='defense',status='confirmed',content={'deliverable_ref':{'id':'D','revision':1},'answer_text':'合成测试实际回答'})]
        self.card['steps'][4]['data']['deliverable_ref']={'id':'D','revision':1}
        b=dict(step=6,workflow_version=workflow.VERSION,confirmed=True,complete=True,data={'summary':'本人核对'},_coach=True)
        with self.assertRaises(PermissionError):workflow.save_progress(self.card,b,self.user)
        b['_coach']=False;workflow.save_progress(self.card,b,self.user)
        self.assertEqual(self.card['status'],'review');self.assertEqual(self.card['submitted_deliverable']['id'],'D')
    def test_duplicate_study_link_and_attachment_not_independent(self):
        self.card['materials']=[{'id':'URL','url':'https://example.test/a','title':'同一研究'}]
        self.card['files']=[{'id':'FILE','name':'同一研究','sha256':'abc'}]
        self.card['_student_messages']={'M':'合成原话'}
        rows=[dict(reference=ref,location='第1页',student_message_ref='M',supports='比较方法',cannot_claim='因果',question_impact='限定',reading_scope='excerpt') for ref in ('URL','FILE')]
        with self.assertRaisesRegex(ValueError,'同一研究'):workflow._reading(self.card,{'source_comparisons':rows})

    def test_old_defense_does_not_complete_new_proposal(self):
        self.card['research']['deliverables']=[dict(id='NEW',revision=1,activity_version=1,object_refs=[])]
        self.card['research']['selected_deliverable']={'id':'NEW','revision':1}
        self.card['research']['objects']=[dict(id='DEF',kind='defense',status='confirmed',content={'deliverable_ref':{'id':'OLD','revision':1},'answer_text':'旧稿实际回答','answer_ref':'M1'})]
        with self.assertRaisesRegex(ValueError,'答辩记录（尚未整理）'):
            workflow.validate_completion(self.card,5,{'summary':'不能冒用旧稿答辩'})

    def test_review_binds_fixed_submission_and_requirement(self):
        self.card.update(status='review',submitted_deliverable=dict(id='D',revision=1,activity_version=1))
        self.card['research']['deliverables']=[dict(id='D',revision=1,object_refs=[])]
        b=dict(decision='approve',value='价值',feasibility='可行',deliverable='计划',annual_acceptance='年度标准',owner='学生',due='2027-01-01',standard='验收')
        workflow.review(self.card,b,dict(role='teacher',name='老师'))
        self.assertEqual(self.card['review']['deliverable_ref']['revision'],1);self.assertEqual(self.card['status'],'approved')
if __name__=='__main__':unittest.main()
