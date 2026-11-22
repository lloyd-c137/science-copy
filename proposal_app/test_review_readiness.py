import unittest
from copy import deepcopy
from proposal_app import workflow, research_service
from proposal_app.test_research_store import fixture, create


class ReadinessTests(unittest.TestCase):
    def test_complete_check_draft_is_prepared_without_confirmation_or_writes(self):
        from proposal_app import research_schema as schema
        c,card,user=fixture();self.addCleanup(c.close)
        card['current_step']=4
        card['steps'][3]['data']={key:'已有依据' for key,_ in workflow.TASKS[3][3]}
        def ref(kind):return dict(type='object',id=kind,revision=1)
        objects=[dict(id=k,kind=k,revision=1,status='confirmed',content=dict.fromkeys(schema.REQUIRED[k],'已核实')) for k in ('rq','hypothesis','method')]
        objects[1]['content']['not_applicable_reason']='描述性比较'
        check=dict(id='check',kind='check',revision=1,status='draft',content=dict(scope_refs=[ref(k) for k in ('rq','hypothesis','method')],reasoned_findings=['有依据的判断'],reviewer_response='已有本人回应',unresolved=[],mechanical_findings=[],**dict.fromkeys(schema.CHECK_JUDGMENTS,'有依据')))
        card['research'].update(objects=objects+[check],links=[dict(id=rel,relation=rel,status='confirmed',from_ref=ref(a),to_ref=ref(b)) for rel,a,b in [('explains','hypothesis','rq'),('operationalized_by','rq','method')]])
        before=deepcopy(card)
        self.assertTrue(workflow.review_readiness(card)['prepared'])
        self.assertFalse(workflow.review_readiness(card)['confirmed'])
        self.assertEqual(before,card)
        with self.assertRaises(ValueError):workflow.validate_completion(card,4,card['steps'][3]['data'])
        for bad in ('missing_judgment','stale_ref','unresolved','needs_review'):
            altered=deepcopy(card);obj=altered['research']['objects'][-1]
            if bad=='missing_judgment':obj['content'].pop('rq_alignment')
            if bad=='stale_ref':obj['content']['scope_refs'][0]['revision']=99
            if bad=='unresolved':obj['content']['unresolved']=['尚未验证']
            if bad=='needs_review':obj['needs_review']=True
            self.assertFalse(workflow.review_readiness(altered)['prepared'],bad)

    def test_missing_and_unconfirmed_reported_together_without_mutation(self):
        card={'current_step':1,'research':{'objects':[dict(id='Q',kind='question',status='draft',revision=1,content=dict(wording='为什么会误解？',question_type='open',importance='保留原意'))]}}
        before=deepcopy(card)
        result=workflow.review_readiness(card)
        self.assertFalse(result['prepared'])
        self.assertEqual([i['status'] for i in result['items'][:2]],['missing','confirm'])
        with self.assertRaisesRegex(ValueError,'原始观察.*尚未整理.*探索问题.*待本人确认'):
            workflow.validate_completion(card,1,dict(summary='已讨论',selection_reason='我的理由'))
        self.assertEqual(card,before)

    def test_draft_preparation_does_not_confirm_student_records(self):
        c,card,user=fixture()
        self.addCleanup(c.close)
        card['steps'][0]['data']=dict(summary='已有讨论',selection_reason='保留原意')
        research_service.mutate(c,card,'research-objects',{'objects':[
            dict(id='C',kind='curiosity',expected_revision=0,content=dict(observation='学生转述消息误解',why_care='担心意思改变',student_quote_ref='M')),
            dict(id='Q',kind='question',expected_revision=0,content=dict(wording='怎样保留原意？',question_type='open',importance='减少误解'))]},user,coach=True,student_messages={'M':'我看到材料里有人被误解，想保留原意'})
        review=card['research']['review_readiness']
        self.assertTrue(review['prepared']);self.assertFalse(review['confirmed'])
        self.assertEqual([o['status'] for o in card['research']['objects']],['draft','draft'])
        self.assertEqual(card['research']['objects'][0]['content']['student_quote'],'我看到材料里有人被误解，想保留原意')
        card['research']['objects'][0]['content'].pop('why_care')
        self.assertFalse(workflow.review_readiness(card)['prepared'])

    def test_superseding_only_pending_suggestions_for_same_object(self):
        c,card,user=fixture();self.addCleanup(c.close)
        create(c,card,user,'T')
        payload={'record':dict(target_object_id='T',expected_revision=1,text='旧建议',reason='理由')}
        old=research_service.object_proposal(card,payload,user);card['quality']['records'].append(old)
        payload['record'].update(text='新建议',supersedes_proposals=[old['id']])
        self.assertEqual(research_service.object_proposal(card,payload,user)['supersedes_proposals'],[old['id']])
        old['status']='accepted'
        with self.assertRaisesRegex(ValueError,'尚未决定'):research_service.object_proposal(card,payload,user)
