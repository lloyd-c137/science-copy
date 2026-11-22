'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let motion = !reduced.matches;
let flowIndex = 0, archIndex = 0, flowTimer = null, archTimer = null;
const stages = [
 ['先留下“教室闷”背后的真实问法。','保留原话和不同可能方向，暂选理由可以继续修订，不按轮数催定题。','观察、问题与暂选理由'],
 ['这些问题，共同指向什么困惑？','区分通风、人数与主观闷感的解释，说明归组理由，由学生核对核心Problem。','问题归组与本人选择'],
 ['搜索与原文，怎样改变了理解？','记录改词和筛选，比较至少两篇独立来源的已读原文，形成有边界的RQ和解释路径。','搜索、来源、RQ与假设'],
 ['方法能支持承诺的结论吗？','核对相连的研究问题、假设与方法，分别判断方法匹配、竞争解释和结论边界；按活动预算做关键小试。','方法、关键验证与复核'],
 ['把计划讲清楚，也回答真实追问。','核对七章节Proposal及固定对象版本；保留学生实际答辩，发现根本缺口后回相关对象复核。','固定开题稿与答辩'],
 ['本人提交，老师发布正式决定。','学生在网站提交核对的固定版本；老师审阅同一版，发布通过、补证或调整方向。','固定提交与正式意见']
];
function setStage(index) {
 flowIndex = index;
 $$('.stage').forEach((button,i) => {button.classList.toggle('active',i===index);button.setAttribute('aria-pressed',String(i===index));});
 $('#stage-marker').textContent = String.fromCharCode(65+index)+' / F';
 $('#stage-title').textContent = stages[index][0];
 $('#stage-description').textContent = stages[index][1];
 $('#stage-evidence').textContent = '留下 → '+stages[index][2];
}
function stopFlow() {clearInterval(flowTimer);flowTimer=null;$('#flow-play').textContent='播放流程 ▷';$('#flow-play').setAttribute('aria-pressed','false');}
function stopArch() {clearInterval(archTimer);archTimer=null;$('#arch-play').textContent='演示协作 ▷';$('#arch-play').setAttribute('aria-pressed','false');$('.architecture').classList.remove('running');}
$$('.stage').forEach(button=>button.addEventListener('click',()=>{stopFlow();setStage(Number(button.dataset.stage));}));
$('#flow-play').addEventListener('click',()=>{
 if(flowTimer){stopFlow();return;}
 if(!motion){setStage((flowIndex+1)%6);return;}
 stopArch();if(flowIndex===5)setStage(0);
 $('#flow-play').textContent='暂停播放 Ⅱ';$('#flow-play').setAttribute('aria-pressed','true');
 flowTimer=setInterval(()=>{if(flowIndex<5)setStage(flowIndex+1);else stopFlow();},2600);
});
const branches = {
 approve:[['可开题','约定首项任务','开始正式研究'],'明确谁来做、何时交、交什么、怎样算完成。'],
 supplement:[['回到相关对象','补齐证据','E新稿与答辩','F重新提交'], 'CO₂ 案例回到D补记开窗时刻，再核对受影响的E开题计划与答辩；F本人重新提交后仍需老师审阅。'],
 redirect:[['说明调整要求','回到相关阶段','重新核对受影响成果'],'重新确认问题或范围，保留已有记录；核对哪些文献与判断仍然成立。']
};
$$('[data-decision]').forEach(button=>button.addEventListener('click',()=>{
 const key=button.dataset.decision;
 $$('[data-decision]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});
 const route=$('#branch-route');route.dataset.kind=key;route.replaceChildren();
 branches[key][0].forEach((label,i)=>{if(i){const arrow=document.createElement('b');arrow.textContent='→';arrow.setAttribute('aria-hidden','true');route.append(arrow);}const span=document.createElement('span');span.textContent=label;span.style.animationDelay=i*80+'ms';route.append(span);});
 $('#branch-note').textContent=branches[key][1];
 if(key==='supplement'){stopFlow();setStage(3);}else if(key==='redirect'){stopFlow();setStage(0);}
}));
const collaboration = [
 {nodes:['website','store','student-mcp','student-codex','files'],direction:'read',side:'student',text:'学生从网站打开课题文件夹下的 Codex 聊天，发送预填指令。插件里的 MCP 读取当前任务和老师批注。'},
 {nodes:['student-codex','skill','files'],direction:'none',text:'Codex 按辅导 Skill 展开讨论，和学生一起看本机文献或分析小试数据。'},
 {nodes:['student-codex','student-mcp','store'],direction:'write',side:'student',text:'插件里的 MCP 把草稿和讨论原文存回网站。网站检查归属，学生可以在学习记录里查看完整原文回执。'},
 {nodes:['store','website'],direction:'none',text:'学生回网站核对阶段成果，需要时可以逐项修改。到 F 阶段，由学生提交固定稿。'},
 {nodes:['website','store','teacher-mcp','teacher-codex','review-guide','review-files'],direction:'review',side:'teacher',text:'老师从网站打开审阅文件夹下的聊天，发送预填指令。插件读取固定稿和网站材料，把 Codex 整理的建议存成网页草稿。'},
 {nodes:['website','store'],direction:'none',text:'老师在网站核对、修改并发布意见，学生看到开题决定和下一步。'}
];
function setArch(index){archIndex=index;const step=collaboration[index];
 $$('[data-node]').forEach(node=>node.classList.toggle('live',step.nodes.includes(node.dataset.node)));
 $$('[data-arch]').forEach(button=>button.setAttribute('aria-pressed',String(Number(button.dataset.arch)===index)));
 $('.architecture').dataset.direction=step.direction;
 $$('.bridge-arrow').forEach(arrow=>{const active=arrow.closest('.student-bridge')?step.side==='student':step.side==='teacher';arrow.style.visibility=active?'visible':'hidden';arrow.textContent=step.direction==='read'?'←':step.direction==='write'?'→':'↔';});
 $('#arch-count').textContent=String(index+1).padStart(2,'0')+' / 06';$('#arch-description').textContent=step.text;
}
$$('[data-arch]').forEach(button=>button.addEventListener('click',()=>{stopArch();setArch(Number(button.dataset.arch));}));
$('#arch-play').addEventListener('click',()=>{
 if(archTimer){stopArch();return;}if(!motion){setArch((archIndex+1)%6);return;}
 if(innerWidth>980)$('.architecture').scrollIntoView({block:'start',behavior:'smooth'});
 stopFlow();if(archIndex===5)setArch(0);$('.architecture').classList.add('running');$('#arch-play').textContent='暂停演示 Ⅱ';$('#arch-play').setAttribute('aria-pressed','true');
 archTimer=setInterval(()=>{if(archIndex<5)setArch(archIndex+1);else stopArch();},3000);
});
function setMotion(value){motion=value;document.body.classList.toggle('motion-off',!motion);$('.motion-toggle').textContent='动效 '+(motion?'开':'关');$('.motion-toggle').setAttribute('aria-pressed',String(!motion));document.documentElement.style.scrollBehavior=motion?'smooth':'auto';if(!motion){stopFlow();stopArch();$('#flow-play').textContent='下一阶段 →';$('#arch-play').textContent='下一环节 →';}else{stopFlow();stopArch();}}
$('.motion-toggle').addEventListener('click',()=>setMotion(!motion));reduced.addEventListener('change',event=>setMotion(!event.matches));
const menu=$('.menu-toggle');
function closeMenu(){menu.setAttribute('aria-expanded','false');$('.nav-links').classList.remove('open');menu.textContent='目录 ＋';}
menu.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));$('.nav-links').classList.toggle('open',open);menu.textContent=open?'收起 −':'目录 ＋';});
$$('.nav-links a').forEach(link=>link.addEventListener('click',closeMenu));
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.getAttribute('aria-expanded')==='true'){closeMenu();menu.focus();}});
document.addEventListener('click',event=>{if(!event.target.closest('.masthead'))closeMenu();});
let scrollQueued=false;
function readingProgress(){const max=document.documentElement.scrollHeight-innerHeight;$('.progress div').style.width=(max>0?100*scrollY/max:0)+'%';let current='';$$('.chapter').forEach(chapter=>{if(chapter.getBoundingClientRect().top<innerHeight*.4)current=chapter.id;});$$('.nav-links a').forEach(link=>{const active=link.hash==='#'+current;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});scrollQueued=false;}
addEventListener('scroll',()=>{if(!scrollQueued){scrollQueued=true;requestAnimationFrame(readingProgress);}},{passive:true});addEventListener('resize',readingProgress);
const visibility=new IntersectionObserver(entries=>{entries.forEach(entry=>{entry.target.classList.toggle('offscreen',!entry.isIntersecting);if(!entry.isIntersecting&&entry.target.classList.contains('flow-diagram'))stopFlow();if(!entry.isIntersecting&&entry.target.classList.contains('architecture'))stopArch();});},{threshold:0});
$$('.diagram,.cover').forEach(el=>visibility.observe(el));
document.addEventListener('visibilitychange',()=>{document.body.classList.toggle('page-hidden',document.hidden);if(document.hidden){stopFlow();stopArch();}});
const imageDialog=$('#image-dialog');let imageTrigger=null;
$$('.zoom').forEach(button=>button.addEventListener('click',()=>{imageTrigger=button;const original=button.querySelector('img');imageDialog.querySelector('img').src=original.src;imageDialog.querySelector('img').alt=original.alt;imageDialog.showModal();document.body.classList.add('modal-open');}));
$('#close-image').addEventListener('click',()=>imageDialog.close());imageDialog.addEventListener('click',event=>{if(event.target===imageDialog)imageDialog.close();});imageDialog.addEventListener('close',()=>{document.body.classList.remove('modal-open');imageTrigger?.focus();});
$('#print').addEventListener('click',()=>{stopFlow();stopArch();print();});
setArch(0);setMotion(motion);readingProgress();
