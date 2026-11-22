"""Quality contracts exercised against independent HTTP projects and credentials."""
import json
import hashlib
import unittest
import uuid
from contextlib import closing
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from proposal_app import server, quality_records as quality
from proposal_app import test_service


class QualityFlow(unittest.TestCase):
    setUp = test_service.ServiceFlow.setUp
    api = test_service.ServiceFlow.api
    login = test_service.ServiceFlow.login

    def record(self, kind, data, expected=200, token=None, **extra):
        card=self.api(self.path,self.student)
        body=dict(kind=kind,record=data,version=card['version'],requirement_version=card['activity']['version'],request_id=uuid.uuid4().hex)
        body.update(extra)
        return self.api(self.path+'/quality',token or self.student,body,expected)

    def decide(self, card, decision='accepted', token=None, expected=200, **extra):
        body=dict(record_id=card['quality']['records'][-1]['id'],decision=decision,reason='我比较了代价后选择这样做',confirmed=True,
                  version=card['version'],requirement_version=card['activity']['version'],request_id=uuid.uuid4().hex)
        body.update(extra)
        req=Request(self.base+'/api'+self.path+'/quality-decision',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Cookie':'coach_session='+(token or self.student)})
        try: response=urlopen(req)
        except HTTPError as error: response=error
        with response:
            result=json.loads(response.read())
            self.assertEqual(response.status,expected,result)
            return result

    def coach(self):
        token=self.login('student')
        card=self.api(self.path,self.student)
        with closing(server.connect(self.srv.db_path)) as c, c:
            c.execute('INSERT INTO coach_sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),self.pid,card['current_step'],card['steps'][card['current_step']-1].get('cycle',1)))
        return token

    def proposal(self, **extra):
        return self.record('proposal',dict(text='比较两个时段',reason='可以区分时段差异',step=1,changes={'summary':'两个时段的路线用时有何不同？'}),**extra)

    def test_proposals_only_change_on_student_acceptance_and_survive_next_stage(self):
        original=self.api(self.path,self.student)
        proposed=self.proposal()
        self.assertEqual(proposed['steps'][0]['data'], original['steps'][0]['data'])
        deferred=self.decide(proposed,'deferred')
        accepted=self.decide(deferred)
        self.assertEqual(accepted['steps'][0]['data']['summary'],'两个时段的路线用时有何不同？')
        self.assertEqual(len(accepted['quality']['records'][-1]['decisions']),2)
        self.assertEqual(accepted['steps'][0]['cycle'],2)
        archive=self.srv.project_archive.enrich(accepted)
        self.assertIn('accepted',json.dumps(archive['quality']))
        root=self.srv.workspaces.visible('U2',self.pid)
        self.assertIn('两个时段', (root/'研究过程'/'依据与选择.md').read_text('utf-8'))
        self.decide(accepted,expected=422)

    def test_decision_requires_browser_student_and_current_baseline(self):
        coach=self.coach()
        proposed=self.proposal(token=coach)
        self.assertEqual(proposed['quality']['records'][-1]['author'],'AI 导师')
        self.decide(proposed,token=coach,expected=403)
        self.decide(proposed,token=self.teacher,expected=403)
        self.api(self.path+'/quality-decision',self.student,{},403)
        self.decide(proposed,confirmed=False,expected=422)
        self.api(self.path+'/comments',self.student,dict(text='并发补充',step=1))
        self.decide(proposed,expected=409)
        fresh=self.api(self.path,self.student)
        self.decide(fresh,'rejected')

    def test_rejected_empty_field_cannot_be_applied_by_coach(self):
        coach=self.coach()
        proposed=self.proposal(token=coach)
        rejected=self.decide(proposed,'rejected')
        body=dict(workflow_version='tanyue-v1',step=1,data={'summary':'两个时段的路线用时有何不同？'},complete=False,confirmed=False,
                  version=rejected['version'],requirement_version=1,request_id='blocked')
        self.api(self.path+'/progress',coach,body,409)
        self.api(self.path+'/revise',coach,dict(title='新题',reason='建议',confirmed=True,version=rejected['version'],request_id='revise'),409)
        self.assertEqual(self.api(self.path,self.student)['steps'][0]['data'].get('summary',''),'')

    def test_claim_origins_arithmetic_and_fabricated_student_evidence(self):
        claim=dict(text='缩小后21毫米，不应再次缩放',origin='ai_example',limitation='示例，不是实验结果',check='仅核算数字',calculation=dict(expression='210 / 10',expected='2.1',unit='mm'))
        card=self.record('claim',claim)
        calc=card['quality']['records'][-1]['calculation']
        self.assertEqual(calc['result'],'21')
        self.assertFalse(calc['passed'])
        self.record('claim',dict(claim,origin='measured',reference='other-file',location='第1行'),422)
        self.record('claim',dict(claim,origin='student',reference='invented'),422)
        self.record('support',dict(concept='比例',observation='会算',strategy='画图',outcome='有效',evidence_id='invented'),422)
        with patch.object(self.srv.project_archive,'read',return_value={'conversations':[{'messages':[{'role':'user','id':'m1','text':'我能用十倍关系解释'}]}],'feedback':[],'profile':{}}):
            supported=self.record('support',dict(concept='比例',observation='解释十倍关系',strategy='长度图',outcome='能解释新例',evidence_id='m1'))
            self.assertEqual(supported['quality']['records'][-1]['student_quote'],'我能用十倍关系解释')

    def test_idempotency_scope_stale_session_and_field_validation(self):
        card=self.record('session',dict(settled='已比较',unresolved='需要计时',next_action='学生计时',owner='学生'),request_id='once')
        repeat=self.record('session',dict(settled='已比较',unresolved='需要计时',next_action='学生计时',owner='学生'),request_id='once',version=card['version']-1)
        self.assertEqual(repeat['version'],card['version'])
        self.record('session',dict(settled='不同',unresolved='需要计时',next_action='学生计时',owner='学生'),409,request_id='once')
        self.record('proposal',dict(text='错误档位',reason='测试',step=3,changes={'tier':'不支持'}),422)
        self.record('session',dict(settled='已比较',unresolved='需要计时',next_action='学生计时',owner='学生'),404,token=self.other)
        coach=self.coach()
        other=next(p['id'] for p in self.api('/home',self.student)['projects'] if p['id'] != self.pid)
        file=self.api('/projects/'+other+'/files',self.student,dict(name='other.txt',content_base64='aGVsbG8='))['files'][-1]
        self.api(file['url'].removeprefix('/api'),coach,expect=403)
        self.api('/projects/'+other,coach,expect=403)
        proposed=self.proposal(token=coach)
        self.decide(proposed)
        self.record('session',dict(settled='旧会话',unresolved='无',next_action='无',owner='学生'),409,token=coach)

    def test_generated_file_cannot_be_measured_and_safe_calculator(self):
        file=self.api(self.path+'/files',self.student,dict(name='AI练习.csv',content_base64='MSwyLDM=',material_origin='ai_generated'))['files'][-1]
        self.record('claim',dict(text='测量结果',origin='measured',reference=file['id'],location='第1行',limitation='仅样例',check='已看'),422)
        for expression in ('__import__("os")', '1/0', 'True+1', '2**1000000'):
            with self.assertRaises(ValueError): quality.calculate(expression)
        self.assertEqual(quality.calculate('(0.1+0.2)*10'),'3.0')

    def test_calculation_correction_and_supplement_history_preserved(self):
        claim=dict(text='长度核算',origin='inference',limitation='只核算数字',check='已复算',calculation=dict(expression='210/10',expected='2.1',unit='mm'))
        card=self.record('claim',claim)
        self.assertTrue(quality.unresolved_calculations(card,1))
        corrected=self.record('claim',dict(claim,supersedes=card['quality']['records'][-1]['id'],calculation=dict(expression='210/10',expected='21',unit='mm')))
        self.assertFalse(quality.unresolved_calculations(corrected,6))
        proposed=self.proposal()
        with closing(server.connect(self.srv.db_path)) as connection, connection:
            raw=json.loads(connection.execute('SELECT card FROM projects WHERE id=?',(self.pid,)).fetchone()[0])
            raw['review']={'decision':'supplement','step':5,'deliverable':'旧题的实验'}
            connection.execute('UPDATE projects SET card=? WHERE id=?',(server.dump(raw),self.pid))
        accepted=self.decide(proposed)
        # A summary revision cannot rewrite the teacher's historical decision.
        self.assertEqual(accepted['review']['deliverable'],'旧题的实验')
        self.assertEqual(accepted['review']['decision'],'supplement')
        self.assertEqual(accepted['steps'][0]['data']['summary'],'两个时段的路线用时有何不同？')

    def test_existing_binding_token_is_enrolled_on_service_restart(self):
        token=self.login('student')
        root=self.srv.workspaces.visible('U2',self.pid)/'.coach'/'binding'
        root.mkdir(exist_ok=True)
        (root.parent/'active-stage.txt').write_text('1-1','utf-8')
        (root/'connection.json').write_text(json.dumps({'token':token,'server':self.base,'account':'U2'}),'utf-8')
        with closing(server.connect(self.srv.db_path)) as connection, connection:
            raw=json.loads(connection.execute('SELECT card FROM projects WHERE id=?',(self.pid,)).fetchone()[0])
            raw['current_step']=2
            connection.execute('UPDATE projects SET card=? WHERE id=?',(server.dump(raw),self.pid))
        restarted=server.serve(self.srv.db_path,0)
        restarted.server_close()
        with closing(server.connect(self.srv.db_path)) as connection, connection:
            binding=connection.execute('SELECT * FROM coach_sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            self.assertEqual(binding['project'],self.pid)
            self.assertEqual(binding['step'],1)
        self.proposal(token=token,expected=409)
        proposed=self.proposal()
        self.decide(proposed,token=token,expected=403)


if __name__ == '__main__': unittest.main()
