"use strict";
// Research records share the existing project, choice and comment lifecycle.
const researchKinds = {
  curiosity:['原始观察',{observation:'观察与经历',why_care:'为什么在意',student_quote_ref:'原话记录引用'}],
  topic:['探索主题',{title:'主题',description:'描述',exploration_reason:'探索理由'}],
  question:['问题积累',{wording:'原始问法',question_type:'问题类型',importance:'为什么值得追问'}],
  problem:['核心困惑',{puzzle:'核心困惑',grouping_reason:'这些问题为什么相连',candidate_explanations:'可能的解释'}],
  rq:['研究问题',{population_or_object:'研究对象',conditions:'条件',question:'研究问题',scope:'范围',promised_conclusion:'希望回答到什么程度'}],
  hypothesis:['解释与假设',{explanation:'解释或假设',mechanism:'作用机制',prediction:'可检验预测',alternatives:'竞争解释或反例',scope:'适用条件与边界',null_hypothesis:'零假设（适用时）',not_applicable_reason:'不适用理由'}],
  method:['研究方法',{research_type:'研究类型',materials:'材料与资源',procedure:'研究步骤',analysis:'分析方法',variables_or_concepts:'变量或概念',feasibility:'可行性与时间预算',limits:'限制',ethics:'参与者安排（适用时）'}],
  search:['检索与阅读',{query:'检索词',channel:'检索渠道',searched_at:'检索时间',result_count:'结果数（未知留空）',selection_reason:'筛选理由',term_change_reason:'改词理由',understanding_change:'理解发生了什么变化',reading_scope:'阅读范围'}],
  check:['一致性核对',{mechanical_findings:'结构核对发现',reasoned_findings:'有依据的判断（每行一项）',rq_alignment:'方法怎样回答研究问题',alternative_discrimination:'怎样区分竞争解释或反例',conclusion_limits:'结论适用到哪里',unresolved:'尚未解决的问题（每行一项）',reviewer_response:'复核回应'}],
  defense:['答辩记录',{deliverable_ref:'对应开题计划',question:'追问',answer_ref:'回答原话引用',answer_text:'自己的回答',feedback:'反馈',revision_actions:'需要修改什么',context:'答辩场景'}]
};
const researchStages=[['curiosity','topic','question'],['problem'],['search','hypothesis','rq'],['method','check'],['defense'],[]];
const researchStatus={draft:'草稿',pending_confirmation:'待本人确认',confirmed:'已确认',superseded:'已替代',abandoned:'已放弃',prepared:'待提交',submitted:'已提交，待审阅',approved:'已通过',supplement:'补证前稿',redirect:'已要求调整'};
const researchSections={background:'背景与核心困惑',literature:'已有研究',question:'研究问题与解释',method:'方法与范围',validation:'关键验证与可行性',limits:'限制与待判断',references:'参考资料'};
const researchRelations={motivates:'引出',belongs_to:'属于主题',groups_into:'归入',frames:'形成',explains:'解释',operationalized_by:'通过方法检验',supports:'支持',challenges:'挑战',limits:'限制',compared_with:'比较',replaces:'替代'};
function isResearch(){return state.project?.workflow_version==='tanyue-v1';}
function researchObjects(){return state.project.research?.objects||[];}
function researchProjectTitle(p){
  const question=p.research?.objects?.find(o=>o.kind==='rq'&&o.content?.question===p.title);
  return question?.content?.population_or_object?.trim() || p.title || '我的研究项目';
}
function researchWritable(){return !teacher()&&state.project.status==='active';}
function researchTitle(o){return o.content?.title||o.content?.question||o.content?.puzzle||o.content?.wording||o.content?.observation||o.content?.explanation||o.content?.query||researchKinds[o.kind]?.[0]||'研究记录';}
function researchValue(v){return typeof v==='string'?v:v==null?'':JSON.stringify(v,null,2);}
function researchDeliverableLabel(ref){
  const versions=state.project.research?.deliverables||[],index=versions.findIndex(v=>v.id===ref?.id&&v.revision===ref?.revision);
  return index>=0?'开题计划 · 第 '+(versions[index].sequence||index+1)+' 稿':'开题计划 · '+String(ref?.id||'未知稿件')+' / 修订 '+String(ref?.revision||'?');
}
function researchDisplayValue(key,value){
  if(key==='deliverable_ref'&&value)return researchDeliverableLabel(value);
  const enums={question_type:{background:'背景问题',measurement:'测量问题',mechanism:'机制问题',open:'开放问题'},reading_scope:{full:'阅读全文',abstract:'只读摘要',excerpt:'只读摘录',not_read:'尚未阅读'},context:{practice:'答辩练习',formal:'正式答辩'}};
  if(enums[key]?.[value])return enums[key][value];
  if(['scope_refs','evidence_refs'].includes(key)&&Array.isArray(value))return value.map(r=>{const o=researchObjects().find(o=>o.id===r.id),e=researchEvidenceOptions().find(e=>e.type===r.type&&e.id===r.id);return (o?researchTitle(o):e?.label||'已保存依据')+(r.revision?' · 第 '+r.revision+' 版':'');}).join('\n');
  if(['student_quote_ref','answer_ref'].includes(key))return value?'已关联真实讨论原话':'';
  return researchValue(value);
}
function researchFields(o){return '<dl class="research-fields">'+Object.entries(o.content||{}).filter(([,v])=>v!==''&&v!=null).map(([k,v])=>'<div><dt>'+esc(researchKinds[o.kind]?.[1]?.[k]||({scope_refs:'核对对象',evidence_refs:'依据引用',deliverable_ref:'对应提交稿',student_quote:'学生原话'}[k])||k)+'</dt><dd>'+esc(researchDisplayValue(k,v))+'</dd></div>').join('')+'</dl>';}
function researchObjectCard(o, compact=false, editable=researchWritable()){
  const attrs='data-id="'+esc(o.id)+'"';
  const actions='<div class="actions">'+btn('research-history','形成过程','text-link',attrs)+btn('research-comment','关联批注','text-link',attrs)+(editable?btn('research-edit',o.status==='confirmed'?'提出修改':'编辑草稿','text-link',attrs)+(o.status==='draft'?btn('research-confirm','核对并确认','secondary',attrs):'')+btn('research-focus','聚焦讨论','text-link',attrs)+btn('research-link','关联依据','text-link',attrs)+(o.needs_review?btn('research-recheck','复核这项内容','text-link',attrs):''):'')+'</div>';
  const meta='<div class="research-meta"><span>'+esc(researchKinds[o.kind]?.[0]||o.kind)+' · 第 '+o.revision+' 版</span><span>'+esc(researchStatus[o.status]||o.status)+'</span>'+(o.needs_review?'<strong>待复核</strong>':'')+'</div>';
  const contents=researchFields(o)+actions;
  const title=esc(researchTitle(o));
  return '<article class="research-object" id="object-'+esc(o.id)+'">'+(compact?'<details><summary>'+title+'</summary>'+meta+contents+'</details>':meta+'<h3>'+title+'</h3>'+contents)+'</article>';
}
function researchOverview(objects){
  const steps=state.project.steps;
  const confirmed=(kind,step)=>{
    const candidates=objects.filter(o=>o.kind===kind&&o.status==='confirmed');
    const refs=steps[step-1]?.data?.object_refs||[];
    return candidates.find(o=>refs.some(r=>r.id===o.id&&r.revision===o.revision))||(candidates.length===1?candidates[0]:null);
  };
  const direction=steps[0]?.data?.direction;
  const observation=objects.find(o=>o.id===direction?.observation_id)||confirmed('curiosity',1);
  const problem=confirmed('problem',2);
  const question=objects.find(o=>o.kind==='rq'&&o.content?.question===state.project.title)||confirmed('rq',3);
  const method=confirmed('method',4);
  const check=confirmed('check',4);
  const selectedQuestions=(direction?.subquestion_ids||[]).map(id=>objects.find(o=>o.id===id)).filter(Boolean);
  const rows=[
    ['最初的观察',observation?.content.observation,observation?.content.student_quote_ref],
    ['选定方向与理由',problem?.content.puzzle||objects.find(o=>o.id===direction?.main_question_id)?.content.wording],
    ['研究问题',question?.content.question],
    ['研究方法',method?.content.procedure],
    ['已做的验证',check?.content.reasoned_findings?.[0]||check?.content.reviewer_response],
    ['下一步验证',steps[3]?.data?.critical_validation||steps[0]?.data?.first_validation],
    ['证据能说明什么',check?.content.conclusion_limits]
  ];
  return '<div class="student-reading research-overview">'+rows.filter(([,value])=>value).map(([label,value,quote])=>
    '<section><h3>'+label+'</h3>'+readableText(value)+(quote?researchQuoteButton(quote):'')+(label==='选定方向与理由'?readableText(problem?.content.grouping_reason||steps[0]?.data?.selection_reason)+(selectedQuestions.length?'<h4>已选子问题</h4><ul>'+selectedQuestions.map(o=>'<li>'+esc(researchTitle(o))+'</li>').join('')+'</ul>':''):'')+'</section>').join('')+'</div>';
}
function researchQuoteButton(id){return btn('quality-evidence','查看原话','text-link','data-evidence-id="'+esc(id)+'"');}
function researchWorkspace(){
  const objects=researchObjects();
  const groups=Object.entries(researchKinds).map(([kind,[label]])=>{
    const group=objects.filter(o=>o.kind===kind);
    const heading=kind==='question'?'历次探索的问题':label;
    return group.length?'<details class="research-group"><summary>'+heading+' <span>'+group.length+'</span></summary>'+group.map(o=>researchObjectCard(o,true)).join('')+'</details>':'';
  }).join('');
  return '<section class="panel student-document research-workspace"><div class="panel-head"><h2>研究工作区</h2>'+(researchWritable()?btn('research-new','新增研究记录','secondary'):'')+'</div>'+(objects.length?researchOverview(objects)+groups:'<p class="empty">从一件好奇的事、一条问题或一次检索开始记录。</p>')+'</section>';
}
function researchPendingChoices(){
  return (state.project.quality?.records||[]).filter(r=>r.kind==='proposal'&&r.status==='pending');
}
function researchReviewState(){return state.project.research?.review_readiness;}
function researchReviewChecklist(){
  const review=researchReviewState();
  if(!review)return '';
  const labels={ready:'已确认',confirm:'待确认',recheck:'待复核',missing:'待整理',incomplete:'还有内容待整理'};
  return '<div class="research-review-checklist">'+review.items.map(item=>'<p><strong>'+esc(item.label)+'</strong> · '+labels[item.status]+(item.detail?'<br><span class="hint">'+esc(item.detail)+'</span>':'')+'</p>').join('')+'</div>';
}
function researchSelectedDeliverable(){
  const step=current();
  const ref=(step.number===6?researchFinalRef():null)||step.data?.deliverable_ref||state.project.research?.selected_deliverable;
  return (state.project.research?.deliverables||[]).find(d=>d.id===ref?.id&&d.revision===ref?.revision);
}
function researchFinalRef(){
  const p=state.project;
  return (p.status!=='active'?p.submitted_deliverable:null)||p.steps[4]?.data?.deliverable_ref;
}
function researchDefenses(version, confirmedOnly=false){
  return researchObjects().filter(o=>o.kind==='defense'&&
    !['abandoned','superseded'].includes(o.status)&&(!confirmedOnly||o.status==='confirmed')&&stageReviewMatchesSubmission(o,version));
}
function researchSubmissionCaption(version){
  if(!version)return '请先核对开题计划与本稿答辩。';
  const count=researchDefenses(version,true).length;
  return researchDeliverableLabel(version)+' · '+(count?'含本稿答辩':'本稿答辩待确认')+' · 尚未提交';
}
function researchTaskView(){
  const p=state.project,s=current(),active=s.number===p.current_step;
  if(teacher()&&p.status==='review'&&active)return teacherReviewView();
  const review=researchReviewState();
  const canReview=active&&researchWritable()&&s.number!==6&&hasStageReviewContent();
  const needsChoice=canReview&&review?.prepared&&(researchPendingChoices().length>0||!review.confirmed);
  const starting = s.number === 1 && p.version === 1;
  const discussionLabel = starting ? '跟AI教练开始讨论' : '继续跟AI教练讨论';
  const emphasizeReview = needsChoice && !starting;
  const awaitingSubmit=active&&s.number===6&&researchWritable();
  const controls=awaitingSubmit?btn('research-progress','核对并提交老师审阅','primary'):
    researchWritable()&&active?btn('launch',discussionLabel+' '+icon('out',16),emphasizeReview?'secondary':'primary')+btn('research-progress','核对阶段成果',emphasizeReview?'primary review-attention':'secondary',canReview?'':'disabled title="暂无可核对的阶段成果"'):teacher()?btn('comment','写批注'):'';
  const discussion=awaitingSubmit?'<p class="action-note submission-discussion">'+btn('launch','跟 AI 教练讨论这份计划','text-link')+'</p>':'';
  const standard=s.number===6&&!teacher()?'':fold('完成标准','<p>'+esc(acceptance[s.number-1])+'</p>');
  const prompt=awaitingSubmit?researchSubmissionCaption(researchSelectedDeliverable()):p.next_action||s.goal||acceptance[s.number-1];
  return '<div class="focus-work"><section class="panel focus-task">'+stageStrip()+'<span class="eyebrow">'+(active?'当前任务':'回看阶段')+'</span><h2>'+esc(names[s.number-1])+'</h2><p class="focus-prompt'+(awaitingSubmit?' submission-caption':'')+'">'+esc(prompt)+'</p>'+(p.review?.decision==='supplement'?'<div class="next"><strong>老师请你补证</strong><p>'+esc(p.review.deliverable)+'</p>'+qualityDetails('完成标准',p.review.standard)+qualityDetails('判断依据',p.review.evidence)+qualityDetails('待核实事项',p.review.gaps)+'</div>':'')+(p.research?.focus_object_id?'<p class="hint">正在聚焦：'+esc(researchTitle(researchObjects().find(o=>o.id===p.research.focus_object_id)||{}))+'</p>':'')+'<div class="actions">'+controls+(!teacher()&&active&&s.number===4&&p.status==='active'?btn('comment','请老师看一看','text-link'):'')+'</div>'+discussion+standard+'</section>'+fold('老师的要求',requirement())+'</div>';
}
function researchDeliverableView(){
  const versions=state.project.research?.deliverables||[];
  const p=state.project;
  const final=p.current_step===6?researchFinalRef():null;
  const ref=final||p.research?.selected_deliverable;
  const current=ref?versions.find(v=>v.id===ref.id&&v.revision===ref.revision):versions.at(-1);
  const older=versions.filter(v=>v!==current).reverse();
  const status=current?.publication_status||current?.status;
  const otherDefenses=researchObjects().filter(o=>o.kind==='defense'&&!versions.some(v=>researchDefenses(v).includes(o)));
  const caption=status==='prepared'?(final?'当前提交稿 · 尚未提交':'当前稿 · 待核对'):researchStatus[status];
  const printHistory=older.map(v=>'<details class="research-deliverable"><summary>'+esc(researchDeliverableLabel(v))+(v.publication_status&&v.publication_status!=='prepared'?' · '+esc(researchStatus[v.publication_status]||v.publication_status):'')+'</summary>'+researchVersionContents(v)+'</details>').join('');
  return '<section class="panel student-document"><div class="panel-head"><h2>开题计划与答辩</h2>'+(researchWritable()?btn('research-deliverable','整理新版开题计划','secondary'):'')+'</div>'+
    (current?'<div class="student-document-summary"><p class="caption">'+esc(caption||'当前稿')+'</p><h3>'+esc(researchDeliverableLabel(current))+'</h3></div>'+researchVersionContents(current,true):'<p class="empty">'+(ref?'当前稿暂时无法读取，请核对开题计划。':'开题计划整理后，可以在这里查看正文和对应的答辩。')+'</p>')+
    (printHistory?fold('历史稿 · '+older.length+' 份',printHistory):'')+
    (otherDefenses.length?fold('其他答辩记录',otherDefenses.map(o=>researchObjectCard(o,true,false)).join('')):'')+
    '<div class="actions">'+(researchWritable()&&current?btn('research-new','记录答辩','text-link','data-kind="defense"'):'')+'<a class="text-link" href="/api/projects/'+encodeURIComponent(p.id)+'/research-export">导出研究过程</a></div></section>'+reviewView();
}
function researchVersionContents(version, current=false){
  return '<div class="student-reading">'+(current?'<div class="document-outline">'+Object.values(researchSections).map(label=>'<span>'+label+'</span>').join('')+'</div>':'')+
    fold('查看计划正文',researchChapters(version))+
    (stageReviewDefense(version,current&&state.project.current_step===6&&!!researchFinalRef())||'<p class="hint">本稿暂无已核对的答辩记录。</p>')+
    (researchDefenses(version).length?fold('答辩详情与修改记录',researchDefenses(version).map(o=>researchObjectCard(o,true,current&&researchWritable())).join('')):'')+
    fold('引用的研究记录',researchRefList(version.object_refs||[]))+'</div>';
}
function researchChapters(version){
  return Object.entries(researchSections).map(([key,label])=>{
    const chapter=version.chapters?.[key];
    const materials=key==='references'?(state.project.materials||[]).filter(m=>!m.lead&&m.url&&chapter?.includes(m.url)):[];
    return '<section class="plan-chapter"><h4>'+label+'</h4>'+readableText(chapter,false)+
      (materials.length?'<ul>'+materials.map(m=>'<li><a href="'+safeUrl(m.url)+'" target="_blank" rel="noopener noreferrer">'+esc(m.title||m.url)+' ↗</a></li>').join('')+'</ul>':'')+'</section>';
  }).join('');
}
function researchRefList(refs){return '<ul class="research-refs">'+refs.map(r=>{const o=researchObjects().find(x=>x.id===r.id);return '<li>'+esc(o?researchTitle(o):r.id)+' · 第 '+esc(r.revision)+' 版'+(o&&r.revision!==o.revision?'（已有新版）':'')+'</li>';}).join('')+'</ul>';}
function researchChanges(record){
  const object=researchObjects().find(o=>o.id===record.target_object_id),baseline=(state.project.research?.revisions||[]).find(o=>o.id===record.target_object_id&&o.revision===record.expected_revision),before=record.baseline_content||baseline?.content||record.baseline||object?.content||{},patch=record.content_patch||{set:{},remove:[]};
  const after={...before,...patch.set};for(const key of patch.remove||[])delete after[key];
  const keys=[...new Set([...Object.keys(patch.set||{}),...(patch.remove||[])])].filter(key=>JSON.stringify(before[key])!==JSON.stringify(after[key]));
  const fields=keys.length?'<div class="quality-changes">'+keys.map(key=>'<div><h4>'+esc(researchKinds[object?.kind]?.[1]?.[key]||({scope_refs:'核对对象',evidence_refs:'引用依据'}[key])||key)+'</h4><div class="quality-before"><span>原内容</span><p>'+esc(researchDisplayValue(key,before[key])||'尚未填写')+'</p></div><div class="quality-after"><span>'+(key in after?'候选内容':'删除此项')+'</span><p>'+esc(researchDisplayValue(key,after[key])||'—')+'</p></div></div>').join('')+'</div>':object?fold('查看本次核对内容',researchFields({...object,content:record.candidate_content||after})):'';
  return '<p class="hint">'+esc(researchKinds[object?.kind]?.[0]||'研究记录')+' · 第 '+esc(record.expected_revision)+' 版 → '+esc(researchStatus[record.proposed_status]||'已确认')+'</p>'+fields+researchRelationChanges(record);
}
function researchRelationChanges(record){
  const links=state.project.research?.links||[],changes=record.relation_changes||{};
  return ['activate_draft_ids','retire_link_ids'].map(key=>(changes[key]||[]).map(id=>{const l=record.relation_baselines?.[id]||links.find(x=>x.id===id);if(!l)return '';const from=researchObjects().find(o=>o.id===l.from_ref?.id),to=researchObjects().find(o=>o.id===l.to_ref?.id);return '<div class="quality-detail"><strong>'+(key==='activate_draft_ids'?'启用关联':'停用关联')+'</strong><p>'+esc(from?researchTitle(from):l.from_ref?.id)+' → '+esc(researchRelations[l.relation]||l.relation)+' → '+esc(to?researchTitle(to):l.to_ref?.id)+'</p><p>'+esc(l.reason)+'</p></div>';}).join('')).join('');
}
function researchEditDialog(object,kind){
  if(!researchWritable())throw Error('当前仅可查看研究记录。');
  kind=object?.kind||kind||'curiosity';
  dialog(object?.status==='confirmed'?'提出内容修改':object?'编辑研究草稿':'新增研究记录',formStart('research-object')+'<input type="hidden" name="object_id" value="'+esc(object?.id||'')+'"><input type="hidden" name="expected_revision" value="'+(object?.revision||0)+'">'+(object?'<input type="hidden" name="object_kind" value="'+kind+'">':'<label>记录类型<select name="object_kind" id="research-kind">'+Object.entries(researchKinds).map(([k,[label]])=>'<option value="'+k+'" '+(kind===k?'selected':'')+'>'+label+'</option>').join('')+'</select></label>')+'<div id="research-edit-fields">'+researchEditFields(kind,object?.content||{})+(kind==='check'?researchReferenceInputs(object?.content?.scope_refs||[]):kind==='defense'?researchEvidenceInputs(object?.content?.evidence_refs||[]):'')+'</div>'+(object?.status==='confirmed'?textField('reason','为什么修改','','textarea',true):'')+formEnd(object?.status==='confirmed'?'保存修改建议':'保存草稿')+'</form>');
}
function researchEditFields(kind,content){return Object.entries(researchKinds[kind][1]).map(([key,label])=>{
  if(kind==='defense'&&key==='deliverable_ref')return researchDeliverableSelect(content.deliverable_ref);
  if(kind==='defense'&&key==='answer_text')return '<p class="hint">保留上方所选回答的原话。</p>';
  if(kind==='check'&&key==='mechanical_findings')return '<p class="hint">系统会核对所选版本。</p>';
  if(['student_quote_ref','answer_ref'].includes(key))return researchQuoteInput('content-'+key,label,content[key]);
  const choices=key==='reading_scope'?{full:'阅读全文',abstract:'只读摘要',excerpt:'只读摘录',not_read:'尚未阅读'}:key==='context'?{practice:'练习',formal:'正式答辩'}:key==='question_type'?{background:'背景问题',measurement:'测量问题',mechanism:'机制问题',open:'开放问题'}:null;
  if(choices)return '<label>'+label+'<select name="content-'+key+'">'+Object.entries(choices).map(([v,l])=>'<option value="'+v+'" '+(content[key]===v?'selected':'')+'>'+l+'</option>').join('')+'</select></label>';
  return textField('content-'+key,label,(['reasoned_findings','unresolved','revision_actions'].includes(key)&&Array.isArray(content[key])?content[key].map(v=>typeof v==='string'?v:JSON.stringify(v)).join('\n'):researchValue(content[key])),key==='result_count'?'number':'textarea');
}).join('');}
function researchDeliverableSelect(value){
  const versions=state.project.research?.deliverables||[],selected=value||state.project.research?.selected_deliverable||versions.at(-1);
  return '<label>本次答辩针对哪份开题计划<select name="content-deliverable_ref" required><option value="">'+(versions.length?'请选择具体版本':'先保存一份开题计划，再记录答辩')+'</option>'+versions.slice().reverse().map(v=>'<option value="'+esc(v.id+'|'+v.revision)+'" '+(selected?.id===v.id&&selected?.revision===v.revision?'selected':'')+'>'+esc(researchDeliverableLabel(v))+' · '+esc(dateText(v.created_at))+'</option>').join('')+'</select></label>';
}
function researchTeacherSummary(p){
  if(p.workflow_version!=='tanyue-v1')return '';
  const modes={observation:'观察经历',divergence:'发散问题',search_diagnosis:'检索诊断',hypothesis_development:'发展假设',value_judgment:'价值判断',method_comparison:'比较方法',critical_validation:'关键验证',revision:'修订方案',prediction:'解释与预测',questioning:'积累问题',grouping:'问题归组',searching:'检索资料',reading:'比较共读',reasoning:'解释推理',alignment:'核对研究框架',proposal:'组织开题计划',review:'审阅',...Object.fromEntries(Object.entries(researchKinds).map(([k,[label]])=>[k,label]))};
  const mode=modes[p.tutor_mode]||(!/^[a-z_]+$/i.test(p.tutor_mode||'')?p.tutor_mode:''),count=p.needs_review_count??(Array.isArray(p.needs_review)?p.needs_review.length:0);
  return '<div class="research-queue-summary">'+(mode?'<span>当前活动：'+esc(mode)+'</span>':'')+(count?'<strong>'+esc(count)+' 项待复核</strong>':'')+(p.last_choice?'<p>最近选择：'+esc(p.last_choice.length>90?p.last_choice.slice(0,90)+'…':p.last_choice)+'</p>':'')+'</div>';
}
async function researchRefresh(message){const previous=state.project.current_step;state.project=await api('projects/'+state.project.id);if(previous!==state.project.current_step){state.step=state.project.current_step;state.researchReviewActive=false;}sheet.close();renderProject();if(message)notify(message);if(state.researchReviewActive)researchProgressDialog();}
async function researchProposal(object,content,reason,openDecision=false){
  const remove=Object.keys(object.content||{}).filter(k=>!(k in content));
  const prior=researchPendingChoices().filter(r=>r.target_object_id===object.id).at(-1);
  await api('projects/'+state.project.id+'/quality',{...dataBase(),kind:'proposal',record:{target_object_id:object.id,expected_revision:object.revision,content_patch:{set:content,remove},proposed_status:'confirmed',text:object.status==='confirmed'?'修改'+researchKinds[object.kind][0]:'确认'+researchKinds[object.kind][0],reason,supersedes_proposals:researchPendingChoices().filter(r=>r.target_object_id===object.id).map(r=>r.id),relation_changes:prior?.relation_changes||{activate_draft_ids:[],retire_link_ids:[]}}});
  await researchRefresh('建议已保存，请在“依据与选择”中核对并作出决定。');
  if(openDecision){const proposal=state.project.quality.records.filter(r=>r.kind==='proposal'&&r.target_object_id===object.id&&r.status==='pending').at(-1);qualityDecisionDialog(proposal.id,'accepted');}
}
async function researchAction(el){
  const action=el.dataset.action,object=researchObjects().find(o=>o.id===el.dataset.id);
  if(action==='research-review-edit'){stageReviewEdit(el);return;}
  if(action==='research-review-save'){await stageReviewSave(el);return;}
  if(action==='research-review-cancel'){stageReviewCancel(el);return;}
  if(!el.closest?.('#sheet')&&action!=='research-progress')state.researchReviewActive=false;
  if(['research-new','research-edit','research-progress'].includes(action))state.researchMessages=(await api('projects/'+state.project.id+'/discussions')).conversations?.flatMap(c=>c.messages||[]).filter(m=>m.role==='user')||[];
  if(action==='research-new'){researchEditDialog(null,el.dataset.kind);return;}
  if(action==='research-edit'){const pending=state.researchReviewActive&&researchPendingChoices().filter(r=>r.target_object_id===object?.id).at(-1);researchEditDialog(pending?.candidate_content?{...object,content:pending.candidate_content}:object);return;}
  if(action==='research-confirm'){await researchProposal(object,object.content,'本人核对研究草稿',true);return;}
  if(action==='research-focus'){await api('projects/'+state.project.id+'/research-focus',{...dataBase(),focus_object_id:object.id,tutor_mode:object.kind});await researchRefresh('已聚焦这项研究记录，可继续跟AI教练讨论。');return;}
  if(action==='research-comment'){state.researchCommentRef={id:object.id,revision:object.revision};await onAction({dataset:{action:'comment'}});return;}
  if(action==='research-link'){researchLinkDialog(object);return;}
  if(action==='research-history'){await researchHistory(object);return;}
  if(action==='research-deliverable'){researchDeliverableDialog();return;}
  if(action==='research-progress'){researchProgressDialog();return;}
  if(action==='research-recheck'){if(object.kind==='check'){researchEditDialog(null,'check');const form=sheet.querySelector('form');form.dataset.supersedes=JSON.stringify({type:'object',id:object.id,revision:object.revision});form.querySelectorAll('[name=object_refs]').forEach(input=>input.checked=(object.content.scope_refs||[]).some(r=>r.id===input.value));return;}dialog('复核这项内容',formStart('research-recheck')+'<input type="hidden" name="object_id" value="'+esc(object.id)+'"><input type="hidden" name="expected_revision" value="'+object.revision+'"><p>'+esc(researchTitle(object))+'</p>'+textField('reason','为什么当前内容仍然适用','','textarea',true)+formEnd('保存复核理由')+'</form>');}
}
document.addEventListener('change',e=>{if(e.target.id==='research-kind')document.getElementById('research-edit-fields').innerHTML=researchEditFields(e.target.value,{})+(e.target.value==='check'?researchReferenceInputs():e.target.value==='defense'?researchEvidenceInputs():'');});
function researchReferenceInputs(selected=[]){return '<fieldset class="research-reference-picker"><legend>引用的研究记录</legend>'+researchObjects().map(o=>'<label class="check"><input type="checkbox" name="object_refs" value="'+esc(o.id)+'" '+(selected.some(r=>r.id===o.id&&r.revision===o.revision)?'checked':'')+'>'+esc(researchTitle(o))+' · 第 '+o.revision+' 版'+(o.needs_review?' · 待复核':'')+'</label>').join('')+'</fieldset>';}
function researchSelectedRefs(f){return f.getAll('object_refs').map(ref=>{const o=researchObjects().find(o=>o.id===ref);if(!o)throw Error('引用内容已有变化，请重新核对。');return {type:'object',id:o.id,revision:o.revision};});}
function researchDeliverableDialog(){
  const previous=(state.project.research?.deliverables||[]).at(-1);
  dialog('整理开题计划',formStart('research-deliverable')+Object.entries(researchSections).map(([key,label])=>textField('chapter-'+key,label,previous?.chapters?.[key]||'','textarea',true)).join('')+researchReferenceInputs(previous?.object_refs||[])+formEnd('保存新版开题计划')+'</form>','每次保存产生一个可回查的版本；到 F 阶段核对后正式提交。');
}
const researchProgressDrafts=new Map();
function researchProgressDraftKey(){return state.user.id+':'+state.project.id+':'+current().number;}
document.addEventListener('input',event=>{
  const form=event.target.closest?.('[data-form="research-progress"]');if(!form)return;
  const data=new FormData(form),values={};for(const key of data.keys())if(key!=='confirmed')values[key]=data.getAll(key);
  values.object_refs=data.getAll('object_refs');researchProgressDrafts.set(researchProgressDraftKey(),values);
});
function researchStageFields(s){
  const fields=s.number===1?{selection_reason:'为什么选择这个方向，暂未选择什么'}:s.number===4?{learning_value:'学习价值',practical_value:'实际价值',research_value:'研究价值',budget:'时间与资源预算',critical_validation:'关键条件和实际验证依据'}:{};
  let html=Object.entries(fields).map(([key,label])=>textField('stage-'+key,label,s.data?.[key]||'','textarea',true)).join('');
  if(s.number===3){const rows=s.data?.source_comparisons||[{},{}];html+='<h3>独立来源比较</h3>'+rows.map((r,index)=>'<fieldset data-source-comparison><legend>来源 '+(index+1)+'</legend>'+Object.entries({reference:'材料或来源引用',location:'已读原文位置',student_message_ref:'说明理解的原话记录',supports:'支持什么',cannot_claim:'还不能声称什么',question_impact:'是否改变问题，为什么'}).map(([key,label])=>key==='student_message_ref'?researchQuoteInput('source-'+index+'-'+key,label,r[key]):key==='reference'?researchSourceInput('source-'+index+'-'+key,label,r[key]):textField('source-'+index+'-'+key,label,r[key]||'','textarea',true)).join('')+'<label>阅读范围<select name="source-'+index+'-reading_scope">'+Object.entries({full:'阅读全文',abstract:'只读摘要',excerpt:'只读摘录'}).map(([v,l])=>'<option value="'+v+'" '+(r.reading_scope===v?'selected':'')+'>'+l+'</option>').join('')+'</select></label></fieldset>').join('');}
  return html;
}
async function researchHistory(object){
  const r=state.project.research||{},revisions=(r.revisions||[]).filter(v=>(v.object_id||v.id)===object.id),events=(r.events||[]).filter(e=>e.object_id===object.id||e.target_object_id===object.id||(e.object_refs||[]).some(ref=>ref.id===object.id));
  const links=(r.links||[]).filter(l=>l.from_ref?.id===object.id||l.to_ref?.id===object.id);
  const comments=(state.project.comments||[]).filter(c=>c.object_id===object.id||c.object_ref?.id===object.id||c.target_object_id===object.id);
  const eventNames={object_saved:'保存研究记录',deliverable_created:'保存开题计划',created:'创建记录',proposed:'提出建议',accepted:'接受修改',rejected:'保留原方案',deferred:'暂缓决定',rechecked:'完成复核',updated:'保存草稿',submitted:'提交审阅'};
  dialog('形成过程 · '+researchKinds[object.kind][0],'<h3>'+esc(researchTitle(object))+'</h3><h4>原始记录与历次修订</h4>'+(revisions.length?revisions.map(v=>'<details><summary>第 '+v.revision+' 版 · '+esc(dateText(v.created_at))+'</summary>'+researchFields({...object,content:v.content})+'</details>').join(''):researchFields(object))+'<h4>关联与依据</h4>'+(links.length?'<ul>'+links.map(l=>{const from=researchObjects().find(o=>o.id===l.from_ref?.id),to=researchObjects().find(o=>o.id===l.to_ref?.id);return '<li>'+esc(from?researchTitle(from):l.from_ref?.id)+' → '+esc(researchRelations[l.relation]||l.relation)+' → '+esc(to?researchTitle(to):l.to_ref?.id)+'<p class="hint">'+esc(l.reason||'')+' · '+esc(l.status==='draft'?'候选关联':l.status==='confirmed'?'已生效':'历史关联')+'</p></li>';}).join('')+'</ul>':'<p class="hint">尚无关联记录</p>')+'<h4>选择与事件</h4><ol class="research-timeline">'+events.map(e=>'<li>'+esc(eventNames[e.kind||e.event_type||e.action||e.type]||'研究记录更新')+' · '+esc(dateText(e.created_at))+(e.reason?'<p>'+esc(e.reason)+'</p>':'')+'</li>').join('')+'</ol><h4>关联批注</h4>'+comments.map(c=>'<blockquote>'+esc(c.text)+'<footer>'+esc(c.author||c.name||'')+' · 第 '+esc(c.object_revision||c.object_ref?.revision||c.target_revision||'?')+' 版'+((c.object_revision||c.object_ref?.revision||c.target_revision)!==object.revision?'（当前已有新版）':'')+'</footer></blockquote>').join(''));
}
function researchCommentFields(){
  if(!isResearch())return '';
  const ref=state.researchCommentRef;delete state.researchCommentRef;
  return '<label>关联研究记录<select name="target_object_id"><option value="">整个阶段</option>'+researchObjects().map(o=>'<option value="'+esc(o.id)+'" '+(ref?.id===o.id?'selected':'')+'>'+esc(researchTitle(o))+' · 第 '+o.revision+' 版</option>').join('')+'</select></label>'+textField('peer_name','如为同伴反馈，填写同伴姓名（选填）','','text');
}
function researchCommentPayload(plain){const o=researchObjects().find(o=>o.id===plain.target_object_id);return o?{object_id:o.id,object_revision:o.revision}:{};}
function researchCommentLabel(c){const o=researchObjects().find(o=>o.id===c.object_id);return '<p class="hint">'+esc(o?researchTitle(o):'研究记录')+' · 第 '+esc(c.object_revision)+' 版'+(o&&o.revision!==c.object_revision?'（已有新版，此批注保留原定位）':'')+(c.peer_name?' · 同伴 '+esc(c.peer_name)+' 的反馈（代录）':'')+'</p>';}
function researchQuoteInput(name,label,value){return '<label>'+esc(label)+'<select name="'+esc(name)+'"><option value="">选择自己的讨论原话</option>'+((value&&!(state.researchMessages||[]).some(m=>m.id===value))?'<option selected value="'+esc(value)+'">此前引用的原话</option>':'')+(state.researchMessages||[]).map(m=>'<option value="'+esc(m.id)+'" '+(m.id===value?'selected':'')+'>'+esc(m.text?.slice(0,150))+'</option>').join('')+'</select></label>';}
function researchSourceInput(name,label,value){return '<label>'+esc(label)+'<select name="'+esc(name)+'"><option value="">选择已登记来源</option>'+researchEvidenceOptions().filter(o=>o.type!=='claim').map(o=>'<option value="'+esc(o.id)+'" '+(o.id===value?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select></label>';}
function researchEvidenceOptions(){return [...(state.project.files||[]).map(o=>({type:'file',id:o.id,label:o.name})),...(state.project.materials||[]).map(o=>({type:'source',id:o.id||o.url,label:o.title||o.url})),...(state.project.quality?.records||[]).filter(o=>o.kind==='claim').map(o=>({type:'claim',id:o.id,label:o.text}))];}
function researchEvidenceInputs(selected=[]){return '<fieldset><legend>对应依据</legend>'+researchEvidenceOptions().map(o=>'<label class="check"><input type="checkbox" name="evidence_refs" value="'+esc(o.type+':'+o.id)+'" '+(selected.some(r=>r.type===o.type&&r.id===o.id)?'checked':'')+'>'+esc(o.label)+'</label>').join('')+'</fieldset>';}
function researchEvidenceSelected(f){return f.getAll('evidence_refs').map(v=>{const separator=v.indexOf(':');return {type:v.slice(0,separator),id:v.slice(separator+1)};});}
function researchAllowedRelations(source,target){
  const a=source.kind,b=target.kind;
  return Object.keys(researchRelations).filter(relation=>{
    if(relation==='motivates')return a==='curiosity'&&['topic','question'].includes(b);
    if(relation==='belongs_to')return a==='question'&&b==='topic';
    if(relation==='groups_into')return a==='question'&&b==='problem';
    if(relation==='frames')return a==='problem'&&b==='rq';
    if(relation==='explains')return a==='hypothesis'&&b==='rq';
    if(relation==='operationalized_by')return ['rq','hypothesis'].includes(a)&&b==='method';
    if(['supports','challenges','limits'].includes(relation))return ['problem','hypothesis','rq','method'].includes(b);
    return ['compared_with','replaces'].includes(relation)&&a&&a===b;
  });
}
function researchLinkRelations(form){
  const target=researchObjects().find(o=>o.id===form.elements.target.value),raw=form.elements.from_ref.value,at=raw.indexOf(':');
  const source=raw.slice(0,at)==='object'?researchObjects().find(o=>o.id===raw.slice(at+1)):{type:raw.slice(0,at)};
  form.elements.relation.innerHTML=(source&&target?researchAllowedRelations(source,target):[]).map(k=>'<option value="'+k+'">'+esc(researchRelations[k])+'</option>').join('');
}
document.addEventListener('change',e=>{if(e.target.name==='from_ref'&&e.target.form?.dataset.form==='research-link')researchLinkRelations(e.target.form);});
function researchLinkDialog(object){
  const choices=[...researchObjects().filter(o=>o.id!==object.id).map(o=>({...o,type:'object',label:researchTitle(o)})),...researchEvidenceOptions()].filter(o=>researchAllowedRelations(o,object).length);
  if(!choices.length){dialog('关联研究依据','<p>先保存相关问题、主题或来源，再建立这项关联。</p>');return;}
  dialog('关联研究依据',formStart('research-link')+'<input type="hidden" name="target" value="'+esc(object.id)+'"><p>将上游问题或依据关联到：'+esc(researchTitle(object))+'</p><label>上游记录<select name="from_ref">'+choices.map(o=>'<option value="'+esc(o.type+':'+o.id)+'">'+esc(o.label)+'</option>').join('')+'</select></label><label>关联方式<select name="relation"></select></label>'+textField('reason','为什么建立这项关联','','textarea',true)+formEnd('保存关联建议')+'</form>','关联先保存为候选，核对并确认后生效。');
  researchLinkRelations(sheet.querySelector('form'));
}
async function researchSaveLink(f,base){
  const raw=f.get('from_ref');if(!raw)throw Error('请先保存上游问题或依据。');
  const at=raw.indexOf(':'),from={type:raw.slice(0,at),id:raw.slice(at+1)},target=researchObjects().find(o=>o.id===f.get('target'));
  if(from.type==='object')from.revision=researchObjects().find(o=>o.id===from.id).revision;
  const linkId='L'+id(),reason=String(f.get('reason')||'').trim();
  await api('projects/'+state.project.id+'/research-objects',{...base,objects:[],links:[{id:linkId,from_ref:from,to_ref:{type:'object',id:target.id,revision:target.revision},relation:f.get('relation'),reason,evidence_refs:[]}]});
  state.project=await api('projects/'+state.project.id);
  await api('projects/'+state.project.id+'/quality',{...dataBase(),kind:'proposal',record:{target_object_id:target.id,expected_revision:target.revision,content_patch:{set:{},remove:[]},proposed_status:target.status,text:'确认关联：'+researchRelations[f.get('relation')],reason,relation_changes:{activate_draft_ids:[linkId],retire_link_ids:[]}}});
  await researchRefresh('关联建议已保存，请在“依据与选择”中核对。');
}
function researchSubmittedView(){
  const ref=state.project.submitted_deliverable,version=(state.project.research?.deliverables||[]).find(v=>v.id===ref?.id&&v.revision===ref?.revision);
  if(!version)return '<p class="hint">学生尚未正式提交开题计划。</p>';
  const defense=stageReviewDefense(version,true);
  return '<h3>正式提交 · '+esc(researchDeliverableLabel(version))+'</h3>'+Object.keys(researchSections).map(k=>[k,version.chapters?.[k]||'']).map(([k,v])=>'<section class="review-source-section"><h4>'+esc(researchSections[k]||k)+'</h4>'+readableText(v,false)+'</section>').join('')+(defense?fold('查看本次答辩',defense):'')+researchRefList(version.object_refs||[]);
}
async function researchSubmit(form,f){
  if(!researchWritable())throw Error('当前仅可查看研究记录。');
  const path='projects/'+state.project.id+'/',kind=form.dataset.form;
  if(kind==='research-stage-review'){await stageReviewSubmit(form,f);return;}
  const savedBase=form.researchBase||(form.researchBase=dataBase());
  if(kind==='research-link'){await researchSaveLink(f,savedBase);return;}
  if(kind==='research-object'){
    const object=researchObjects().find(o=>o.id===f.get('object_id')),objectKind=f.get('object_kind'),content={...(object?.content||{})};
    for(const [key] of Object.entries(researchKinds[objectKind][1])){const value=String(f.get('content-'+key)||'').trim();if(key==='deliverable_ref'){const [refId,revision]=value.split('|');if(!refId)throw Error('请先选择本次答辩对应的开题计划版本。');content[key]={id:refId,revision:Number(revision)};}else if(['reasoned_findings','unresolved','revision_actions'].includes(key)){content[key]=value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);}else if(key==='mechanical_findings'){continue;}else if(key==='result_count'){content[key]=value===''?null:Number(value);}else if(value)content[key]=value;else delete content[key];}
    if(!Object.values(content).some(v=>v!==null&&v!==''))throw Error('请先写下这项研究记录的内容。');
    if(objectKind==='check'){content.scope_refs=researchSelectedRefs(f);if(form.dataset.supersedes)content.supersedes=JSON.parse(form.dataset.supersedes);}
    if(objectKind==='defense')content.evidence_refs=researchEvidenceSelected(f);
    if(object?.status==='confirmed'){await researchProposal(object,content,String(f.get('reason')||'').trim());return;}
    const record={kind:objectKind,expected_revision:Number(f.get('expected_revision')),origin_refs:object?.origin_refs||[]};
    if(object){record.id=object.id;record.content_patch={set:content,remove:Object.keys(object.content||{}).filter(k=>!(k in content))};}else record.content=content;
    const updated=await api(path+'research-objects',{...savedBase,objects:[record],links:[]});
    if(object&&state.researchReviewActive&&researchPendingChoices().some(r=>r.target_object_id===object.id)){
      state.project=updated;const revised=researchObjects().find(o=>o.id===object.id);
      await researchProposal(revised,revised.content,'本人修改待核对内容，仍需明确确认');return;
    }
  }else if(kind==='research-deliverable'){
    await api(path+'research-deliverable',{...savedBase,...((state.project.research?.deliverables||[]).length?{id:state.project.research.deliverables.at(-1).id,expected_revision:state.project.research.deliverables.at(-1).revision}:{}),chapters:Object.fromEntries(Object.keys(researchSections).map(k=>[k,String(f.get('chapter-'+k)||'').trim()])),object_refs:researchSelectedRefs(f)});
  }else if(kind==='research-recheck'){
    const objectId=f.get('object_id'),links=(state.project.research?.links||[]).filter(l=>l.to_ref?.id===objectId&&l.needs_review).map(l=>l.id);
    await api(path+'research-recheck',{...savedBase,object_id:objectId,expected_revision:Number(f.get('expected_revision')),reason:String(f.get('reason')||'').trim(),link_ids:links});
  }else if(kind==='research-progress'){
    if(!f.has('confirmed'))throw Error('请先核对阶段成果。');
    const latest=researchSelectedDeliverable();
    const extra={};for(const [k,v] of f)if(k.startsWith('stage-'))extra[k.slice(6)]=String(v).trim();
    if(current().number===3)extra.source_comparisons=[...form.querySelectorAll('[data-source-comparison]')].map((row,index)=>Object.fromEntries([...row.querySelectorAll('[name]')].map(input=>[input.name.replace('source-'+index+'-',''),input.value.trim()])));
    await api(path+'progress',{...savedBase,step:current().number,complete:true,confirmed:true,workflow_version:'tanyue-v1',data:{summary:String(f.get('summary')||'').trim(),object_refs:researchSelectedRefs(f),...extra,...(latest?{deliverable_ref:{id:latest.id,revision:latest.revision}}:{})}});
    researchProgressDrafts.delete(researchProgressDraftKey());state.researchReviewActive=false;
  }
  await researchRefresh(kind==='research-progress'?'阶段成果已提交':'研究记录已保存');
}
