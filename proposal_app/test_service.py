"""Exercise the actual HTTP contract against an isolated SQLite store."""
import base64
from contextlib import closing
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from proposal_app import server
from proposal_app.test_research_fixtures import ResearchHTTP


class ServiceFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.srv = server.serve(Path(self.temp.name) / "test.sqlite3",0)
        worker = threading.Thread(target=self.srv.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_port}"
        self.student = self.login("student")
        self.teacher = self.login("teacher")
        self.other = self.login("student2")
        roster = self.api("/home",self.teacher)
        activity = self.api("/activities",self.teacher,dict(title="校园研究",requirements="解释本人的研究选择",deadline="2027-01-20",student_ids=[p["id"] for p in roster["students"]]))
        self.aid=activity["id"]
        self.pid=next(p["id"] for p in self.api("/home",self.student)["projects"] if p["activity_id"]==self.aid)
        self.path="/projects/"+self.pid
        self.api(self.path+"/workspace",self.student,{"parent":str(Path(self.temp.name)/"student-projects")})

    def api(self,path,auth=None,body=None,expect=200):
        headers={"Content-Type":"application/json"}
        if auth:
            if auth.startswith("cookie:"): headers["Cookie"]="coach_session="+auth[7:]
            else: headers["Authorization"]="Bearer "+auth
        req=Request(self.base+"/api"+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:
            res=urlopen(req)
        except HTTPError as err:
            res=err
        with res:
            raw=res.read()
            self.assertEqual(res.status,expect,raw[:1000])
            return json.loads(raw) if res.headers.get_content_type()=="application/json" else raw

    def login(self,name):
        return self.api("/login",body=dict(username=name,password="yanjiu123"))["token"]

    def test_project_files_are_read_only_and_account_scoped(self):
        card=self.api(self.path,self.student)
        root=self.srv.workspaces.visible(card['student_id'],self.pid)
        note=root/'我的笔记'/'私有观察.md';note.write_text('我的猜想：先比较改错时间。','utf-8')
        before=note.read_bytes()
        found=self.api(self.path+'/search-project-files',self.student,{'query':'改错'})
        self.assertEqual(found['files'][0]['path'],'我的笔记/私有观察.md')
        read=self.api(self.path+'/read-project-file',self.student,{'path':found['files'][0]['path']})
        self.assertEqual(read['text'],before.decode())
        self.api(self.path+'/search-project-files',self.other,{},404)
        self.api(self.path+'/read-project-file',self.student,{'path':'.coach/project.json'},422)
        self.assertEqual(note.read_bytes(),before)
        self.assertEqual(self.api(self.path,self.student)['version'],card['version'])

    def save(self,card,step,data,complete=True,expect=200,**other):
        b=dict(workflow_version="tanyue-v1",version=card["version"],requirement_version=card["activity"]["version"],confirmed=True,request_id=uuid.uuid4().hex,step=step,data=data,complete=complete)
        b.update(other)
        return self.api(self.path+"/progress","cookie:"+self.student,b,expect)

    def test_sources_are_private_shared_with_teacher_and_retry_safe(self):
        body=dict(title='测试材料',url='https://example.org/paper',help='支持比较方法',limit='不能直接外推',request_id='source-1')
        self.api(self.path+'/sources',self.other,body,404)
        self.api(self.path+'/sources',self.teacher,body,403)
        self.api(self.path+'/sources',self.student,body)
        self.api(self.path+'/sources',self.student,dict(body,help='更新方法说明',request_id='source-2'))
        self.api(self.path+'/sources',self.student,body)
        card=self.api(self.path,self.teacher)
        self.assertEqual(card['materials'][0]['help'],'更新方法说明')
        self.assertEqual(len(card['reading_items']['files']),1)
        self.assertIn('required_judgment',card['teaching_brief'])
        self.api(self.path+'/sources',self.student,dict(body,help='编号冲突'),422)

    def test_folder_picker_releases_database_write_lock(self):
        entered=threading.Event();release=threading.Event();result=[]
        def pick(user):
            entered.set();release.wait(5);return ''
        with patch.object(self.srv.workspaces,'pick',side_effect=pick):
            worker=threading.Thread(target=lambda:result.append(self.api(self.path+'/pick-folder',self.student,{})))
            worker.start();self.assertTrue(entered.wait(2))
            try:
                with closing(server.connect(self.srv.db_path)) as connection:
                    connection.execute('PRAGMA busy_timeout=300')
                    connection.execute('BEGIN IMMEDIATE')
                    connection.rollback()
            finally:
                release.set();worker.join(3)
            self.assertEqual(result,[{'path':''}])

    def test_new_unconfigured_project_rejects_archive_only_writes(self):
        card=self.api(self.path,self.student)
        fresh=self.api(self.path+'/reset',self.student,{'version':card['version'],'confirmed':True})
        self.api('/projects/'+fresh['id']+'/sources',self.student,
                 dict(title='模拟文章',url='https://example.org/paper',help='待保存',limit='无',request_id='no-folder'),409)

    def test_personal_access_and_stale_writes(self):
        self.api(self.path,self.other,expect=404)
        self.api(self.path+"/comments",self.other,{"text":"越权","step":1},404)
        p=self.api(self.path,self.student)
        self.save(p,1,{"origin":"我昨天又迟到了"},expect=422)
        self.save(p,1,{"origin":"两个路口等灯时间不同"},complete=True,confirmed=False,expect=422)
        req=dict(workflow_version="tanyue-v1",requirement_version=p["activity"]["version"],step=1,data={"origin":"我昨天又迟到了"},complete=False,confirmed=False,version=1,request_id="once")
        a=self.api(self.path+"/progress",self.student,req)
        b=self.api(self.path+"/progress",self.student,req)
        self.assertEqual(a["result_id"],b["result_id"])
        self.assertEqual(b["version"],2)
        self.api(self.path+"/progress",self.student,dict(req,request_id="other"),409)
        self.api(self.path+"/progress",self.student,dict(req,data={"origin":"另一件事"}),409)
        self.api("/activities/"+self.aid,self.teacher,dict(version=1,title="校园研究",requirements="新标准",deadline="2027-01-20"))
        self.save(a,1,{"origin":"等待补查"},False,409)
        old=self.api(self.path+"/versions/1",self.student)
        self.assertEqual(old["activity"]["requirements"],"解释本人的研究选择")

    def test_reset_isolated_project_and_rejects_old_conversation(self):
        card=self.save(self.api(self.path,self.student),1,{"origin":"这是一份需要清空的观察"},False)
        card=self.api(self.path+"/files",self.student,dict(version=card["version"],request_id="reset-file",name="记录.txt",content_base64=base64.b64encode(b"original").decode()))
        old_file=card["files"][0]["id"]
        before_other=self.api("/home",self.other)["projects"]
        payload=dict(version=card["version"],confirmed=True)
        self.api(self.path+"/reset",self.other,payload,404)
        self.api(self.path+"/reset",self.teacher,payload,403)
        self.api(self.path+"/reset",self.student,dict(payload,confirmed=False),422)
        self.api(self.path+"/reset",self.student,dict(payload,version=0),409)
        fresh=self.api(self.path+"/reset",self.student,payload)
        self.assertNotEqual(fresh["id"],self.pid)
        self.assertEqual(fresh["current_step"],1)
        self.assertTrue(all(not s["data"] for s in fresh["steps"]))
        self.assertFalse(fresh["files"] or fresh["comments"] or fresh["history"] or fresh["review"])
        self.assertEqual(fresh["activity"]["requirements"],card["activity"]["requirements"])
        self.api(self.path,self.student,expect=404)
        self.api(self.path+"/progress",self.student,dict(version=card["version"],confirmed=True,step=1,complete=False,data={"origin":"旧会话晚到的保存"}),404)
        self.api("/files/"+old_file,self.student,expect=404)
        self.assertEqual(self.api("/home",self.other)["projects"],before_other)
        self.assertEqual(self.api('/projects/'+fresh['id']+'/discussions',self.student)['conversations'],[])
        self.assertEqual(self.api('/projects/'+fresh['id']+'/coach',self.student)['status'],'idle')

    def test_coach_launch_uses_authenticated_project(self):
        self.api(self.path+"/coach",body={},expect=401)
        self.api(self.path+"/coach",self.other,{},404)
        self.api(self.path+"/coach",self.teacher,{},403)
        with patch.object(self.srv.coach_launcher,"start",return_value={"status":"starting"}) as start:
            self.assertEqual(self.api(self.path+"/coach",self.student,{"student_id":"U3"}),{"status":"starting"})
            user, card, origin, token = start.call_args.args
            self.assertEqual(user["id"], card["student_id"])
            self.assertEqual(card["id"],self.pid)
            self.assertEqual(origin,self.base)
            self.assertEqual(self.api(self.path,token)["id"],self.pid)
        self.assertEqual(self.api(self.path+"/coach",self.student),{"status":"idle"})

    def test_evidence_and_review_loop(self):
        flow=ResearchHTTP(self)
        flow.stage_a();flow.stage_b();flow.stage_c();flow.stage_d()
        p=flow.card
        upload=dict(name="两次试测.csv",content_base64=base64.b64encode(b"x,y\n1,2").decode(),request_id="file_once",version=p["version"])
        p=self.api(self.path+"/files",self.student,upload)
        self.assertEqual(p["result_id"],self.api(self.path+"/files",self.student,upload)["result_id"])
        self.assertEqual(len(p["files"]),1)
        file=p["files"][0]
        self.api("/files/"+file["id"],self.other,expect=404)
        self.assertEqual(self.api("/files/"+file["id"],self.teacher),b"x,y\n1,2")
        flow.card=p;flow.stage_e()
        final=dict(version=flow.card['version'],requirement_version=1,request_id='final-submit',workflow_version='tanyue-v1',step=6,complete=True,confirmed=True,data={'summary':'核对固定稿'})
        self.api(self.path+'/progress',self.student,final,403)
        p=self.api(self.path+'/progress','cookie:'+self.student,final)
        self.assertEqual(p['status'],'review')
        submitted=p['submitted_deliverable']
        b=dict(decision="supplement",value="有本班价值",feasibility="缺时刻",owner="学生",due="2027-01-10",deliverable="补充一项对照",step=5,version=p["version"])
        self.api(self.path+"/review",self.student,b,403)
        p=self.api(self.path+"/review",self.teacher,b)
        self.assertEqual([s["status"] for s in p["steps"]],["complete"]*4+["active","pending"])
        self.assertEqual(p['review']['deliverable_ref'],submitted)
        flow.card=p;flow.deliverable();flow.defense();flow.progress(5,{'summary':'回应补证意见'});p=flow.progress(6)
        self.assertNotEqual(p['submitted_deliverable']['id'],submitted['id'])
        roster=next(x for x in self.api('/home',self.teacher)['projects'] if x['id']==p['id'])
        self.assertEqual(roster['status'],'review');self.assertEqual(roster['review']['decision'],'supplement')
        # A focused source supplement reopens B plus final preparation, preserving A/C/D.
        p=self.api(self.path+'/review',self.teacher,dict(b,step=2,version=p['version']))
        self.assertEqual([s['status'] for s in p['steps']],['complete','active','complete','complete','pending','pending'])
        flow.card=p;flow.progress(2);self.assertEqual(flow.card['current_step'],5)
        flow.deliverable();flow.defense();flow.progress(5);p=flow.progress(6)
        self.api(self.path+"/review",self.teacher,dict(decision="approve",value="有价值",version=p['version']),422)
        p=self.api(self.path+"/review",self.teacher,dict(b,decision="approve",version=p["version"],annual_acceptance="抽查数据",standard="对照完整"))
        self.assertEqual(p["status"],"approved")
        self.assertEqual(p['review']['deliverable_ref'],p['submitted_deliverable'])

    def test_all_stage_preflight_detects_completion_gaps(self):
        from copy import deepcopy
        from proposal_app import workflow
        flow=ResearchHTTP(self);base=flow.ready()
        base['_student_messages']=flow.messages
        for stage in range(1,7):
            with self.subTest(stage=stage):
                self.assertTrue(workflow.review_readiness(base,stage)['confirmed'])
                broken=deepcopy(base);broken['steps'][stage-1]['data'].pop('summary',None)
                if stage in (5,6):
                    self.assertTrue(workflow.review_readiness(broken,stage)['prepared'])
                    continue
                self.assertFalse(workflow.review_readiness(broken,stage)['prepared'])
                with self.assertRaises(ValueError):workflow.validate_completion(broken,stage,broken['steps'][stage-1]['data'])
        def fault(stage,edit):
            broken=deepcopy(base);edit(broken)
            self.assertFalse(workflow.review_readiness(broken,stage)['prepared'])
            with self.assertRaises((ValueError,server.research_service.Conflict)):
                workflow.validate_completion(broken,stage,broken['steps'][stage-1]['data'])
        fault(1,lambda p:p['research'].update(objects=[o for o in p['research']['objects'] if o['kind']!='curiosity']))
        fault(2,lambda p:p['research'].update(links=[l for l in p['research']['links'] if l['relation']!='groups_into']))
        fault(3,lambda p:p['steps'][2]['data'].update(source_comparisons=p['steps'][2]['data']['source_comparisons'][:1]))
        fault(3,lambda p:p['steps'][2]['data']['source_comparisons'][0].update(student_message_ref='not-a-student-message'))
        fault(3,lambda p:p['research'].update(links=[l for l in p['research']['links'] if l['relation']!='explains']))
        fault(4,lambda p:next(o for o in p['research']['objects'] if o['kind']=='check')['content'].pop('rq_alignment'))
        fault(4,lambda p:next(o for o in p['research']['objects'] if o['kind']=='method').update(revision=999))
        fault(5,lambda p:next(o for o in p['research']['objects'] if o['kind']=='defense')['content'].update(deliverable_ref={'id':'old','revision':1}))
        fault(6,lambda p:p['steps'][4]['data'].update(deliverable_ref={'id':'old','revision':1}))
        fault(6,lambda p:p['steps'][2].update(status='pending'))
        # A complete relation proposal can be personally reviewed before completion.
        pending=deepcopy(base);obj=next(o for o in pending['research']['objects'] if o['kind']=='problem')
        link=next(l for l in pending['research']['links'] if l['relation']=='groups_into');link['status']='draft'
        pending['quality']['records'].append(dict(id='pending-link',kind='proposal',status='pending',target_object_id=obj['id'],expected_revision=obj['revision'],requirement_version=pending['activity']['version'],content_patch={'set':{},'remove':[]},relation_changes={'activate_draft_ids':[link['id']]},relation_baselines={link['id']:deepcopy(link)}))
        before=deepcopy(pending);result=workflow.review_readiness(pending,2)
        self.assertTrue(result['prepared']);self.assertFalse(result['confirmed']);self.assertEqual(pending,before)
        pending['quality']['records'][-1]['expected_revision']=999
        self.assertFalse(workflow.review_readiness(pending,2)['prepared'])

    def test_review_preparation_and_personal_confirmation(self):
        flow=ResearchHTTP(self)
        flow.write('research-objects',{'objects':[dict(id='question',kind='question',expected_revision=0,content=dict(wording='怎样避免误解？',question_type='open',importance='保留原意'))]})
        self.assertFalse(flow.card['research']['review_readiness']['prepared'])
        failure=flow.write('progress',dict(step=1,complete=True,confirmed=True,workflow_version='tanyue-v1',data=dict(summary='已有讨论',selection_reason='保留原意')),expect=422,web=True)
        self.assertIn('原始观察',failure['error']);self.assertIn('探索问题',failure['error'])
        flow.write('research-objects',{'objects':[dict(id='curiosity',kind='curiosity',expected_revision=0,content=dict(observation='学生转述',why_care='避免误解',student_quote_ref='observation'))]})
        flow.write('progress',dict(step=1,complete=False,confirmed=False,workflow_version='tanyue-v1',data=dict(summary='已有讨论',selection_reason='保留原意')))
        self.assertTrue(flow.card['research']['review_readiness']['prepared'])
        self.assertFalse(flow.card['research']['review_readiness']['confirmed'])
        record=dict(target_object_id='question',expected_revision=1,text='核对问题',reason='整理已有讨论')
        flow.write('quality',dict(kind='proposal',record=record))
        old=flow.card['quality']['records'][-1]['id']
        flow.write('quality',dict(kind='proposal',record=dict(record,text='核对最新问题',supersedes_proposals=[old])))
        self.assertEqual(flow.card['quality']['records'][-2]['status'],'superseded')
        latest=flow.card['quality']['records'][-1]['id']
        flow.write('quality-decision',dict(record_id=latest,decision='accepted',reason='我的判断',confirmed=True),expect=403)
        flow.write('quality-decision',dict(record_id=latest,decision='accepted',reason='我的判断',confirmed=True),web=True)
        flow.confirm('curiosity')
        self.assertTrue(flow.card['research']['review_readiness']['confirmed'])
        flow.progress(1,dict(summary='学生核对后的成果',selection_reason='我选择继续'))
        self.assertEqual(flow.card['current_step'],2)

    def test_completed_coach_request_retries_original_receipt_only(self):
        flow=ResearchHTTP(self)
        flow.obj('curiosity','curiosity',dict(observation='现象',why_care='关心',student_quote_ref='observation'))
        flow.obj('question','question',dict(wording='问法',question_type='open',importance='原因'))
        with patch.object(self.srv.coach_launcher,'start',return_value={'status':'starting'}) as start:
            self.api(self.path+'/coach',self.student,{})
            token=start.call_args.args[3]
        p=flow.card
        self.api(self.path+'/research-recheck',self.student,dict(object_id='question',expected_revision=2,reason='不能由Bearer替本人复核'),403)
        body=dict(version=p['version'],requirement_version=1,request_id='coach-complete',workflow_version='tanyue-v1',step=1,complete=True,confirmed=True,data={'summary':'合成完成','selection_reason':'本人已选'})
        self.api(self.path+'/progress',token,body,403)
        first=self.api(self.path+'/progress','cookie:'+self.student,body)
        self.assertEqual(first['current_step'],2)
        retry=self.api(self.path+'/progress','cookie:'+self.student,body)
        self.assertEqual(retry,first)
        self.api(self.path+'/progress',token,dict(body,request_id='new-after-complete'),403)
        self.api(self.path+'/progress','cookie:'+self.student,dict(body,data={'summary':'编号冲突'}),409)
    def test_changed_activity_reopens_completed_evidence_and_blocks_old_review(self):
        flow=ResearchHTTP(self);p=flow.ready()
        old_objects=p['research']['objects'];old_submission=p['submitted_deliverable']
        unchanged=self.api('/activities/'+self.aid,self.teacher,dict(version=1,title='校园研究',requirements='解释本人的研究选择',deadline='2027-01-20'))
        self.assertEqual(unchanged['version'],1)
        self.assertEqual(self.api(self.path,self.student)['version'],p['version'])
        self.api('/activities/'+self.aid,self.teacher,dict(version=1,title='仅修改标题',requirements='解释本人的研究选择',deadline='2027-01-20'))
        renamed=self.api(self.path,self.student)
        self.assertEqual([st['status'] for st in renamed['steps']],['complete']*4+['active','pending'])
        self.assertEqual(renamed['steps'][3]['requirement_version'],2)
        self.api('/activities/'+self.aid,self.teacher,dict(version=2,title='校园研究',requirements='须追加独立条件核对',deadline='2027-01-20'))
        current=self.api(self.path,self.student)
        self.assertEqual(current['status'],'active');self.assertEqual(current['current_step'],1)
        self.assertEqual([st['status'] for st in current['steps']],['active']+['pending']*5)
        self.assertEqual(current['research']['objects'],old_objects)
        self.assertEqual(current['submitted_deliverable'],old_submission)
        self.assertTrue(current['steps'][2]['data']['source_comparisons'])
        b=dict(decision='approve',version=current['version'],value='价值',feasibility='可行',deliverable='任务',annual_acceptance='验收',owner='学生',due='2027-01-01',standard='标准')
        self.api(self.path+'/review',self.teacher,b,409)
        self.save(current,6,{'summary':'不能跳过重核'},expect=409)

    def test_topic_change_preserves_material_and_original_reason(self):
        flow=ResearchHTTP(self);flow.stage_a()
        p=self.api(self.path+"/comments",self.teacher,dict(step=2,text="哪项结果会改变你明早的选择？"))
        version=p['version'];flow.card=p
        self.api(self.path+'/revise',self.student,dict(title='绕过对象确认',reason='不应生效',confirmed=True,request_id='bad-revise',version=version),422)
        p=flow.confirm('question',patch={'set':{'wording':'哪条路线的到校时间更稳定？'},'remove':[]})
        self.assertEqual(p['current_step'],1);self.assertEqual(p['comments'][0]['step'],2)
        old=self.api(self.path+'/versions/'+str(version),self.student)
        question=next(o for o in old['research']['objects'] if o['id']=='question')
        self.assertEqual(question['content']['wording'],'近路更稳定吗？')
        current=next(o for o in p['research']['objects'] if o['id']=='question')
        self.assertEqual(current['content']['wording'],'哪条路线的到校时间更稳定？')
        self.assertEqual(p['quality']['records'][-1]['decision_reason'],'合成测试：本人核对依据后选择')


if __name__=="__main__":
    unittest.main()
