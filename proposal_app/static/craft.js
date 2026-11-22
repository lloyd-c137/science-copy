"use strict";
// Presentation helpers only. Data, forms, transitions and persistence stay in app.js.
function craftMark() {
  return '<span class="craft-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>';
}
function craftBrand() { return '<div class="brand">'+craftMark()+'<span>开题手记</span></div>'; }
const craftTreeState=new Map();
function craftBranch(key,label,content,css=''){
  const id=state.user.id+':'+key;
  return '<details class="nav-branch '+css+'" data-tree="'+esc(id)+'"'+(craftTreeState.get(id)===false?'':' open')+'><summary>'+label+'</summary><div class="nav-children">'+content+'</div></details>';
}
document.addEventListener('toggle',event=>{if(event.target.matches?.('[data-tree]'))craftTreeState.set(event.target.dataset.tree,event.target.open);},true);
function craftMast() {
  document.body.classList.toggle('signed-in', !!state.user);
  document.body.classList.remove('nav-open');
  if (!state.user) return '<header class="mast login-mast">'+craftBrand()+'</header>';
  const p = state.project;
  const homeLabel = teacher() ? '老师工作台' : '我的项目';
  return '<header class="mobile-top">'+btn('toggle-nav','☰','icon-btn mobile-menu','aria-label="打开导航" aria-controls="craft-sidebar" aria-expanded="false"')+craftBrand()+'</header>'+
    '<button class="nav-scrim" data-action="close-nav" aria-label="关闭导航" tabindex="-1"></button>'+
    '<aside class="craft-sidebar" id="craft-sidebar" aria-label="工作空间导航"'+(window.innerWidth<=900?' inert':'')+'>'+craftBrand()+
    '<nav class="space-navigation" aria-label="空间与项目">'+craftBranch('space',icon('user',19)+'<span>'+esc(state.user.name)+'的空间</span>',
    craftBranch('projects',icon('layers',18)+'<span>'+homeLabel+'</span>',
    btn(teacher()?'home':'projects',teacher()?'查看工作台':'查看全部项目','sidebar-home'+(!p?' selected':''),!p?'aria-current="page"':'')+
    (p ? craftBranch('project:'+p.id,icon('book',18)+'<span>'+esc(isResearch()?researchProjectTitle(p):p.title && p.title!=='尚未确定题目' ? p.title : p.activity?.title || '我的研究项目')+'</span>','<nav class="tabs" aria-label="项目内容">'+
      tabBtn('work','当前任务','pen')+(isResearch()?tabBtn('research','研究工作区','layers'):'')+tabBtn('card','开题计划与答辩','book')+tabBtn('learning','学习记录','layers')+tabBtn('files','材料','clip')+tabBtn('feedback','批注','bubble')+'</nav>','project-branch') : '')))+
    '</nav><footer class="sidebar-account"><div>'+icon('user',20)+'<span>'+esc(state.user.name)+'</span></div><div class="account-actions">'+
    '<a class="text-btn" href="/settings.html">设置</a><a class="text-btn" href="/first-use.html">'+icon('out',16)+'<span>插件</span></a>'+(p&&!teacher()?btn('reset-project',icon('trash',16)+'<span>清空</span>','text-btn reset-entry','title="清空当前项目"'):'')+btn('logout',icon('logout',16)+'<span>退出</span>','text-btn')+'</div></footer></aside>';
}
function craftLogin() {
  return mast()+'<main id="main" class="login"><div class="login-docs" aria-hidden="true">'+
    [['purple','pen','当前任务'],['yellow','user','老师的要求'],['green','layers','研究材料'],['blue','paper','开题卡']]
      .map(([tone,symbol,label])=>'<div class="preview-doc tone-'+tone+'"><h2>'+icon(symbol,26)+' '+label+'</h2><div class="login-preview-lines"></div></div>').join('')+'</div>'+
    '<section class="login-form"><h1>登录</h1><form id="login-form" class="form-stack"><label>教学账号<input name="username" required autocomplete="username"></label><label>密码<input name="password" type="password" required autocomplete="current-password"></label><div class="error" role="alert"></div><button class="primary">登录</button></form></section></main>';
}
function craftHome() {
  const h=state.home, acts=h.activities||[], projects=(h.projects||[]).filter(p=>!state.activity||String(p.activity_id)===state.activity);
  return mast()+'<main id="main" class="wrap student-home"><header class="home-heading"><div><h1>我的项目</h1></div><div class="filters"><select id="activity-filter" aria-label="筛选开题活动"><option value="">全部活动</option>'+acts.map(a=>'<option value="'+esc(a.id)+'" '+(String(a.id)===state.activity?'selected':'')+'>'+esc(a.title)+'</option>').join('')+'</select>'+btn('refresh-projects','刷新','text-btn')+'</div></header>'+
    (projects.length?projects.map(p=>{
      const activity=acts.find(a=>String(a.id)===String(p.activity_id));
      const supplement=p.status==='active'&&p.review?.decision==='supplement';
      return '<section class="home-project"><div class="home-feature"><article class="project-preview tone-purple"><div class="project-symbol">'+icon('book',48)+'</div><div><span class="caption">'+esc(activity?.title||'开题活动')+'</span><h2>'+esc(p.title||'我的第一个研究问题')+'</h2><span class="doc-chip">'+esc(supplement?'补充证据':p.status==='review'?'等待老师审阅':p.status==='approved'?'已开题':names[(p.current_step||1)-1]+' · 第 '+(p.current_step||1)+' 阶段')+'</span><p>'+esc(p.next_action||'继续讨论，把观察和证据整理成自己的研究。')+'</p>'+btn('project','继续当前任务','primary','data-id="'+esc(p.id)+'"')+'</div></article><aside class="requirements-preview tone-yellow"><h2>老师的要求</h2><p>'+esc(supplement?p.review.deliverable:activity?.requirements||'进入项目，查看本次活动的具体要求。')+'</p>'+(supplement?'<small>'+esc(p.review.owner)+'负责 · '+esc(p.review.due)+'复核</small>':'')+'</aside></div><h2 class="home-progress-title">研究进展</h2><div class="home-document-grid">'+[
        ['当前任务','pen','tone-purple',names[(p.current_step||1)-1],'work'],
        ['我的开题卡','book','tone-pink','研究问题、价值与年度范围','card'],
        ['学习记录','layers','tone-blue','讨论和学习反馈','learning'],
        ['研究材料','clip','tone-yellow','文献、观察与小试记录','files'],
        ['老师批注','bubble','tone-green','查看意见，回应老师','feedback']
      ].map(([label,symbol,tone,preview,key])=>'<button class="home-document '+tone+'" data-action="project-tab" data-id="'+esc(p.id)+'" data-key="'+key+'">'+icon(symbol,23)+'<h3>'+label+'</h3><div class="document-preview-lines"><p>'+esc(preview)+'</p><span aria-hidden="true">'+icon('arrow',14)+'</span></div></button>').join('')+'</div></section>';
    }).join(''):'<section class="panel empty">老师发布开题活动后，你可以在这里开始选题。</section>')+'</main>';
}
function craftTaskLayout(content) {
  const template=document.createElement('template'); template.innerHTML=content;
  const root=template.content.querySelector('.focus-work');
  if (!root || root.querySelector('.review-summary')) return content;
  root.classList.add('craft-task-layout');
  const strip=root.querySelector('.stage-strip'); if(strip)strip.remove();
  const aside=document.createElement('aside'); aside.className='craft-progress';
  aside.innerHTML='<details'+(window.innerWidth>680?' open':'')+'><summary>研究进度 <span>（6 步）</span></summary>'+road()+'</details>';
  root.append(aside);
  const requirement=root.querySelector('.support-options');
  if(requirement) { const folds=requirement.querySelectorAll(':scope > details'); if(folds.length>1)folds[0].remove(); }
  return template.innerHTML;
}
function craftReview(content) {
  const template=document.createElement('template');template.innerHTML=content;
  const summary=template.content.querySelector('.review-summary');
  if(!summary)return content;
  summary.querySelector('.stage-strip')?.remove();
  const wrapper=document.createElement('div');wrapper.className='craft-review-layout';
  const source=document.createElement('section');source.className='panel review-source';
  source.innerHTML='<h2>'+esc(state.project.title)+'</h2><div class="meta">'+esc(state.project.student_name)+' '+statusLabel(state.project.status)+'</div>'+state.project.steps.map(s=>'<section class="review-source-section"><h3><span class="section-number">'+String(s.number).padStart(2,'0')+'</span>'+esc(names[s.number-1])+'</h3><dl>'+ (taskRows(s)||'<p class="hint">尚未记录成果</p>')+'</dl></section>').join('');
  if(isResearch())source.innerHTML='<h2>'+esc(state.project.title)+'</h2>'+researchSubmittedView();
  const label=document.createElement('div');label.className='draft-title';label.innerHTML='<h2>审阅草稿</h2>';
  const pending=summary.querySelector('.review-pending');if(pending)label.append(pending);
  summary.prepend(label);wrapper.append(source,summary);
  return wrapper.outerHTML+fold('老师的要求',requirement());
}
function craftProjectChrome(p) {
  const title=isResearch()?researchProjectTitle(p):p.title==='尚未确定题目'?'我的第一个研究问题':p.title;
  return '<nav aria-label="返回与项目位置" class="crumb'+(teacher()?' teacher-project-nav':'')+'">'+
    btn(teacher()?'home':'projects',icon('back',17)+(teacher()?'返回老师工作台':'我的项目'),teacher()?'workspace-return':'text-btn')+
    (isResearch()?'':'<span class="crumb-divider">›</span><span class="project-location">'+esc(p.activity?.title||'开题活动')+'</span>')+'</nav>'+
    '<section class="hero project-context"><h1>'+esc(title||'我的研究项目')+'</h1><div class="meta">'+statusLabel(p.status)+
    (p.status==='approved'&&p.review?.due?'<span>首项交付 '+esc(p.review.due)+'</span>':p.review?.decision==='supplement'&&p.status==='active'?'<span>补证复核 '+esc(p.review.due||'待约定')+'</span>':p.activity?.deadline?'<span>开题期限 '+esc(p.activity.deadline)+'</span>':'')+'</div></section>';
}
function craftCloseNav(restoreFocus=false) {
  document.body.classList.remove('nav-open');
  const toggle=document.querySelector('.mobile-menu');toggle?.setAttribute('aria-expanded','false');
  document.getElementById('main')?.removeAttribute('inert');
  document.querySelector('.craft-sidebar')?.toggleAttribute('inert',window.innerWidth<=900);
  if(restoreFocus)toggle?.focus();
}
function craftToggleNav() {
  if(document.body.classList.contains('nav-open'))return craftCloseNav(true);
  document.body.classList.add('nav-open');
  document.querySelector('.craft-sidebar')?.removeAttribute('inert');
  document.querySelector('.mobile-menu')?.setAttribute('aria-expanded','true');
  document.getElementById('main')?.setAttribute('inert','');
  document.querySelector('.craft-sidebar summary')?.focus();
}
document.addEventListener('keydown',event=>{
  if(!document.body.classList.contains('nav-open'))return;
  if(event.key==='Escape'){event.preventDefault();craftCloseNav(true);}
  if(event.key==='Tab'){
    const buttons=[...document.querySelectorAll('.craft-sidebar button,.craft-sidebar a,.craft-sidebar summary')].filter(el=>el.checkVisibility());
    const first=buttons[0],last=buttons.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }
});
window.matchMedia('(min-width: 901px)').addEventListener('change',()=>craftCloseNav());
