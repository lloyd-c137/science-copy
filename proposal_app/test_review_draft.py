"""Teacher draft isolation and scoped review credentials over real HTTP."""
import json
import base64
import unittest
from contextlib import closing
from unittest.mock import Mock

from proposal_app import server
from proposal_app import test_service
from proposal_app.test_research_fixtures import seed_review


class ReviewDraftFlow(unittest.TestCase):
    setUp = test_service.ServiceFlow.setUp
    api = test_service.ServiceFlow.api
    login = test_service.ServiceFlow.login

    def ready(self):
        with closing(server.connect(self.srv.db_path)) as c, c:
            card=json.loads(c.execute('SELECT card FROM projects WHERE id=?',(self.pid,)).fetchone()[0])
            card['activity']={'version':1}
            seed_review(c,card,dict(id=card['student_id'],role='student',name=card['student_name']))
            c.execute('UPDATE projects SET card=? WHERE id=?',(server.dump(card),self.pid))
        return dict(project_version=card['version'],requirement_version=1,draft_revision=None,decision='supplement',
                    value='值得验证',feasibility='还需小试',deliverable='补交实际记录',
                    owner='学生',due='2027-01-20',step=5,evidence='已有问题记录',gaps='缺小试')

    def test_draft_is_private_and_does_not_publish(self):
        body=self.ready()
        before=self.api(self.path,self.student)
        self.assertEqual(self.api(self.path+'/review-draft',self.teacher),{'draft':None,'stale':False})
        result=self.api(self.path+'/review-draft',self.teacher,body)
        self.assertTrue(result['saved'])
        self.assertFalse(result['stale'])
        after=self.api(self.path,self.student)
        for key in ('status','version','review','history','steps'):
            self.assertEqual(before[key],after[key])
        self.assertNotIn('draft',after)
        self.api(self.path+'/review-draft',self.student,expect=403)
        self.api(self.path+'/review-draft',self.student,body,403)
        self.api(self.path+'/review-draft',self.other,expect=404)
        with closing(server.connect(self.srv.db_path)) as c,c:
            c.execute("INSERT INTO users SELECT 'U9','teacher9','另一老师','teacher',salt,pw FROM users WHERE id='U1'")
        outsider=self.login('teacher9')
        self.api(self.path+'/review-draft',outsider,body,404)

    def test_stale_project_and_requirements_are_rejected(self):
        body=self.ready()
        body['draft_revision']=self.api(self.path+'/review-draft',self.teacher,body)['draft']['revision']
        self.api(self.path+'/comments',self.teacher,{'text':'新证据'})
        self.assertTrue(self.api(self.path+'/review-draft',self.teacher)['stale'])
        self.api(self.path+'/review-draft',self.teacher,body,409)
        body['project_version']+=1
        body['draft_revision']=self.api(self.path+'/review-draft',self.teacher,body)['draft']['revision']
        self.api('/activities/'+self.aid,self.teacher,dict(version=1,title='新要求',requirements='修订',deadline='2027-01-20'))
        self.assertTrue(self.api(self.path+'/review-draft',self.teacher)['stale'])
        self.api(self.path+'/review-draft',self.teacher,body,409)

    def test_draft_revision_prevents_overwriting_another_reader(self):
        body=self.ready()
        missing=dict(body)
        missing.pop('draft_revision')
        self.api(self.path+'/review-draft',self.teacher,missing,422)
        first=self.api(self.path+'/review-draft',self.teacher,dict(body,draft_revision=''))['draft']
        self.api(self.path+'/review-draft',self.teacher,body,409)
        teacher_read=self.api(self.path+'/review-draft',self.teacher)['draft']
        ai_read=self.api(self.path+'/review-draft',self.teacher)['draft']
        teacher_body=dict(body,draft_revision=teacher_read['revision'],value='老师修订的判断')
        updated=self.api(self.path+'/review-draft',self.teacher,teacher_body)['draft']
        self.assertNotEqual(first['revision'],updated['revision'])
        self.api(self.path+'/review-draft',self.teacher,dict(body,draft_revision=ai_read['revision'],value='AI旧稿'),409)
        self.assertEqual(self.api(self.path+'/review-draft',self.teacher)['draft'],updated)
        self.api(self.path+'/review',self.teacher,dict(body,draft_revision=ai_read['revision'],version=body['project_version']),409)
        # A valid draft revision does not make an old project snapshot current.
        self.api(self.path+'/comments',self.teacher,{'text':'新增证据'})
        self.api(self.path+'/review-draft',self.teacher,dict(body,draft_revision=updated['revision']),409)
        # Nor does refreshing project_version allow an obsolete draft revision to win.
        self.api(self.path+'/review-draft',self.teacher,dict(body,draft_revision=ai_read['revision'],project_version=body['project_version']+1),409)
        retained=self.api(self.path+'/review-draft',self.teacher)
        self.assertEqual(retained['draft'],updated)
        self.assertTrue(retained['stale'])

    def test_validation_and_normal_publication(self):
        body=self.ready()
        for changes in ({'step':None},{'due':'bad'},{'value':''},{'decision':'unknown'}, {'project_version':True}):
            self.api(self.path+'/review-draft',self.teacher,dict(body,**changes),422)
        draft=self.api(self.path+'/review-draft',self.teacher,body)['draft']
        published=self.api(self.path+'/review',self.teacher,dict(body,draft_revision=draft['revision'],version=body['project_version']))
        student=self.api(self.path,self.student)
        self.assertEqual(student['review'],published['review'])
        self.assertEqual(student['review']['deliverable'],body['deliverable'])
        self.assertEqual(student['status'],'active')
        self.assertIsNone(self.api(self.path+'/review-draft',self.teacher)['draft'])

    def test_review_launch_token_only_reads_target_and_writes_drafts(self):
        body=self.ready()
        uploaded=self.api(self.path+'/files',self.student,dict(name='evidence.txt',content_base64=base64.b64encode(b'evidence').decode()))
        body['project_version']=uploaded['version']
        launcher=Mock()
        launcher.start.return_value={'status':'running'}
        launcher.read.return_value={'status':'idle'}
        self.srv.review_launcher=launcher
        self.api(self.path+'/review-coach',self.student,{},403)
        self.assertEqual(self.api(self.path+'/review-coach',self.teacher)['status'],'idle')
        self.api(self.path+'/review-coach',self.teacher,{'background':True})
        args=launcher.start.call_args.args
        token=args[3]
        self.assertEqual(args[0]['id'],'U1')
        self.assertEqual(args[1]['id'],self.pid)
        self.assertTrue(launcher.start.call_args.kwargs['background'])
        self.api(self.path,token)
        self.api(self.path+'/discussions',token)
        self.assertEqual(self.api(uploaded['files'][0]['url'].removeprefix('/api'),token),b'evidence')
        self.api(self.path+'/review-draft',token,body)
        for path,payload in ((self.path+'/review',body),(self.path+'/comments',{'text':'bad'}),
                             ('/activities',{}),('/activities/'+self.aid,{}),
                             (self.path+'/review-coach',{}),('/login',{'username':'teacher','password':'yanjiu123'})):
            self.api(path,token,payload,403)
        self.api('/home',token,expect=403)
        other_pid=next(p['id'] for p in self.api('/home',self.other)['projects'])
        other_file=self.api('/projects/'+other_pid+'/files',self.other,dict(name='private.txt',content_base64=base64.b64encode(b'private').decode()))['files'][0]
        self.api(other_file['url'].removeprefix('/api'),token,expect=403)
        self.api('/projects/'+other_pid,token,expect=403)
        self.api('/projects/'+other_pid+'/review-draft',token,body,403)
        manual=dict(body,version=body['project_version'])
        manual.pop('draft_revision')
        self.api(self.path+'/review',self.teacher,manual)
        self.api(self.path+'/review-coach',self.teacher,{},409)
        current=self.api(self.path,self.student)
        self.api(self.path+'/reset',self.student,dict(version=current['version'],confirmed=True))
        # Deleting a project must never turn its scoped credential into a full teacher session.
        self.api('/home',token,expect=403)
        self.api('/projects/'+other_pid,token,expect=403)

    def test_review_launcher_rejects_remote_host(self):
        self.ready()
        original=self.srv.server_address
        self.srv.server_address=('0.0.0.0',original[1])
        try:
            self.api(self.path+'/review-coach',self.teacher,expect=409)
            self.api(self.path+'/review-coach',self.teacher,{},409)
        finally:
            self.srv.server_address=original


if __name__=='__main__':
    unittest.main()
