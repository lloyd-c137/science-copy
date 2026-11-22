// Isolated HTTP + Chrome acceptance; never changes the user's current projects.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const output=path.resolve(process.env.STAGE_REVIEW_OUTPUT||'proposal_app/local_data/browser-verification');fs.mkdirSync(output,{recursive:true});
const bootstrap=String.raw`
import json,sys
from proposal_app.test_stage_review import StageReviewHTTP, CompactResearchHTTP
class Preview(CompactResearchHTTP):
 def progress(self,n,data=None,expect=200):
  if expect!=200:return self.card
  return self.write('progress',dict(workflow_version='tanyue-v1',step=n,complete=False,confirmed=False,data=data or {'summary':'已讨论并整理的阶段小结'}))
c=StageReviewHTTP();c.setUp();r=Preview(c)
try:
 r.stage_a()
 r.obj('question-second','question',dict(wording='出门时间怎样影响迟到？',importance='比较不同影响因素',question_type='measurement'))
 print('READY '+json.dumps({'base':c.base,'pid':c.pid}),flush=True)
 for line in sys.stdin:
  command=line.strip()
  if command=='quit':break
  r.card=c.api(c.path,c.student)
  getattr(r,'stage_'+command)() if command in 'bcde' else r.progress(6)
  print('SEEDED '+command,flush=True)
finally:c.doCleanups()
`;
const service=spawn('python',['-u','-B','-c',bootstrap],{cwd:path.resolve('.'),stdio:['pipe','pipe','pipe']});
let stdout='',stderr='';service.stdout.on('data',x=>stdout+=x);service.stderr.on('data',x=>stderr+=x);
async function waitForText(re){const start=Date.now();while(Date.now()-start<30000){const m=stdout.match(re);if(m)return m;if(service.exitCode!==null)throw Error(stderr);await new Promise(r=>setTimeout(r,100));}throw Error('Fixture timeout '+stderr.slice(-2000));}
let browser;const checks=[],errors=[];
(async()=>{
 const setup=JSON.parse((await waitForText(/READY (.+)\r?\n/))[1]);
 browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(12000);page.on('pageerror',e=>errors.push(String(e)));
 await page.route(/\/api\/projects\/[^/]+\/(?:coach|review-coach)(?:\?.*)?$/,r=>r.fulfill({json:{status:'idle'}}));
 await page.goto(setup.base);await page.locator('[name=username]').fill('student');await page.locator('[name=password]').fill('yanjiu123');await page.locator('#login-form button').click();await page.waitForFunction(()=>!!state.user);await page.evaluate(pid=>openProject(pid),setup.pid);
 async function open(){
  assert.equal(await page.locator('.focus-task').getByText(/^(打开研究工作区|讨论文件夹)$/).count(),0);
  await page.locator('[data-action=research-progress]').click();
  await page.locator('[data-form=research-stage-review]').waitFor();
 }
 async function shot(name,width){await page.setViewportSize({width,height:1000});await page.screenshot({path:path.join(output,name+'.png'),animations:'disabled'});assert(await page.evaluate(()=>sheet.scrollWidth<=sheet.clientWidth+1),name+' overflow');}
 assert.equal(await page.locator('.quality-panel').count(),0);
 assert.equal(await page.locator('.review-attention').evaluate(el=>getComputedStyle(el).animationName),'research-review-breathe');
 await page.emulateMedia({reducedMotion:'reduce'});
 assert.equal(await page.locator('.review-attention').evaluate(el=>getComputedStyle(el).animationName),'none');
 checks.push('Review entry breathing animation preserved; reduced motion supported');
 await open();assert.equal(await page.locator('#sheet input[type=checkbox]').count(),0);assert.equal(await page.locator('#sheet .stage-review-section').count(),2);
 assert(!/形成过程|关联批注|聚焦讨论|关联依据|本人核对|第.*版/.test(await page.locator('#sheet').innerText()));
 await shot('a-desktop',1440);await shot('a-mobile',375);
 const recordOrder=await page.locator('#sheet [data-review-object]').evaluateAll(els=>els.map(el=>el.dataset.reviewObject));
 await page.locator('[data-review-object=question] [data-action=research-review-edit]').click();await page.locator('[name=review-question-wording]').fill('两条路线在工作日的用时波动有什么差别？');await shot('a-mobile-edit',375);
 assert(await page.locator('[data-review-object=question] [data-action=research-review-save]').evaluate(el=>el.matches('.primary:enabled')));
 await page.locator('.stage-review-stage [data-action=research-review-edit]').click();
 await page.locator('[name=review-stage-selection_reason]').fill('先研究用时波动，帮助安排出门时间');
 assert(await page.locator('#sheet [type=submit]').isDisabled());
 await page.locator('[data-review-object=question] [data-action=research-review-save]').click();
 await page.waitForFunction(()=>sheet.open&&state.project.current_step===1&&researchObjects().find(o=>o.id==='question').status==='confirmed');
 assert.deepEqual(await page.locator('#sheet [data-review-object]').evaluateAll(els=>els.map(el=>el.dataset.reviewObject)),recordOrder,'saving the first item must not reorder records');
 assert.equal(await page.locator('[name=review-stage-selection_reason]').inputValue(),'先研究用时波动，帮助安排出门时间');
 assert.equal(await page.evaluate(()=>researchObjects().find(o=>o.id==='curiosity').status),'draft');
 assert(await page.locator('[data-review-object=question] [data-action=research-review-edit]').isVisible());
 await page.locator('.stage-review-stage [data-action=research-review-save]').click();
 await page.waitForFunction(()=>sheet.open&&state.project.current_step===1&&state.project.steps[0].data.selection_reason==='先研究用时波动，帮助安排出门时间');
 // Saved entries stay editable, and cancelling one edit does not submit the stage.
 await page.locator('[data-review-object=question] [data-action=research-review-edit]').click();
 await page.locator('[name=review-question-wording]').fill('不保存的修改');
 await page.locator('[data-review-object=question] [data-action=research-review-cancel]').click();
 assert.deepEqual(await page.locator('#sheet [data-review-object]').evaluateAll(els=>els.map(el=>el.dataset.reviewObject)),recordOrder);
 assert((await page.locator('[data-review-object=question]').innerText()).includes('工作日'));
 const savedRevision=await page.evaluate(()=>researchObjects().find(o=>o.id==='question').revision);
 await shot('a-mobile-saved',375);
 await page.locator('#sheet [data-action=close]').click();await page.reload();await page.waitForFunction(()=>!!state.user);await page.evaluate(pid=>openProject(pid),setup.pid);await open();
 assert.deepEqual(await page.locator('#sheet [data-review-object]').evaluateAll(els=>els.map(el=>el.dataset.reviewObject)),recordOrder,'order must also survive page reload');
 checks.push('Item order unchanged after saving, cancelling and page reload');
 await page.getByRole('button',{name:'确认并继续',exact:true}).click();await page.waitForFunction(()=>!sheet.open&&state.project.current_step===2);
 assert.equal(await page.evaluate(()=>researchObjects().find(o=>o.id==='question').revision),savedRevision);
 checks.push('Independent saves remain on A; other drafts and edit buttons preserved; final continue does not reconfirm saved question');
 for(const letter of ['b','c','d','e','f']){
  // Let the page's post-submit project refresh finish before the fixture reads it.
  await page.waitForLoadState('networkidle');
  service.stdin.write(letter+'\n');await waitForText(new RegExp('SEEDED '+letter));await page.evaluate(pid=>openProject(pid),setup.pid);await open();
  assert.equal(await page.locator('#sheet .stage-review-blocker').count(),0,letter+' should be ready');
  if(letter==='f'){
   assert.equal(await page.locator('.focus-task .actions button').count(),1);
   assert.equal(await page.locator('.focus-task .submission-discussion button').innerText(),'跟 AI 教练讨论这份计划');
   assert.equal(await page.locator('.focus-task summary').filter({hasText:'完成标准'}).count(),0);
   assert.match(await page.locator('.student-document-summary').innerText(),/本次提交[\s\S]*第 1 稿[\s\S]*本稿答辩/);
   await page.locator('#sheet').getByText('查看计划正文',{exact:true}).click();
   assert(await page.locator('#sheet').getByRole('heading',{name:'研究问题与解释',exact:true}).isVisible());
   await page.locator('#sheet').getByText('查看本稿答辩',{exact:true}).click();
  }
  const contextHeading={b:'并入核心困惑的问题',c:'适用限制',d:'方案能验证什么',e:'本稿的答辩记录',f:'本稿的答辩记录'}[letter];
  assert((await page.locator('#sheet').innerText()).includes(contextHeading),letter+' decision context missing');
  const linkHeading={c:'研究问题的来由',d:'这个方法检验什么'}[letter];
  if(linkHeading)assert(await page.locator('#sheet').getByRole('heading',{name:linkHeading,exact:true}).isVisible());
  assert.equal(await page.locator('#sheet [type=submit]').innerText(),letter==='f'?'提交老师':'确认并继续');
  if(letter==='c'||letter==='d'){
   for(const oid of (letter==='c'?['rq','hypothesis']:['method'])){
    const version=await page.evaluate(()=>state.project.version);
    await page.locator('[data-review-object='+oid+'] [data-action=research-review-edit]').click();
    const contentBefore=await page.evaluate(id=>stageReviewObjects().find(o=>o.id===id).content,oid);
    const editorValues=await page.locator('[data-review-object='+oid+'] textarea').evaluateAll(nodes=>Object.fromEntries(nodes.map(n=>[n.name,n.value.trim()])));
    for(const [name,value] of Object.entries(editorValues))assert.equal(value,contentBefore[name.slice(('review-'+oid+'-').length)],name);
    await page.locator('[data-review-object='+oid+'] [data-action=research-review-save]').click();
    await page.waitForFunction(v=>sheet.open&&state.project.version>v,version);
   }
   assert.equal(await page.locator('#sheet .stage-review-blocker').count(),0,
    letter+' separate confirmations must retain valid references: '+JSON.stringify(await page.evaluate(()=>researchReviewState()?.items.filter(i=>['missing','incomplete','recheck'].includes(i.status)))));
   checks.push(letter.toUpperCase()+' independent item saves preserve dependent references');
  }
  await shot(letter+'-desktop',1440);await shot(letter+'-mobile',375);
  await page.locator('#sheet [type=submit]').click();await page.waitForFunction(()=>!sheet.open);
  checks.push(letter.toUpperCase()+' single-submit completed');
 }
 assert.equal(await page.evaluate(()=>state.project.status),'review');
 const reviewPage=await browser.newPage();
 reviewPage.setDefaultTimeout(12000);
 await reviewPage.goto(setup.base);
 await reviewPage.locator('[name=username]').fill('teacher');
 await reviewPage.locator('[name=password]').fill('yanjiu123');
 await reviewPage.locator('#login-form button').click();
 await reviewPage.waitForFunction(()=>!!state.user);
 await reviewPage.evaluate(pid=>openProject(pid),setup.pid);
 assert.equal(await reviewPage.locator('.review-summary').getByRole('button',{name:'讨论文件夹',exact:true}).count(),0);
 await reviewPage.getByText('查看本次答辩',{exact:true}).click();
 assert(await reviewPage.getByRole('heading',{name:'本稿的答辩记录'}).isVisible());
 await reviewPage.locator('[data-action=review]').first().click();
 const draftSave=reviewPage.locator('[data-action=save-review-draft]');
 assert(await draftSave.isEnabled());
 assert(await draftSave.evaluate(el=>getComputedStyle(el).backgroundColor !== getComputedStyle(el).borderColor));
 const teacherForm=reviewPage.locator('[data-form=review]');
 await teacherForm.locator('[name=decision]').selectOption('supplement');
 await teacherForm.locator('[name=step]').selectOption('4');
 for(const [name,value] of Object.entries({value:'有通勤实践价值',feasibility:'还缺一次同钟对照',deliverable:'补一组同时段记录',standard:'保留原始时间和采样条件',owner:'学生',due:'2027-01-10',evidence:'本次答辩已限定结论边界',gaps:'实际计时待核'})){
  await teacherForm.locator('[name='+name+']').fill(value);
 }
 await draftSave.click();
 await reviewPage.waitForFunction(()=>state.reviewDraft?.gaps==='实际计时待核'&&state.project.status==='review');
 assert.equal(await reviewPage.locator('.review-summary').getByRole('button',{name:'讨论文件夹',exact:true}).count(),0);
 await teacherForm.getByRole('button',{name:'确认并发布',exact:true}).click();
 await reviewPage.waitForFunction(()=>state.project.status==='active'&&state.project.current_step===4&&state.project.review?.decision==='supplement');
 checks.push('Teacher saw the exact submitted defense, saved an editable draft, then separately published a supplement request');
 await page.emulateMedia({reducedMotion:'reduce'});
 assert.equal(await page.evaluate(()=>getComputedStyle(Object.assign(document.body.appendChild(document.createElement('button')),{className:'review-attention'})).animationName),'none');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors}));
})().catch(e=>{console.error(e,stderr.slice(-1500));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();service.stdin.write('quit\n');service.stdin.end();});
