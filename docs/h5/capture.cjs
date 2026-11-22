// Capture current UI against a temporary example database, never the active service.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');
const output=path.join(__dirname,'images');fs.mkdirSync(output,{recursive:true});
const bootstrap=String.raw`
import json,sys
from proposal_app.test_stage_review import StageReviewHTTP, CompactResearchHTTP
class Example(CompactResearchHTTP):
 def deliverable(self):
  chapters=dict(background='近路不一定更准时：信号灯等待可能让每天的到校时间出现波动。希望在两条上学路线中找到更稳定的选择。',literature='比较两份阅读材料对平均用时和用时分布的处理，采用分布比较，保留观察研究的限制。',question='同一工作日时段，两条路线的用时波动有什么差别？信号灯等待时长可能是影响因素。',method='用两周交替记录两条路线的出发、到达与等待时刻，比较用时分布及迟到次数，同时记录天气和出发时间。',validation='先核对时间记录能否对齐，再确认校历允许连续记录。将记录任务安排在课程预算内。',limits='结果只描述本人两周内的通勤样本；出发时刻和天气可能影响比较，不能据此证明路线导致迟到。',references='阅读材料与原文位置见项目材料，比较判断见研究工作区。')
  return self.write('research-deliverable',dict(chapters=chapters,object_refs=[self.ref(k) for k in ('problem','rq','method')]))
c=StageReviewHTTP();c.setUp();r=Example(c)
try:
 original=r.progress
 r.progress=lambda n,data=None,expect=200:r.write('progress',dict(workflow_version='tanyue-v1',step=n,complete=False,confirmed=False,data=data or {}))
 r.stage_a()
 r.obj('question-second','question',dict(wording='出发时间怎样影响迟到？',importance='比较不同影响因素',question_type='measurement'))
 print('READY '+json.dumps({'base':c.base,'pid':c.pid}),flush=True)
 for line in sys.stdin:
  if line.strip()=='quit':break
  r.card=c.api(c.path,c.student);r.progress=original
  r.write('research-review',dict(step=1,complete=True,confirmed=True,edits=[],data={}),web=True)
  r.stage_b();r.stage_c();r.stage_d();r.stage_e();r.progress(6)
  print('REVIEW',flush=True)
finally:c.doCleanups()
`;
const service=spawn('python',['-u','-B','-c',bootstrap],{cwd:path.resolve(__dirname,'../..'),stdio:['pipe','pipe','pipe']});
let out='',err='',browser;service.stdout.on('data',x=>out+=x);service.stderr.on('data',x=>err+=x);
async function wait(re){const start=Date.now();while(Date.now()-start<45000){const m=out.match(re);if(m)return m;if(service.exitCode!==null)throw Error(err);await new Promise(r=>setTimeout(r,100));}throw Error('Capture timeout '+err.slice(-1500));}
(async()=>{
 const meta=JSON.parse((await wait(/READY (.+)\r?\n/))[1]);
 browser=await chromium.launch({channel:'chrome',headless:true});
 async function login(role){const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});await page.goto(meta.base);await page.locator('[name=username]').fill(role);await page.locator('[name=password]').fill('yanjiu123');await page.locator('#login-form button').click();await page.waitForFunction(()=>!!state.user);await page.evaluate(id=>openProject(id),meta.pid);return page;}
 const student=await login('student');await student.locator('[data-action=research-progress]').click();await student.locator('.stage-review-footer').waitFor();await student.screenshot({path:path.join(output,'student-review.png'),animations:'disabled'});
 await student.locator('[data-review-object=question] [data-action=research-review-edit]').click();await student.locator('[name=review-question-wording]').fill('两条上学路线，哪条用时更稳定？');await student.screenshot({path:path.join(output,'student-edit.png'),animations:'disabled'});
 await student.close();service.stdin.write('review\n');await wait(/REVIEW/);
 const teacher=await login('teacher');await teacher.locator('[data-action=review]').first().waitFor();await teacher.screenshot({path:path.join(output,'teacher-review.png'),animations:'disabled'});
 console.log('Captured current student review/edit and teacher fixed submission.');
})().catch(e=>{console.error(e,err.slice(-1500));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();service.stdin.write('quit\n');service.stdin.end();});
