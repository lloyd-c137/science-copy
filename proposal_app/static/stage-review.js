"use strict";

const stageReviewFields = {
  curiosity:{observation:'发生了什么',why_care:'为什么在意'},
  topic:{title:'探索方向',exploration_reason:'选择理由'},
  question:{wording:'想继续探索的问题'},
  problem:{puzzle:'核心问题',grouping_reason:'为什么聚焦它',candidate_explanations:'可能的解释'},
  rq:{question:'研究问题',population_or_object:'研究谁或什么',conditions:'在哪些条件下',scope:'研究范围',promised_conclusion:'希望回答到什么程度'},
  hypothesis:{explanation:'主要解释',prediction:'可检验的预测',alternatives:'其他可能的解释',scope:'适用范围'},
  method:{procedure:'怎样研究',variables_or_concepts:'比较什么',analysis:'怎样分析',feasibility:'可行性条件',limits:'方法的限制'},
  defense:{revision_actions:'答辩后要改什么'}
};
const stageReviewGroups = {
  1:[['想研究的问题',['question']]],
  2:[['聚焦的核心问题',['problem']]],
  3:[['研究问题',['rq']],['解释与预测',['hypothesis']]],
  4:[['研究方法',['method']]],
  5:[['答辩后的修改',['defense']]],6:[]
};
function stageReviewObjects(){
  const kinds=new Set([...(researchStages[current().number-1]||[])]),targets=new Set(researchPendingChoices().map(p=>p.target_object_id));
  const direction=current().number===1&&current().data?.direction;
  if(direction){
    const active=researchObjects().filter(o=>!['abandoned','superseded'].includes(o.status));
    const objects=new Map(active.map(o=>[o.id,o]));
    const selected=[direction.observation_id,direction.main_question_id,...direction.subquestion_ids];
    const other=active.filter(o=>targets.has(o.id)&&!['curiosity','question','topic'].includes(o.kind));
    return [...selected.map(id=>objects.get(id)).filter(Boolean),...other].map(stageReviewCandidate);
  }
  const step=current().number, deliverable=step>=5?researchSelectedDeliverable():null;
  return researchObjects().filter(o=>!['abandoned','superseded'].includes(o.status)&&
    (o.kind==='defense'?step===5&&stageReviewMatchesSubmission(o,deliverable):kinds.has(o.kind)||targets.has(o.id))).map(stageReviewCandidate);
}
function stageReviewCandidate(o){
  const proposal=researchPendingChoices().filter(p=>p.target_object_id===o.id).at(-1);
  return {...o,content:proposal?.candidate_content||o.content};
}
function stageReviewStageLabels(step){
  if(step===1){
    const data=current().data;
    return {
      ...(data?.technical_plan?{technical_plan:'技术方案（草稿）'}:{}),
      ...(data?.first_validation?{first_validation:'第一步怎么验证'}:{}),
      selection_reason:'选择这个方向的理由'
    };
  }
  return step===4?{learning_value:'学习价值',practical_value:'实际价值',research_value:'研究价值',critical_validation:'最关键的验证',budget:'时间与资源'}:{};
}
function stageReviewObjectEntries(o){
  return Object.entries(stageReviewFields[o.kind]||{}).filter(([key])=>o.content?.[key]!=null&&o.content[key]!=='');
}
function hasStageReviewContent(){
  const step=current();
  const groupedKinds=new Set(stageReviewGroups[step.number].flatMap(group=>group[1]));
  return Boolean(researchPendingChoices().length ||
    researchReviewState()?.prepared ||
    (step.number>=5 && researchSelectedDeliverable()) ||
    Object.keys(stageReviewStageLabels(step.number)).some(key=>step.data?.[key]) ||
    stageReviewObjects().some(o=>(step.data?.direction||groupedKinds.has(o.kind)||!['search','check','curiosity','topic'].includes(o.kind))&&stageReviewObjectEntries(o).length));
}
function stageReviewObject(o){
  const entries=stageReviewObjectEntries(o);
  if(!entries.length)return '';
  return '<article class="stage-review-record" data-review-object="'+esc(o.id)+'"><div class="stage-review-copy">'+entries.map(([k,label],index)=>'<div class="stage-review-value">'+(index?'<h4>'+esc(label)+'</h4>':'')+'<p'+(!index?' class="stage-review-lead"':'')+'>'+esc(Array.isArray(o.content[k])?o.content[k].join('\n'):researchDisplayValue(k,o.content[k]))+'</p></div>').join('')+'</div><div class="stage-review-editor" hidden>'+entries.map(([k,label],index)=>{const field=textField('review-'+o.id+'-'+k,label,Array.isArray(o.content[k])?o.content[k].join('\n'):o.content[k],'textarea',k!=='revision_actions');return index?field:field.replace('<label>'+esc(label),'<label><span class="stage-review-sr">'+esc(label)+'</span>');}).join('')+'</div>'+btn('research-review-edit','修改','text-link stage-review-edit','aria-expanded="false"')+'</article>';
}
function stageReviewStageFields(){
  const s=current(),fields=stageReviewStageLabels(s.number);
  if(!Object.keys(fields).length)return '';
  return '<section class="stage-review-section stage-review-stage"><div class="stage-review-copy">'+Object.entries(fields).map(([k,label])=>'<h3>'+label+'</h3><p>'+esc(s.data?.[k]||'尚未整理')+'</p>').join('')+'</div><div class="stage-review-editor" hidden>'+Object.entries(fields).map(([k,label])=>textField('review-stage-'+k,label,s.data?.[k]||'','textarea',true)).join('')+'</div>'+btn('research-review-edit','修改','text-link stage-review-edit','aria-expanded="false"')+'</section>';
}
function stageReviewDocument(){
  const d=researchSelectedDeliverable();
  if(!d)return '<p class="stage-review-blocker">开题计划尚未整理。</p>';
  if(current().number===6){
    const defense=stageReviewDefense(d,true);
    return '<div class="student-document-summary"><p class="caption">本次提交</p><h3>'+esc(researchDeliverableLabel(d))+'</h3><p>'+ (defense?'包括计划正文和本稿答辩。':'本稿答辩待确认。')+'</p></div>'+
      fold('查看计划正文',researchChapters(d))+(defense?fold('查看本稿答辩',defense):'');
  }
  return '<section class="stage-review-section stage-review-document"><h3>'+esc(researchDeliverableLabel(d))+'</h3>'+Object.entries(researchSections).map(([k,label])=>'<h4>'+label+'</h4><p>'+esc(d.chapters?.[k]||'')+'</p>').join('')+'</section>';
}
function stageReviewMatchesSubmission(object, draft){
  const ref=object.content?.deliverable_ref;
  return !!draft&&ref?.id===draft.id&&ref.revision===draft.revision;
}
function stageReviewDetails(title, values){
  const rows=values.filter(([,value])=>value).map(([label,value])=>'<h4>'+esc(label)+'</h4><p>'+esc(value)+'</p>').join('');
  return rows?'<section class="stage-review-section"><h3>'+esc(title)+'</h3>'+rows+'</section>':'';
}
function stageReviewDefense(d, confirmedOnly=false){
  const records=researchDefenses(d,confirmedOnly);
  if(!records.length)return '';
  return '<section class="defense-reading"><h3>本稿的答辩记录</h3>'+records.map(({content:c})=>{
    const full=String(c.answer_text||'');
    // Older saved answers may include a website handoff after the student's answer.
    const answer=full.split(/(?<=。)\s*(?=请把(?:这条新答辩|这个回答)(?:作为练习|绑定))/u)[0];
    return '<article><h4>'+esc(c.question)+'</h4>'+readableText(answer,false)+
      (c.answer_ref?(current().number===6&&state.researchReviewActive?fold('查看已保存的完整回答',readableText(full,false)):researchQuoteButton(c.answer_ref)):answer!==full?fold('查看完整记录',readableText(full,false)):'')+
      (c.feedback?fold('AI 教练反馈',readableText(c.feedback,false)):'')+'</article>';
  }).join('')+'</section>';
}
function stageReviewLinks(title, targets, relations){
  const proposed=new Set(researchPendingChoices().flatMap(p=>p.relation_changes?.activate_draft_ids||[]));
  const byId=new Map(researchObjects().map(o=>[o.id,o]));
  const links=(state.project.research?.links||[]).filter(l=>relations.includes(l.relation)&&targets.has(l.to_ref.id)&&
    (proposed.has(l.id)||(l.status==='confirmed'&&!l.needs_review)));
  return stageReviewDetails(title,links.map(l=>[researchTitle(byId.get(l.from_ref.id)||{}),l.reason]));
}
function stageReviewStageContext(step, objects){
  const ids=kind=>new Set(objects.filter(o=>o.kind===kind).map(o=>o.id));
  if(step.number===2){
    return stageReviewLinks('并入核心困惑的问题',ids('problem'),['groups_into']);
  }
  if(step.number===3){
    const sources=new Map(researchEvidenceOptions().map(o=>[o.id,o.label]));
    return stageReviewLinks('研究问题的来由',ids('rq'),['frames','explains'])+
      (step.data?.source_comparisons||[]).map(row=>stageReviewDetails(sources.get(row.reference)||'共读来源',[
      ['读到哪里',[row.location,researchDisplayValue('reading_scope',row.reading_scope)].filter(Boolean).join(' · ')],
      ['支持什么',row.supports],['适用限制',row.cannot_claim],['怎样影响研究问题',row.question_impact]
    ])).join('');
  }
  if(step.number===4){
    const checks=objects.filter(o=>o.kind==='check');
    const replaced=new Set(checks.map(o=>o.content.supersedes?.id).filter(Boolean));
    return stageReviewLinks('这个方法检验什么',ids('method'),['operationalized_by'])+
      checks.filter(o=>!replaced.has(o.id)).map(o=>stageReviewDetails('方案能验证什么',[
      ['怎样回答研究问题',o.content.rq_alignment],['怎样区分不同解释',o.content.alternative_discrimination],
      ['结论能到哪里',o.content.conclusion_limits],['学生的回应',o.content.reviewer_response],
      ['待解决事项',o.content.unresolved?.join('\n')]
    ])).join('');
  }
  return step.number===5?stageReviewDefense(researchSelectedDeliverable()):'';
}
function researchProgressDialog(){
  state.researchReviewActive=true;
  const s=current(),review=researchReviewState(),objects=stageReviewObjects(),groups=stageReviewGroups[s.number],shown=new Set(groups.flatMap(g=>g[1]));
  const direction=s.number===1&&s.data?.direction;
  if(direction)shown.add('curiosity');
  let content=s.number>=5?stageReviewDocument():'';
  const sections=direction?[
    ['最初的观察',objects.filter(o=>o.id===direction.observation_id)],
    ['主问题',objects.filter(o=>o.id===direction.main_question_id)],
    ['已选子问题',objects.filter(o=>direction.subquestion_ids.includes(o.id))]
  ]:groups.map(([label,kinds])=>[label,objects.filter(o=>kinds.includes(o.kind))]);
  for(const [label,entries] of sections){
    const rows=entries.map(stageReviewObject).join('');
    if(rows)content+='<section class="stage-review-section"><h3>'+label+'</h3>'+rows+'</section>';
  }
  const other=objects.filter(o=>!shown.has(o.kind)&&!['search','check','curiosity','topic'].includes(o.kind)).map(stageReviewObject).join('');
  if(other)content+='<section class="stage-review-section"><h3>本次调整</h3>'+other+'</section>';
  content+=stageReviewStageContext(s,objects);
  content+=stageReviewStageFields();
  for(const p of researchPendingChoices().filter(p=>!p.target_object_id))content+='<section class="stage-review-section"><h3>'+esc(p.text)+'</h3>'+Object.values(p.changes||{}).map(v=>'<p>'+esc(v)+'</p>').join('')+'</section>';
  const blockers=(review?.items||[]).filter(i=>['missing','incomplete','recheck'].includes(i.status));
  const blocked=blockers.length>0;
  if(blocked){
    const visible=blockers.filter(item=>item.kind!=='execution');
    const explained=visible.length?visible:blockers;
    const plainLabels={'科学判断与当前引用':'关键验证','确认事务检查':'请先核对最新成果'};
    const labels=[...new Set(explained.map(item=>plainLabels[item.label]||item.label).filter(Boolean))];
    const details=[...new Set(explained.map(item=>item.detail?.replaceAll('请导师','请AI教练')).filter(Boolean))];
    content+='<aside class="stage-review-blocker" aria-label="待补内容"><strong>还有内容待补</strong>'+
      (labels.length?'<ul>'+labels.map(label=>'<li>'+esc(label)+'</li>').join('')+'</ul>':'')+
      (details.length?'<details><summary>查看具体要求</summary>'+details.map(detail=>'<p>'+esc(detail)+'</p>').join('')+'</details>':'')+
      '</aside>';
  }
  const canSave=objects.some(o=>o.status!=='confirmed')||researchPendingChoices().length;
  const label=blocked?'保存选择':s.number===6?'提交老师':review?.confirmed?'继续':'确认并继续';
  dialog(s.number===6?'提交开题计划':s.title||names[s.number-1],formStart('research-stage-review')+'<div class="stage-review-body">'+content+'</div>'+formError+'<footer class="stage-review-footer">'+(blocked?btn('launch','继续讨论',canSave?'secondary':'primary'):'')+(!blocked||canSave?'<button type="submit" class="primary">'+label+'</button>':'')+'</footer></form>');
  const form=sheet.querySelector('form');form.reviewBase=dataBase();form.reviewStep=s.number;form.reviewComplete=!blocked;form.reviewObjects=objects;
  // Disabled controls neither duplicate the reading view nor participate in validation.
  form.querySelectorAll('.stage-review-editor textarea').forEach(el=>el.disabled=true);
  form.querySelectorAll('.stage-review-editor').forEach(editor=>editor.insertAdjacentHTML('beforeend','<div class="stage-review-edit-actions">'+btn('research-review-save','保存修改','primary')+btn('research-review-cancel','取消','text-link')+'</div>'));
}
function stageReviewEdit(el){
  const section=el.closest('.stage-review-record,.stage-review-stage'),form=el.closest('form');
  if(form.dataset.busy)return;
  section.querySelector('.stage-review-copy').hidden=true;
  const editor=section.querySelector('.stage-review-editor');editor.hidden=false;editor.querySelectorAll('textarea').forEach(input=>input.disabled=false);
  el.hidden=true;editor.querySelector('textarea')?.focus();
  const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
}
function stageReviewRestore(form,except){
  const drafts=[...form.querySelectorAll('.stage-review-record,.stage-review-stage')].filter(section=>section!==except&&!section.querySelector('.stage-review-editor').hidden).map(section=>({id:section.dataset.reviewObject,values:[...section.querySelectorAll('textarea')].map(input=>[input.name,input.value])}));
  const scroll=sheet.scrollTop;
  researchProgressDialog();
  const next=sheet.querySelector('form');
  for(const draft of drafts){
    const section=[...next.querySelectorAll('.stage-review-record,.stage-review-stage')].find(s=>s.dataset.reviewObject===draft.id);
    if(!section)continue;
    stageReviewEdit(section.querySelector('[data-action=research-review-edit]'));
    for(const [name,value] of draft.values){const input=[...section.querySelectorAll('textarea')].find(i=>i.name===name);if(input)input.value=value;}
  }
  sheet.scrollTop=scroll;
}
function stageReviewCancel(el){const form=el.closest('form');if(form.dataset.busy)return;stageReviewRestore(form,el.closest('.stage-review-record,.stage-review-stage'));}
async function stageReviewSave(el){
  const form=el.closest('form'),section=el.closest('.stage-review-record,.stage-review-stage');
  if(form.dataset.busy)return;
  for(const input of section.querySelectorAll('textarea'))if(!input.reportValidity())return;
  const f=new FormData();section.querySelectorAll('textarea').forEach(input=>f.set(input.name,input.value));
  const {edits,data}=stageReviewPayload(form,f,true);
  form.dataset.busy='1';el.disabled=true;
  const error=form.querySelector('.error');error.textContent='';
  try{
    const result=await api('projects/'+state.project.id+'/research-review',{...form.reviewBase,step:form.reviewStep,confirmed:true,complete:false,scope:'item',edits,data});
    state.project=result;renderProject();stageReviewRestore(form,section);notify('已保存');
  }catch(e){report(e,form);}finally{delete form.dataset.busy;el.disabled=false;}
}
function stageReviewPayload(form,f,includeUnchanged=false){
  const edits=[],data={};
  for(const o of form.reviewObjects){
    const set={};for(const key of Object.keys(stageReviewFields[o.kind]||{})){
      const name='review-'+o.id+'-'+key;if(f.has(name))set[key]=key==='revision_actions'?String(f.get(name)).split(/\r?\n/).map(v=>v.trim()).filter(Boolean):String(f.get(name)).trim();
    }
    if(Object.keys(set).length&&(includeUnchanged||Object.keys(set).some(k=>JSON.stringify(set[k])!==JSON.stringify(o.content[k]))))edits.push({id:o.id,expected_revision:o.revision,set});
  }
  for(const [key,value] of f)if(key.startsWith('review-stage-'))data[key.slice(13)]=String(value).trim();
  return {edits,data};
}
async function stageReviewSubmit(form,f){
  if(form.querySelector('.stage-review-editor:not([hidden])'))throw Error('请先保存或取消正在修改的内容。');
  const {edits,data}=stageReviewPayload(form,f);
  const result=await api('projects/'+state.project.id+'/research-review',{...form.reviewBase,step:form.reviewStep,confirmed:true,complete:form.reviewComplete,edits,data});
  state.researchReviewActive=false;
  const completed=result.steps[form.reviewStep-1].status==='complete'||result.status==='review';
  await acceptProject(result,completed?(form.reviewStep===6?'已提交老师':'已保存，进入下一阶段'):'修改已保存');
}
