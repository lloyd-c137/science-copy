"use strict";

// Structured research evidence and student choices. All record content is escaped.
const qualityOrigins = {measured:'实际测量',literature:'文献证据',student:'学生自述',ai_example:'AI 练习示例',inference:'推断'};
const qualityStatuses = {pending:'待我选择',accepted:'已接受',rejected:'已拒绝',deferred:'暂缓决定',superseded:'已由新建议替代'};
const qualityKinds = {claim:'判断依据',proposal:'导师建议',support:'学习支持',session:'讨论续接'};
function qualityProposalStale(record,p){
  if(!record.target_object_id)return false;
  if(p.research?.review_readiness?.items.some(i=>i.proposal_id===record.id&&i.status==='incomplete'))return true;
  const obj=p.research?.objects.find(o=>o.id===record.target_object_id);
  return !obj||obj.revision!==record.expected_revision||record.requirement_version!==p.activity.version||Object.entries(record.relation_baselines||{}).some(([id,baseline])=>JSON.stringify(p.research?.links.find(l=>l.id===id))!==JSON.stringify(baseline));
}

function qualityField(record, key) {
  return state.project.steps.find(s=>s.number===record.step)?.fields.find(f=>f.key===key)?.label || key;
}
function qualityDetails(label, value) {
  return value ? '<div class="quality-detail"><strong>'+esc(label)+'</strong><p>'+esc(value)+'</p></div>' : '';
}
function qualityChanges(record) {
  if(record.target_object_id)return researchChanges(record);
  return '<div class="quality-changes">'+Object.entries(record.changes||{}).map(([key,value])=>
    '<div><h4>'+esc(qualityField(record,key))+'</h4><div class="quality-before"><span>'+(record.status==='accepted'?'修改前':'原方案')+'</span><p>'+esc(record.baseline?.[key]||'尚未填写')+'</p></div><div class="quality-after"><span>'+(record.status==='accepted'?'已选':'建议')+'</span><p>'+esc(value)+'</p></div></div>').join('')+'</div>';
}
function qualityReference(record, p) {
  if(!record.reference)return '';
  if(record.origin==='student')return btn('quality-evidence','查看学生原话','text-link','data-evidence-id="'+esc(record.reference)+'"');
  const file=p.files?.find(f=>f.id===record.reference);
  let href=file?safeUrl(file.url):(/^https?:\/\//i.test(record.reference)?safeUrl(record.reference):'');
  const label=file?file.name:record.reference;
  return '<div class="quality-reference">'+(href?'<a href="'+href+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>':'<span>'+esc(label)+'</span>')+(record.location?'<span>'+esc(record.location)+'</span>':'')+'</div>';
}
function qualityRecord(record, p) {
  let content='';
  if(record.kind==='claim') {
    content='<h3>'+esc(record.text)+'</h3><span class="quality-tag">'+esc(qualityOrigins[record.origin]||record.origin)+'</span>'+qualityReference(record,p)+qualityDetails('核对记录',record.check)+qualityDetails('结论边界',record.limitation);
    if(p.quality.records.some(r=>r.supersedes===record.id))content='<span class="quality-tag">已由后续记录更正</span>'+content;
    if(record.supersedes)content+=qualityDetails('更正原记录',record.supersedes);
    if(record.calculation) {
      const c=record.calculation;
      content+='<div class="quality-calculation '+(c.passed===false?'needs-check':'')+'"><strong>'+(c.passed===true?'算式复算一致':c.passed===false?'算式结果不一致':'计算记录')+'</strong><p><code>'+esc(c.expression)+' = '+esc(c.result)+'</code> '+esc(c.unit||'')+'</p>'+(c.expected!==undefined?'<p>原记录结果：'+esc(c.expected)+'</p>':'')+'</div>';
    }
  } else if(record.kind==='proposal') {
    content='<h3>'+esc(record.text)+'</h3><span class="quality-tag">'+esc(record.status==='pending'&&teacher()?'待学生选择':qualityStatuses[record.status]||record.status)+'</span>'+qualityDetails('建议理由',record.reason)+qualityChanges(record)+qualityDetails(teacher()?'学生决定':'我的决定',record.decision_reason);
    if(record.decisions?.length>1)content+='<details class="quality-decision-history"><summary>此前的选择</summary>'+record.decisions.slice(0,-1).map(d=>qualityDetails(qualityStatuses[d.decision]||d.decision,d.reason)).join('')+'</details>';
    if(!teacher() && p.status==='active' && ['pending','deferred'].includes(record.status)&&qualityProposalStale(record,p))content+='<p class="hint">这项建议依据的版本已变化，导师更新后再核对。</p>';
    if(!teacher() && p.status==='active' && ['pending','deferred'].includes(record.status)&&!qualityProposalStale(record,p)) {
      content+='<div class="actions quality-actions">'+[['accepted','接受建议'],['rejected','保留原方案'],['deferred','暂缓决定']].map(([decision,label])=>btn('quality-decide',label,decision==='accepted'?'secondary':'text-link','data-id="'+esc(record.id)+'" data-decision="'+decision+'"')).join('')+'</div>';
    }
  } else if(record.kind==='support') {
    content='<h3>'+esc(record.concept)+'</h3>'+qualityDetails('理解观察',record.observation)+qualityDetails('尝试的帮助',record.strategy)+qualityDetails('实际效果',record.outcome)+(record.evidence_id?btn('quality-evidence','查看学生原话','text-link','data-evidence-id="'+esc(record.evidence_id)+'"'):'');
  } else if(record.kind==='session') {
    content=qualityDetails('本轮已确定',record.settled)+qualityDetails('还没解决',record.unresolved)+qualityDetails('下一步',record.next_action)+qualityDetails('由谁继续',record.owner);
  }
  return '<article class="quality-record" data-quality-id="'+esc(record.id)+'"><div class="quality-meta"><span>'+esc(qualityKinds[record.kind]||'研究记录')+'</span><span>阶段 '+esc(record.step)+'</span>'+(record.author?'<span>'+esc(typeof record.author==='object'?(record.author.name||'研究记录者'):record.author)+'</span>':'')+'</div>'+content+'</article>';
}
function qualityView(p) {
  const records=p.quality?.records||[];
  if(!records.length)return '';
  const active=records.filter(r=>r.kind==='proposal'&&['pending','deferred'].includes(r.status));
  const latest=records.filter(r=>!active.includes(r)).slice(-3).reverse();
  const older=records.filter(r=>!active.includes(r)&&!latest.includes(r)).reverse();
  return '<section class="panel quality-panel" aria-label="依据与选择"><div class="panel-head"><h2>依据与选择</h2>'+(active.length?'<span class="quality-count">'+active.length+' 项待'+(teacher()?'学生':'我')+'选择</span>':'')+'</div>'+[...active,...latest].map(r=>qualityRecord(r,p)).join('')+(older.length?'<details class="quality-history"><summary>此前的 '+older.length+' 条记录</summary>'+older.map(r=>qualityRecord(r,p)).join('')+'</details>':'')+'</section>';
}
function qualityDecisionDialog(recordId, decision, reason='') {
  const p=state.project, record=p.quality?.records.find(r=>r.id===recordId);
  if(teacher()||p.status!=='active'||!record||record.kind!=='proposal'||!['pending','deferred'].includes(record.status))throw Error('这条建议已处理，请查看最新记录。');
  if(qualityProposalStale(record,p))throw Error('建议依据的版本已变化，请导师更新后再核对。');
  if(!['accepted','rejected','deferred'].includes(decision))throw Error('请选择有效的决定。');
  const title={accepted:'接受这项建议',rejected:'保留我的原方案',deferred:'暂缓这项建议'}[decision];
  dialog(title,formStart('quality-decision')+'<input type="hidden" name="record_id" value="'+esc(record.id)+'"><input type="hidden" name="quality_decision" value="'+decision+'"><input type="hidden" name="version" value="'+p.version+'"><input type="hidden" name="requirement_version" value="'+p.activity.version+'"><input type="hidden" name="request_id" value="'+esc(id())+'"><h3>'+esc(record.text)+'</h3>'+qualityChanges(record)+textField('reason',decision==='accepted'?'我选择修改的理由':decision==='rejected'?'我选择保留的理由':'我还需要什么，何时再判断',reason,'textarea',true)+(decision==='accepted'?'<p class="hint">接受后会更新以上成果；已完成且受影响的阶段需要重新核对。</p><label class="check"><input name="confirmed" type="checkbox" required>我已核对修改内容，这是我的选择。</label>':'')+'<div class="quality-conflict" hidden>'+btn('quality-refresh','核对最新建议','secondary')+'</div>'+formEnd('保存我的决定')+'</form>');
}
async function submitQualityDecision(form, f) {
  const decision=String(f.get('quality_decision'));
  if(decision==='accepted'&&!f.has('confirmed'))throw Error('请先核对修改内容。');
  const reason=String(f.get('reason')||'').trim();
  if(!reason)throw Error('请留下这次选择的理由。');
  try {
    const result=await api('projects/'+state.project.id+'/quality-decision',{
      record_id:f.get('record_id'),decision,reason,version:Number(f.get('version')),
      requirement_version:Number(f.get('requirement_version')),request_id:f.get('request_id'),confirmed:f.has('confirmed')
    });
    await acceptProject(result,decision==='accepted'?'建议已接受，成果与后续任务已更新':'你的选择与理由已保存');
    if(state.researchReviewActive&&isResearch())researchProgressDialog();
  } catch(error) {
    // Keep the original values/version on failure. Never silently retry a changed proposal.
    if(error.status===409)form.querySelector('.quality-conflict').hidden=false;
    report(error,form);
  }
}
async function refreshQualityDecision() {
  const form=sheet.querySelector('[data-form="quality-decision"]');
  if(!form)return;
  const f=new FormData(form), reason=String(f.get('reason')||'');
  state.project=await api('projects/'+state.project.id);
  renderProject();
  qualityDecisionDialog(f.get('record_id'),f.get('quality_decision'),reason);
}
async function qualityEvidence(evidenceId) {
  const saved=state.project.quality?.records.find(r=>(r.evidence_id===evidenceId||r.reference===evidenceId)&&r.student_quote);
  if(saved){dialog('这次讨论的原话',readableText(saved.student_quote,false));return;}
  const discussions=await api('projects/'+state.project.id+'/discussions');
  const message=(discussions.conversations||[]).flatMap(c=>c.messages||[]).find(m=>m.id===evidenceId&&m.role==='user');
  if(!message)throw Error('这条原话暂未同步，请稍后在学习记录中查看。');
  dialog('这次讨论的原话',readableText(message.text,false));
}
