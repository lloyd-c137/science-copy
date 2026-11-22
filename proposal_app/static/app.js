"use strict";
const app = document.getElementById("app");
const sheet = document.getElementById("sheet");
const toast = document.getElementById("toast");
let returnProjectId = new URLSearchParams(location.search).get("project");
const state = {
  user: null,
  home: null,
  project: null,
  tab: "work",
  step: 1,
  activity: "",
  rosterFilter: "all",
  sound: false,
  demo: false,
};
const names = [
  "A 兴趣探索与问题积累", "B 形成核心困惑", "C 搜索诊断与假设发展",
  "D 研究框架与关键验证", "E 开题计划与答辩准备", "F 老师审阅与开题决定",
];
const statuses = {
  active: "进行中",
  pending: "待开展",
  complete: "已完成",
  review: "待老师审阅",
  approved: "已开题",
};
const acceptance = [
  "保留真实观察与原始问法，说明当前选择继续探索的方向和理由。",
  "说明哪些问题被同一个核心困惑连接，保留归组理由、竞争解释与本人的选择。",
  "记录检索和阅读范围；比较至少两篇独立来源各一处已读原文，说明支持与限制，形成研究问题和解释路径。",
  "说明研究价值、方法、范围和时间预算；关键条件有依据，必要小试支持方法能够回答承诺的问题。",
  "组织完整开题计划，引用已经核对的对象版本，保留答辩问题、自己的回答和修改行动。",
  "本人核对固定版本后提交。老师分别判断价值与可行性，发布可开题、补证后再判或调整方向的决定。",
];
const paths = {
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4m0 3h.01"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  logout: '<path d="M9 4H4v16h5m-1-8h13m-5-5 5 5-5 5"/>',
  book: '<path d="M3 5q5-1 9 2 4-3 9-2v14q-5-1-9 2-4-3-9-2zM12 7v14"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  back: '<path d="M20 12H5m6-6-6 6 6 6"/>',
  out: '<path d="M6 18 18 6M8 6h10v10"/>',
  pen: '<path d="m4 20 5-1L20 8l-4-4L5 15zM13 7l4 4"/>',
  layers: '<path d="m3 8 9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  paper: '<path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8m-8 4h6"/>',
  bubble: '<path d="M4 4h16v13H9l-5 4zM8 8h8m-8 4h6"/>',
  sound: '<path d="M3 9h4l5-5v16l-5-5H3zm12-2q5 5 0 10m3-13q8 8 0 16"/>',
  mute: '<path d="M3 9h4l5-5v16l-5-5H3zm13 0 5 6m0-6-5 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  user: '<circle cx="12" cy="8" r="3"/><path d="M5 20q0-8 7-8t7 8"/>',
  clip: '<path d="m8 14 7-7q3-3 5 0t-1 5l-9 9q-4 3-7 0t0-7l10-10"/>',
  check: '<path d="m4 12 5 5 10-11"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  group:
    '<circle cx="9" cy="8" r="3"/><path d="M2 20q0-8 7-8t7 8m-1-15q5 0 4 5m-1 3q4 1 4 7"/>',
};
const icon = (key, size = 18) =>
  '<svg aria-hidden="true" width="' +
  size +
  '" height="' +
  size +
  '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">' +
  (paths[key] || "") +
  "</svg>";
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const safeUrl = (value) => {
  try {
    const u = new URL(value, location.origin);
    return ["http:", "https:"].includes(u.protocol) ? esc(u.href) : "";
  } catch {
    return "";
  }
};
const statusLabel = (value) =>
  '<span class="status ' +
  esc(value) +
  '">' +
  esc(statuses[value] || value) +
  "</span>";
const id = () =>
  globalThis.crypto?.randomUUID?.() ||
  Date.now().toString(36) + Math.random().toString(36).slice(2);
const btn = (action, label, cls = "secondary", extra = "") =>
  '<button type="button" class="' +
  cls +
  '" data-action="' +
  action +
  '" ' +
  extra +
  ">" +
  label +
  "</button>";
let toastTimer, audioEngine, lastCueAt = -Infinity;
function notify(message) {
  toast.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.textContent = ""), 4800);
}
function setting(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {}
}
state.sound = true;
function chime(frequency=392) {
  if (!state.sound) return;
  try {
    audioEngine ??= new AudioContext();
    audioEngine.resume().catch(() => {});
    const now = audioEngine.currentTime;
    if (now - lastCueAt < 0.25) return;
    lastCueAt = now;
    const oscillator = audioEngine.createOscillator(), gain = audioEngine.createGain();
    oscillator.type = "triangle";
    oscillator.frequency.setValueAtTime(frequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(frequency*0.94, now + 0.045);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.042, now + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.12);
    oscillator.connect(gain);
    gain.connect(audioEngine.destination);
    oscillator.onended = () => {
      oscillator.disconnect();
      gain.disconnect();
    };
    oscillator.start(now);
    oscillator.stop(now + 0.13);
  } catch {}
}
async function api(path, body) {
  let response;
  try {
    response = await fetch("/api/" + path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw Error("暂时连不上开题手记，请检查网络后重试。");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let m = data.error || data.detail || data.message || "操作未成功，请重试。";
    if (typeof m !== "string") m = JSON.stringify(m);
    if (Array.isArray(data.missing) && data.missing.length)
      m += " 待补：" + data.missing.join("、") + "。";
    const e = Error(m);
    e.status = response.status;
    e.code = data.code;
    throw e;
  }
  return data;
}
function mast() { return craftMast(); }
const teacher = () => state.user?.role === "teacher";
function login() { app.innerHTML = craftLogin(); }
async function signIn(username, password) {
  const result = await api("login", { username, password });
  state.user = result.user;
  state.activity = "";
  await home();
}
async function home() {
  state.home = await api("home");
  state.user = state.home.user;
  state.project = null;
  const projects = state.home.projects || [];
  if (returnProjectId) {
    const target = returnProjectId;
    returnProjectId = null;
    if (projects.some(project => String(project.id) === target)) return openProject(target);
    notify("当前账号无法打开这个项目，请从工作台选择项目。");
  }
  if (!teacher() && projects.length === 1) return openProject(projects[0].id);
  renderHome();
}
function renderHome() {
  if (teacher()) return renderTeacherHome();
  app.innerHTML = craftHome();
}
function rosterCategory(p) {
  if(p.status==='review')return 'review';
  if(p.status==='approved')return 'approved';
  if(p.review?.decision==='supplement')return 'supplement';
  return 'active';
}
function renderTeacherHome() {
  const acts=state.home.activities||[];
  const projects=(state.home.projects||[]).filter(p=>!state.activity||String(p.activity_id)===state.activity);
  const groups=[['review','待审阅','审阅开题'],['supplement','等补证','查看补证'],['active','进行中','查看进展'],['approved','已开题','查看研究任务']];
  const counts=Object.fromEntries(groups.map(([key])=>[key,projects.filter(p=>rosterCategory(p)===key).length]));
  const today=new Date(), date=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
  const rows=(key,action)=>projects.filter(p=>rosterCategory(p)===key).sort((a,b)=>key==='supplement'?(a.review?.due||'9999').localeCompare(b.review?.due||'9999'):0).map(p=>{
    const r=p.review||{}, overdue=key==='supplement'&&r.due&&r.due<date;
    const note=key==='review'?(r.decision==='supplement'?'补证后已重新提交，请复核更新后的成果。':'开题卡已提交，等待你的判断。'):key==='supplement'?r.deliverable:key==='approved'?p.next_action:r.decision==='redirect'?'按老师建议调整方向':names[(p.current_step||1)-1];
    const activity=acts.find(a=>String(a.id)===String(p.activity_id))?.title||'';
    return '<article class="queue-row"><div class="queue-person"><strong>'+esc(p.student_name)+'</strong>'+(!state.activity&&activity?'<span>'+esc(activity)+'</span>':'')+'</div><div class="queue-content"><h3>'+esc(p.title||'尚未确定题目')+'</h3>'+(note?'<p>'+esc(note)+'</p>':'')+researchTeacherSummary(p)+(key==='supplement'?'<div class="queue-deadline'+(overdue?' overdue':'')+'">'+esc(r.owner||'学生')+'负责'+(r.due?' · '+esc(r.due)+' 复核'+(overdue?' · 已到复核时间':r.due===date?' · 今天复核':''):'')+'</div>':'')+'</div>'+btn('project',action+' '+icon('arrow',15),key==='review'?'primary':'secondary','data-id="'+esc(p.id)+'"')+'</article>';
  }).join('');
  app.innerHTML=mast()+'<main id="main" class="wrap teacher-dashboard"><header class="dashboard-heading"><div><h1>老师工作台</h1></div>'+btn('publish',icon('plus')+' 发布活动','secondary')+'</header><div class="dashboard-tools"><select aria-label="筛选开题活动" id="activity-filter"><option value="">全部活动</option>'+acts.map(a=>'<option value="'+esc(a.id)+'" '+(String(a.id)===state.activity?'selected':'')+'>'+esc(a.title)+'</option>').join('')+'</select><div>'+ (state.activity?btn('edit-activity','修改活动要求','text-btn'):'')+btn('refresh-roster','刷新','text-btn')+'</div></div><nav class="queue-counts" aria-label="按学生状态筛选">'+groups.map(([key,label])=>btn('roster-filter','<span>'+label+'</span><strong>'+counts[key]+'</strong>','queue-count '+key+(state.rosterFilter===key?' selected':''),'data-key="'+key+'" aria-pressed="'+(state.rosterFilter===key)+'"')).join('')+'</nav><div class="queue-list-heading"><h2>'+(state.rosterFilter==='all'?'学生待办与进展':groups.find(g=>g[0]===state.rosterFilter)[1])+'</h2>'+btn('roster-filter','查看全部 · '+projects.length,'text-btn','data-key="all" aria-pressed="'+(state.rosterFilter==='all')+'"')+'</div>'+groups.filter(([key])=>state.rosterFilter==='all'||state.rosterFilter===key).map(([key,label,action])=>counts[key]?'<section class="queue-group" aria-label="'+label+'"><h2>'+label+'<span>'+counts[key]+'</span></h2>'+rows(key,action)+'</section>':'').join('')+((state.rosterFilter==='all'?projects.length:counts[state.rosterFilter])?'':'<p class="queue-empty">'+(projects.length?'当前活动没有这类学生。':acts.length?'这个范围内还没有学生项目。':'还没有开题活动，点击右上方“发布活动”开始。')+'</p>')+'</main>';
}
async function openProject(projectId) {
  state.project = await api("projects/" + encodeURIComponent(projectId));
  state.step = Number(state.project.current_step) || 1;
  state.tab = "work";
  state.discussions = null;
  state.coachUrl = "";
  state.reviewDraft = null;
  state.reviewDraftStale = false;
  if (teacher()) await loadReviewDraft();
  renderProject();
}
const current = () =>
  state.project.steps.find((s) => s.number == state.step) ||
  state.project.steps[0];
function road() {
  return (
    '<ol class="road">' +
    state.project.steps
      .map(
        (s) =>
          '<li><button class="' +
          esc(s.status) +
          '" data-action="step" data-n="' +
          s.number +
          '"><span class="node">' +
          (s.status === "complete" ? icon("check", 15) : s.number) +
          "</span><span>" +
          esc(names[s.number - 1]) +
          '</span><span class="sub">' +
          esc(statuses[s.status] || "") +
          "</span></button></li>",
      )
      .join("") +
    "</ol>"
  );
}
function fold(label, content) {
  if (!content) return "";
  return '<details class="support-fold"><summary>' + label + '</summary><div class="fold-body">' + content + '</div></details>';
}
function requirement() {
  const text = state.project.activity?.requirements?.trim();
  const budget = state.project.budget;
  return (text ? '<p class="value">' + esc(text) + '</p>' : '') + (budget ? '<p class="hint">年度安排：' + esc(budget.weeks) + ' 周 · 学生 '+esc(budget.student_hours)+' 小时（研究 '+esc(budget.research_hours)+' 小时）· 教师 '+esc(budget.teacher_hours)+' 小时</p>' : '');
}
function readingKey(tab) { return 'proposal.read.' + state.user.id + '.' + state.project.id + '.' + tab; }
function unreadCount(tab) {
  let seen=[]; try { seen=JSON.parse(setting(readingKey(tab)) || '[]'); } catch {}
  return (state.project.reading_items?.[tab] || []).filter(id=>!seen.includes(id)).length;
}
function markRead(tab) {
  if (!document.hidden && state.project.reading_items?.[tab]) setting(readingKey(tab), JSON.stringify(state.project.reading_items[tab]));
}
function stageStrip() {
  const labels=['兴趣探索','核心困惑','搜索与假设','研究框架','计划与答辩','开题决定'];
  const short=['选题','文献','价值','范围','验证','提交'];
  return '<nav class="stage-strip" aria-label="六阶段开题进度">'+state.project.steps.map((s,i)=>btn('step',
    '<span class="stage-number">'+(s.status==='complete'?'✓':i+1)+'</span><span class="stage-label">'+labels[i]+'</span><span class="stage-short">'+short[i]+'</span>',
    'stage-point '+(s.status==='complete'?'done ':'')+(s.number===state.project.current_step?'active':''),
    'data-n="'+s.number+'" aria-label="'+labels[i]+'，'+(s.status==='complete'?'已完成':s.number===state.project.current_step?'当前阶段':'待完成')+'"'+(s.number===state.project.current_step?' aria-current="step"':''))).join('')+'</nav>';
}
function celebrateStage() {
  if (teacher() || state.tab!=='work' || !unseenMilestone() || document.hidden) return;
  const key=milestoneKey()+'.celebrated';
  if (setting(key)) return;
  setting(key,'yes');
  document.querySelector('.stage-success')?.classList.add('celebrate');
  chime(392); setTimeout(()=>chime(494),300); setTimeout(()=>chime(587),600);
}
// Unlock audio on an ordinary student gesture, before leaving for Codex.
document.addEventListener('pointerdown',()=>{ if(state.sound) { try { audioEngine ??= new AudioContext(); audioEngine.resume().catch(()=>{}); } catch {} } },{capture:true});
function tabBtn(key, label, symbol) {
  const shortLabels = {
    work: "任务",
    card: "开题计划",
    research: "研究",
    files: "材料",
    feedback: "批注",
    learning: "学习记录",
  };
  return btn(
    "tab",
    icon(symbol, 17) +
      '<span class="wide-label">' +
      label +
      '</span><span class="narrow-label">' +
      shortLabels[key] +
      "</span>" + (unreadCount(key) ? '<span class="unread-count" aria-label="'+unreadCount(key)+' 条未读">'+unreadCount(key)+'</span>' : ''),
    "tab" + (state.tab === key ? " selected" : ""),
    'data-key="' +
      key +
      '" aria-current="' +
      (state.tab === key ? "page" : "false") +
      '"',
  );
}
function renderProject() {
  const previousTab = document.getElementById("tab-body")?.dataset.view;
  const p=state.project;
  if(!p)return;
  const job=coachJobs.get(p.id);
  if(job && job.kind!=="review" && job.stage!==coachStageIdentity(p)){coachJobs.delete(p.id);coachNotice();}
  if(state.tab!=="learning")markRead(state.tab);
  const body=state.tab==='research' ? researchWorkspace() : state.tab==='work' ? craftTaskLayout(workView()) : state.tab==='card' ? cardView() : state.tab==='files' ? fileView() : state.tab==='learning' ? learningView() : feedbackView();
  app.innerHTML=mast()+'<main id="main" class="wrap project-page '+(teacher()?'teacher-page':'student-page')+'">'+craftProjectChrome(p)+
    '<div class="tab-body'+(previousTab&&previousTab!==state.tab?' tab-enter':'')+'" id="tab-body" data-view="'+esc(state.tab)+'">'+body+((isResearch()?state.tab==='research':['work','card','research'].includes(state.tab))?qualityView(p):'')+(isResearch()&&state.tab==='research'?projectVersionHistory(p):'')+'</div></main>';
  if(previousTab&&previousTab!==state.tab)window.scrollTo(0,0);
  celebrateStage();
}
function workView() {
  if(isResearch())return researchTaskView();
  const p = state.project,
    s = current(),
    num = s.number,
    isCurrent = num === p.current_step;
  if(!teacher() && isCurrent && p.status==='active' && p.review?.decision==='supplement') return supplementView();
  if (!teacher() && isCurrent && p.status !== "approved" && unseenMilestone()) return milestoneView();
  if (teacher() && p.status === "review" && isCurrent) return teacherReviewView();
  const reviewed = p.status === "approved";
  const supplement = isCurrent && p.status === "active" && p.review?.decision === "supplement" && p.review.step === num ? p.review : null;
  if (reviewed && isCurrent && p.review?.decision === "approve") {
    const r = p.review;
    const clarification = (p.comments || []).filter(c => c.role === "teacher" && c.step === 6 && c.created >= r.created).at(-1);
    return '<div class="grid"><section class="panel first-task"><span class="eyebrow">老师已同意开题</span><h2>第一项研究任务</h2><p class="deliverable">' +
      esc(r.deliverable) + '</p>' + (clarification ? '<div class="first-note"><strong>老师补充</strong><p>' + esc(clarification.text) + '</p></div>' : '') +
      '<dl><dt>做到什么程度</dt><dd>' + esc(r.standard) +
      '</dd><dt>由谁完成</dt><dd>' + esc(r.owner) + '</dd><dt>何时交付</dt><dd>' +
      esc(r.due) + '</dd></dl><div class="actions">' + btn("tab","查看老师的判断","secondary",'data-key="card"') +
      (teacher()?btn("comment","补充交付说明","text-link"):btn("tab","就这项任务提问","text-link",'data-key="feedback"')) + '</div>' +
      '</section><aside class="stack">' + fold("查看开题进度", road()) + '</aside></div>';
  }
  const recentFeedback = (p.comments || [])
    .filter((c) => c.step === num && c.role === "teacher")
    .at(-1);
  const rows = taskRows(s);
  const items = rows ? '<dl>' + rows + '</dl>' : '';
  let controls = "";
  if (teacher())
    controls =
      btn("comment", "写批注", "primary") +
      (p.status === "review" ? btn("review", "审阅开题卡") : "");
  else if (isCurrent && !reviewed && p.status !== "review")
    controls =
      btn("launch", "去 Codex 讨论 " + icon("out", 16), "primary") +
      btn("edit", "写进展");
  else controls = btn("tab", "查看开题项目卡", "secondary", 'data-key="card"');
  const draft = readDraft(num);
  if (!teacher()) {
    const starting = isCurrent && num === 1 && !Object.values(s.data || {}).some(Boolean);
    const waiting = p.status === "review" && isCurrent;
    const heading = waiting ? "开题卡已提交，等待老师审阅" : starting ? "先聊一件让你好奇的事" : names[num - 1];
    const action = starting ? "生活里的观察、喜欢的学科，或老师给的方向，都可以作为起点。" : p.next_action || s.goal;
    const primary = isCurrent && !reviewed && !waiting
      ? (num === 6 ? btn("edit", "核对并提交老师审阅", "primary") + btn("launch", "请AI教练帮忙 " + icon("out", 16), "text-link") : btn("launch", (starting ? "跟AI教练开始讨论" : "继续跟AI教练讨论") + " " + icon("out", 16), "primary") + btn("edit", draft ? "继续填写草稿" : "整理讨论成果", "text-link"))
      : controls;
    const feedback = recentFeedback ? '<div class="next"><strong>老师的批注</strong><p>' + esc(recentFeedback.text) + '</p>' + btn("tab", "回应老师", "text-link", 'data-key="feedback"') + '</div>' : '';
    return '<div class="focus-work"><section class="panel focus-task">' + stageStrip() + '<span class="eyebrow">' +
      (isCurrent ? "当前任务" : "查看任务") + ' · ' + num + ' / 6</span><h2>' + esc(heading) +
      '</h2>' + (supplement ? '' : '<p class="focus-prompt">' + esc(waiting ? "老师的意见会显示在这里。" : isCurrent ? action : s.goal) + '</p>') + (supplement ? '<div class="next"><strong>老师请你补证</strong><p>' + esc(supplement.deliverable) + '</p><p class="hint">' + esc(supplement.owner) + '负责 · ' + esc(supplement.due) + '复核</p></div>' : '') +
      feedback + (s.recovered ? '<p class="hint">已有此前讨论的草稿，核对后继续。</p>' : '') + '<div class="actions">' + primary + '</div>' +
      (state.coachUrl && isCurrent ? '<p class="action-note"><a class="quiet-link" href="' + esc(state.coachUrl) + '">重新打开 Codex ↗</a></p>' : '') +
      (draft ? '<p class="hint action-note">有一份未提交的草稿</p>' : '') +
      fold("完成标准", '<p>' + esc(acceptance[num - 1]) + '</p>').replace('<details', '<details open') + '</section>' +
      (items ? fold("查看已记录的内容", items) : '') +
      '<div class="support-options">' + fold("开题进度 · " + p.steps.filter(step => step.status === "complete").length + "/6", road()) + fold("老师的要求", requirement()) + '</div>' + resetEntry() + '</div>';
  }
  return '<div class="focus-work"><section class="panel focus-task">' + stageStrip() + '<span class="eyebrow">' +
    esc(p.student_name) + ' · 任务 ' + num + ' / 6</span><h2>' + esc(names[num - 1]) +
    '</h2><p class="focus-prompt">' + esc(s.goal) + '</p><div class="actions">' + controls + '</div>' +
    fold("完成标准", '<p>' + esc(acceptance[num - 1]) + '</p>') + '</section>' +
    fold("查看学生已记录的内容", items) +
    (recentFeedback ? fold("最近的批注", '<p>' + esc(recentFeedback.text) + '</p>') : '') +
    '<div class="support-options">' + fold("开题进度", road()) + fold("老师的要求", requirement()) + '</div></div>';
}
function supplementView() {
  const p=state.project,r=p.review,ready=p.current_step===6,s=current();
  return '<div class="focus-work"><section class="panel focus-task supplement-task">'+stageStrip()+'<span class="eyebrow">'+(ready?'补证成果已保存':'老师请你补证')+'</span><h2>'+(ready?'核对开题，重新提交':'先补齐这项证据')+'</h2><div class="supplement-request"><span class="caption">老师要求补什么</span><p>'+esc(r.deliverable)+'</p><div class="supplement-date"><strong>'+esc(r.due)+' 前完成，供老师复核</strong><span>'+esc(r.owner)+'负责</span></div></div><ol class="supplement-path" aria-label="补证流程"><li'+(!ready?' aria-current="step"':'')+'>1 补充证据</li><li'+(ready?' aria-current="step"':'')+'>2 核对并重新提交</li><li>3 等待老师审阅</li></ol><p class="supplement-guidance">'+(ready?'核对新证据是否改变原判断，再提交。':'已有记录会保留。请按老师的要求补证。')+'</p><div class="actions">'+(ready?btn('edit','核对并重新提交','primary'):btn('launch','跟AI教练补证 '+icon('out',16),'primary')+btn('edit','填写补证成果','secondary'))+btn('tab','上传或查看材料','text-link','data-key="files"')+'</div>'+fold('查看老师的判断',readableText(r.value)+readableText(r.feasibility))+'</section>'+(taskRows(s)?fold('查看已保存成果','<dl>'+taskRows(s)+'</dl>'):'')+'</div>';
}

const reviewDecisions = {approve:"可开题", supplement:"补证后再判", redirect:"调整方向"};
async function loadReviewDraft() {
  if (!teacher() || !state.project) return false;
  const project = state.project, user = state.user.id;
  const result = await api('projects/'+encodeURIComponent(project.id)+'/review-draft');
  if (state.project?.id !== project.id || state.user?.id !== user || !teacher()) return false;
  const changed = JSON.stringify(state.reviewDraft) !== JSON.stringify(result.draft) || state.reviewDraftStale !== !!result.stale;
  state.reviewDraft = result.draft || null;
  state.reviewDraftStale = !!result.stale;
  return changed;
}
function reviewEvidence(value) {
  if (!value) return '';
  if (Array.isArray(value)) return '<ul>'+value.map(v=>'<li>'+esc(typeof v === 'string' ? v : JSON.stringify(v))+'</li>').join('')+'</ul>';
  return '<p class="value">'+esc(typeof value === 'string' ? value : JSON.stringify(value))+'</p>';
}
function teacherReviewView() { return craftReview(teacherReviewContent()); }
function teacherReviewContent() {
  const d = state.reviewDraft;
  const localAssistant = true;
  return '<div class="focus-work"><section class="panel focus-task review-summary">'+stageStrip()+
    '<div class="review-heading"><span class="eyebrow">开题审阅</span>'+(d ? '<span class="review-pending">待老师确认</span>' : '')+'</div><h2>'+
    (d ? '建议：'+esc(reviewDecisions[d.decision] || '待判断') : '一起核对这份开题卡')+'</h2>'+
    (d ? (state.reviewDraftStale ? '<p class="review-stale">课题或要求已更新，请重新审阅。</p>' : '')+
      '<dl class="review-reasons"><dt>研究价值</dt><dd>'+esc(d.value)+'</dd><dt>年度可行性</dt><dd>'+esc(d.feasibility)+
      '</dd><dt>下一步</dt><dd>'+esc(d.deliverable)+(d.owner || d.due ? '<p class="hint">'+esc([d.owner,d.due].filter(Boolean).join(' · '))+'</p>' : '')+'</dd></dl>' :
      '<p class="focus-prompt">'+(localAssistant ? '让 Codex 对照学生成果和活动要求，整理审阅建议。' : '对照活动要求和学生成果，填写并发布审阅意见。')+'</p>')+
    '<div class="actions">'+(localAssistant ? btn('review-coach', d ? '继续辅助审阅' : '请 Codex 辅助审阅', d ? 'secondary' : 'primary') : '')+
    btn('review', d ? (state.reviewDraftStale ? '查看过期草稿' : '核对并发布草稿') : '手工审阅', !localAssistant || (d && !state.reviewDraftStale) ? 'primary' : 'text-link')+(d && state.reviewDraftStale ? btn('review-manual','重新手工审阅','text-link') : '')+'</div>'+
    (d ? fold('查看证据与待补内容',(d.evidence?'<h3>判断依据</h3>'+reviewEvidence(d.evidence):'')+(d.gaps?'<h3>待核实事项</h3>'+reviewEvidence(d.gaps):'')+(d.annual_acceptance ? '<h3>当前活动验收依据</h3>'+reviewEvidence(d.annual_acceptance) : '')+(d.standard ? '<h3>完成标准</h3>'+reviewEvidence(d.standard) : '')) : '')+
    '</section>'+fold('查看学生成果',state.project.steps.map(s=>'<h3>'+esc(names[s.number-1])+'</h3><dl>'+taskRows(s)+'</dl>').join(''))+
    fold('老师的要求',requirement())+'</div>';
}
async function launchReviewCoach() {
  if (!teacher()) return;
  if (state.project.plugin_pilot) return launchPluginDialog();
  const project=state.project.id;
  let job=coachJobs.get(project);
  if(job?.status==='ready'){await openPreparedCoach(job);return;}
  if(job?.status==='starting'){showCoachWait(job);return;}
  job={project,user:state.user.id,kind:'review',title:state.project.student_name+' · 开题审阅',status:'starting'};
  coachJobs.set(project,job);showCoachWait(job);await prepareCoach(job);
}

function workspaceControls() {
  if (state.project.plugin_pilot) return '';
  if(teacher())return '';
  const w=state.project.workspace;
  return '<div class="workspace-entry">'+(w?.configured ? btn('open-folder',icon('book',16)+' 打开项目文件夹','text-link')+'<span class="workspace-path">'+esc(w.path)+'</span>' : btn('workspace','选择项目存储位置','text-link'))+'</div>';
}
function resetEntry() {
  return teacher() ? '' : workspaceControls();
}
function milestoneKey() {
  const m = state.project?.milestone;
  return "proposal.milestone." + (state.user?.id || state.user?.username || state.user?.name) + "." + state.project.id + "." + m?.step + "." + m?.version;
}
function unseenMilestone() {
  return state.project.milestone && setting(milestoneKey()) !== "seen";
}
function milestoneView() {
  const m = state.project.milestone;
  const submitted = m.kind === "submitted";
  const resubmitted=submitted&&state.project.review?.decision==='supplement';
  return '<section class="panel stage-success" aria-labelledby="stage-title">' + stageStrip() + '<span class="stage-seal" aria-hidden="true">' + icon("check", 27) +
    '</span><span class="eyebrow">' + (resubmitted?'补证后已重新提交':submitted ? "开题卡已提交" : "阶段 " + esc(m.step) + " · 已完成") +
    '</span><h2 id="stage-title">' + esc(resubmitted?'等待老师再次审阅':m.title || (submitted ? "等待老师审阅" : "这一阶段，完成了")) +
    '</h2>' + (resubmitted?'<p class="focus-prompt">已重新提交，等老师审阅。</p>':m.summary ? '<p class="focus-prompt">' + esc(m.summary) + '</p>' : '') +
    '<div class="actions">' + btn("next-stage", submitted ? "查看开题卡" : "进入下一阶段 " + icon("arrow",16), "primary") + '</div></section>';
}
function preserveView(render) {
  const y = window.scrollY;
  const details = [...document.querySelectorAll("#tab-body details")].map(e => [e.querySelector(":scope > summary")?.textContent, e.open]);
  render();
  document.querySelectorAll("#tab-body details").forEach((e,index) => {
    const candidate = details[index];
    const previous = candidate?.[0] === e.querySelector(":scope > summary")?.textContent ? candidate : null;
    if (previous) e.open = previous[1];
  });
  window.scrollTo(0, y);
}
let loadingDiscussions = false;
async function loadDiscussions() {
  if (loadingDiscussions || !state.project || state.tab !== "learning") return;
  const projectId = state.project.id;
  loadingDiscussions = true;
  try {
    const result = await api("projects/" + encodeURIComponent(projectId) + "/discussions");
    if (state.project?.id !== projectId) return;
    if (state.tab === "learning") markRead("learning");
    const changed = JSON.stringify(state.discussions) !== JSON.stringify(result);
    state.discussions = result;
    if (changed && state.tab === "learning" && !sheet.open) preserveView(renderProject);
  } catch (error) {
    if (state.project?.id !== projectId) return;
    if (state.tab === "learning") markRead("learning");
    state.discussions = { ...(state.discussions || {}), sync: { status: "error", message: error.message } };
    if (state.tab === "learning" && !sheet.open) preserveView(renderProject);
  } finally { loadingDiscussions = false; }
}
function learningView() {
  const data = state.discussions;
  if (!data) return '<section class="panel student-document"><h2>学习记录</h2><p role="status">正在读取学习记录…</p></section>';
  const conversations = (data.conversations || []).filter(c => c.messages?.some(m => m.text?.trim()));
  const feedback = (data.feedback || []).filter(f => f.observation?.trim());
  const sync = data.sync || {};
  const receipt = sync.last_receipt_at ? '<p class="hint">最近同步 '+esc(dateText(sync.last_receipt_at))+'</p>' : '';
  const status = sync.status === "error" ? '<p class="error" role="status">' + esc(sync.message || "记录同步暂时中断") + ' ' + btn("retry-learning", "重试", "text-link") + '</p>' :
    (sync.status === "syncing" ? '<p class="hint" role="status">最近一轮的回复还在同步。</p>' : sync.status === "unconfirmed" && !conversations.length ? '<p class="hint" role="status">讨论开始后，原话会同步到这里。</p>' : '') + receipt;
  const notes = feedback.length ? '<section class="panel"><h2>学习反馈</h2>' + feedback.map(f =>
    '<div class="entry learning-note">' + (f.dimension ? '<span class="caption">' + esc(f.dimension) + '</span>' : '') + readableText(f.observation) +
    (f.next_action ? '<div class="practice-note"><span class="caption">下一次试试</span>' + readableText(f.next_action) + '</div>' : '') +
    (f.evidence_id && conversations.some(c => c.messages.some(m => String(m.id) === String(f.evidence_id))) ? '<a class="quiet-link" href="#message-' + esc(f.evidence_id) + '" data-evidence="' + esc(f.evidence_id) + '">查看这次讨论 ↗</a>' : '') + '</div>').join('') + '</section>' : '';
  const history = conversations.map((c, index) => {
    const stageData=state.project.steps[c.step-1]?.data;
    const summary=c.step===5&&stageData?.revision_notes?stageData.revision_notes:stageData?.summary;
    return '<section class="learning-phase"><h3>'+esc(names[c.step-1]||c.title||'讨论记录')+'</h3>'+(summary?readableText(summary):'')+
    '<details id="discussion-'+index+'" class="doc-row discussion-thread"><summary><span>查看讨论原话</span><span class="section-status">' + c.messages.filter(m=>m.text?.trim()).length + ' 条消息</span>' +
    '</summary><div class="discussion-messages">' + c.messages.filter(m => m.text?.trim()).map(m =>
      '<article class="discussion-message ' + (m.role === 'user' ? 'student-message' : '') + '" id="message-' + esc(m.id) + '"><div class="meta"><strong>' +
      (m.role === 'user' ? esc(state.project.student_name || "学生") : 'AI 教练') + '</strong><time>' + esc(dateText(m.time)) + '</time></div>' + readableText(m.text) + '</article>').join('') + '</div></details></section>';
  }).join('');
  return '<div class="stack learning-record"><section class="panel student-document"><div class="panel-head"><h2>学习记录</h2></div>'+status+
    '<div class="student-reading">'+history+(!notes&&!history&&!status?'<p class="hint">跟 AI 教练讨论后，可以在这里查看原话。</p>':'')+'</div></section>'+notes+'</div>';
}
document.addEventListener("click", event => {
  const thread=event.target.closest("[data-thread]");
  if(thread){const target=document.getElementById(thread.dataset.thread);if(target)target.open=true;}
  const link = event.target.closest("[data-evidence]");
  if (!link) return;
  const message = document.getElementById("message-" + link.dataset.evidence);
  if (message) {
    for (let parent = message.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
    message.querySelectorAll('details').forEach(detail => detail.open = true);
  }
});

// Format stored text without rewriting it or trusting embedded HTML.
// Long transcripts remain available in full, but do not dominate the first view.
function readableText(value, compact = true) {
  const text = String(value ?? '').trim();
  if (!text) return '';
  const blocks = text.split(/\n+/).filter(line => line.trim()).flatMap(line => {
    const sentences = line.match(/[^。！？]+[。！？]?[”’]?|[。！？]/g) || [line];
    const chunks = []; let chunk = '';
    for (const sentence of sentences) {
      if (chunk && chunk.length + sentence.length > 170) { chunks.push(chunk); chunk = ''; }
      chunk += sentence;
    }
    if (chunk) chunks.push(chunk);
    return chunks;
  });
  const inline = text => esc(text).replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  const render = blocks => blocks.map(block => {
    const heading = block.match(/^#{1,4}\s+(.+)$/);
    return heading ? '<p class="prose-heading">' + inline(heading[1]) + '</p>' : '<p>' + inline(block) + '</p>';
  }).join('');
  const truncated = compact && (text.length > 480 || blocks.length > 5);
  const count = text.length > 900 ? 1 : 2;
  if (truncated && blocks.length <= count) {
    const original = blocks.join('');
    blocks.splice(0, blocks.length, original.slice(0,170), original.slice(170,340), original.slice(340));
  }
  return '<div class="prose">' + (truncated && blocks.length > count
    ? render(blocks.slice(0,count)) + '<details class="read-more"><summary><span class="more-label">展开完整记录</span><span class="less-label">收起完整记录</span><span class="reading-count">' + text.length + ' 字</span></summary><div class="prose-rest">' + render(blocks.slice(count)) + '</div></details>'
    : render(blocks)) + '</div>';
}
function paperView(p) {
  return (
    '<div class="paper"><h3>' +
    esc(p.title || "待命名论文") +
    "</h3>" +
    [
      ["出处", p.source],
      ["原文位置", p.location],
      ["研究与发现", p.finding],
      ["证据局限", p.limit],
      ["独立研究", p.study],
    ]
      .filter((x) => x[1])
      .map(
        ([k, v]) =>
          '<div class="paper-field"><span class="caption">' +
          k +
          "</span>" +
          (/^https?:\/\//.test(v)
            ? '<a href="' +
              safeUrl(v) +
              '" target="_blank" rel="noopener noreferrer">' +
              esc(v) +
              "</a>"
            : readableText(v)) +
          "</div>",
      )
      .join("") +
    ((state.project.files || []).some((f) => String(f.id) === String(p.file_id))
      ? fileLinks([p.file_id])
      : "") +
    "</div>"
  );
}
function fileLinks(ids) {
  const files = (state.project.files || []).filter(f => !ids || ids.map(String).includes(String(f.id)));
  if (!files.length) return "";
  return (
    '<div class="files">' +
    files
      .map(
        (f) =>
          '<a target="_blank" rel="noopener" href="' +
          safeUrl(f.url) +
          '">' +
          icon("clip", 15) +
          " " +
          esc(f.name) +
          "</a>",
      )
      .join("") +
    "</div>"
  );
}
function taskRows(step) {
  return (step.fields || []).map(field => {
    const value = step.data?.[field.key];
    if (!value || (typeof value === "string" && !value.trim())) return "";
    if (Array.isArray(value) && !value.length) return "";
    const content = field.key === "papers" ? value.map(paperView).join("") :
      field.key === "file_ids" ? fileLinks(value) : readableText(value);
    return content ? '<div class="record-row"><dt>' + esc(field.label) + "</dt><dd>" + content + "</dd></div>" : "";
  }).join("");
}
function cardView() {
  if(isResearch())return researchDeliverableView();
  const p = state.project;
  const records = p.steps.map(step => ({step, rows: taskRows(step)})).filter(record => record.rows);
  if (!records.length && !p.review) {
    return '<section class="panel"><p class="focus-prompt">完成讨论并保存成果后，会在这里汇成开题卡。</p>' +
      btn("tab", "回到当前任务", "primary", 'data-key="work"') + '</section>';
  }
  const expanded = records.find(record => record.step.number === p.current_step) || records.at(-1);
  const sections = records.map(({step, rows}) => '<details class="doc-row" ' +
    (step.number === expanded.step.number ? 'open' : '') + '><summary>' +
    '<span class="section-number">' + String(step.number).padStart(2,'0') + '</span><span>' + esc(names[step.number - 1]) + '</span><span class="section-status">' + esc(statuses[step.status] || step.status) + '</span>' +
    '</summary><div class="doc-content"><dl>' + rows + '</dl></div></details>').join("");
  return '<div class="stack proposal-document">' + (sections ? '<section class="panel"><div class="panel-head"><h2>' +
    (teacher() ? esc(p.student_name) + '的开题卡' : '我的开题卡') + '</h2>' +
    (!teacher() && p.status !== "approved" ? btn("revise", "调整选题", "text-link") : '') + '</div>' +
    sections + (teacher() && p.status === "review" ? btn("review-coach", state.reviewDraft ? "继续辅助审阅" : "请 Codex 辅助审阅", "primary") + btn("review", state.reviewDraft ? "核对并发布草稿" : "手工审阅") : '') + '</section>' : '') +
    reviewView() + fold("老师的要求", requirement()) + resetEntry() + '</div>';
}
function reviewView() {
  const r = state.project.review;
  if (!r)
    return '';
  const fields = {
    value: "研究价值",
    feasibility: "年度可行性",
    annual_acceptance: "当前活动验收依据",
    owner: "责任人",
    due: "约定日期",
    deliverable: "交付物",
    standard: "完成标准",
    evidence: "判断依据",
    gaps: "待核实事项",
  };
  return (
    '<section class="panel"><h2>' +
    esc(
      { approve: "可开题", supplement: "补证后再判", redirect: "调整方向" }[
        r.decision
      ] || "老师意见",
    ) +
    "</h2>" +
    Object.entries(fields)
      .filter(([k]) => r[k])
      .map(
        ([k, label]) =>
          '<div class="entry"><span class="caption">' +
          label +
          "</span>" +
          readableText(r[k]) +
          "</div>",
      )
      .join("") +
    "</section>"
  );
}
function fileView() {
  const materials=state.project.materials||[], files=state.project.files||[];
  const comparisons=state.project.steps.flatMap(s=>s.data?.source_comparisons||[]);
  const readings=materials.map(m=>{
    const match=comparisons.find(row=>[m.id,m.url].includes(row.reference));
    const label=m.lead?'阅读线索':/未独立核验|未能打开外部|未核验/.test(m.limit||'')?'学生自述节选 · 待核验':match?.reading_scope?researchDisplayValue('reading_scope',match.reading_scope):'研究参考';
    return '<article id="source-'+esc(m.id)+'" class="material-entry"><p class="caption">'+esc(label)+'</p><h3><a href="'+safeUrl(m.url)+'" target="_blank" rel="noopener noreferrer">'+esc(m.title||m.url)+' ↗</a></h3>'+
      (match?.location?'<p class="hint">阅读位置 '+esc(match.location)+'</p>':'')+readableText(m.help)+(m.limit?'<div class="source-limit"><strong>使用边界</strong>'+readableText(m.limit)+'</div>':'')+'</article>';
  }).join('');
  return '<section class="panel student-document material-page"><div class="panel-head"><h2>材料</h2>'+(!teacher()?btn('upload',icon('plus')+' 上传材料','secondary'):'')+'</div>'+
    (readings?'<div class="student-reading">'+readings+'</div>':'')+
    (files.length?'<h3 class="material-heading">上传的材料</h3>'+fileLinks():'')+
    (!readings&&!files.length?'<div class="panel empty">讨论中用到的文章会收在这里，也可以上传论文或小试记录。</div>':'')+'</section>';
}
function feedbackView() {
  const p = state.project;
  const comments = (p.comments || []).slice().reverse();
  const entries = comments.map(c =>
    '<div class="entry"><div class="meta"><b>' + esc(c.name) + '</b><span>' +
    esc(names[c.step - 1] || "项目卡") + '</span><time>' + esc(dateText(c.created)) +
    '</time></div>' + (isResearch()&&c.object_id?researchCommentLabel(c):'') + readableText(c.text) + '</div>');
  const unsubmitted=!teacher()&&p.status==='active'&&!p.submitted_deliverable&&!p.review;
  return '<div class="stack feedback-document"><section class="panel student-document"><div class="panel-head"><h2>批注</h2>' +
    btn("comment", teacher() ? "写批注" : comments.length ? "写回应" : "给老师留言", comments.length||teacher()?"primary":"secondary") + '</div><div class="student-reading">' +
    (entries[0] || '<p class="empty">'+(unsubmitted?'尚未提交老师审阅':'暂时没有批注')+'</p>') +
    (entries.length > 1 ? fold("查看之前的 " + (entries.length - 1) + " 条", entries.slice(1).join("")) : '') +
    '</div></section>'+(isResearch()?'':projectVersionHistory(p))+'</div>';
}
function projectVersionHistory(p){
  const history=(p.history||[]).slice().reverse();
  if(!history.length)return '';
  const rows=history.map(v=>'<li><span class="hint">版本 '+esc(v.version)+'</span><span>'+esc(v.reason?.replace(/^保存依据与选择：(?:session|support|claim)$/,'保存讨论记录')||'更新研究记录')+'</span>'+btn('version','查看版本 '+esc(v.version),'text-link','data-version="'+esc(v.version)+'"')+'</li>').join('');
  return fold('项目版本记录 · '+history.length+' 项','<ul class="version-list">'+rows+'</ul>'+btn('version','查看初始版本','text-link','data-version="1"'));
}
function dateText(s) {
  if (!s) return "";
  if (/T.*(?:Z|[+-]\d\d:\d\d)$/.test(String(s))) {
    const d = new Date(s), pad = n => String(n).padStart(2, "0");
    if (!Number.isNaN(d.getTime())) return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  return String(s).replace("T", " ").slice(0, 16);
}
function dialog(title, body, hint = "") {
  sheet.innerHTML =
    '<div class="dialog-inner"><div class="dialog-head"><div><h2 id="sheet-title" tabindex="-1">' +
    esc(title) +
    "</h2>" +
    (hint ? '<p class="hint">' + esc(hint) + "</p>" : "") +
    "</div>" +
    btn("close", "×", "icon-btn", 'aria-label="关闭"') +
    "</div>" +
    body +
    "</div>";
  if (!sheet.open) sheet.showModal();
  sheet.scrollTop = 0;
  sheet.querySelector('#sheet-title').focus({preventScroll: true});
}
function textField(
  name,
  label,
  value = "",
  type = "textarea",
  required = false,
) {
  const attr = ' name="' + esc(name) + '" ' + (required ? "required" : "");
  return (
    "<label>" +
    esc(label) +
    (type === "textarea"
      ? "<textarea" + attr + ' rows="2">' + esc(value) + "</textarea>"
      : "<input" +
        attr +
        ' type="' +
        esc(type) +
        '" value="' +
        esc(value) +
        '">') +
    "</label>"
  );
}
const formError = '<div class="error" role="alert"></div>';
function formEnd(action = "保存") {
  return (
    formError +
    '<div class="form-foot">' +
    btn("close", "取消") +
    '<button class="primary" type="submit">' +
    esc(action) +
    "</button></div>"
  );
}
function formStart(key) {
  return '<form class="form-stack" data-form="' + key + '">';
}
function draftKey(n) {
  return "proposal.draft." + state.user.id + "." + state.project.id + "." + n;
}
function readDraft(n) {
  try {
    return JSON.parse(setting(draftKey(n)) || "null");
  } catch {
    return null;
  }
}
function earlierNotes(step, data) {
  return step.fields.flatMap(({key,label}) => {
    const value = data?.[key];
    if (!value || (Array.isArray(value) && !value.length)) return [];
    let content = readableText(value);
    if (key === "papers") content = value.map(paperView).join("");
    if (key === "file_ids") content = fileLinks(value);
    return ['<div class="record-row"><dt>' + esc(label) + '</dt><dd>' + content + '</dd></div>'];
  }).join("");
}
function attachmentInput(key, ids) {
  return (
    "<fieldset><legend>关联已上传材料</legend>" +
    ((state.project.files || [])
      .map(
        (f) =>
          '<label class="check"><input type="checkbox" name="' +
          key +
          '" value="' +
          esc(f.id) +
          '" ' +
          ((ids || []).map(String).includes(String(f.id)) ? "checked" : "") +
          ">" +
          esc(f.name) +
          "</label>",
      )
      .join("") || '<p class="hint">选择下方文件即可上传并关联。</p>') +
    '<label class="local-upload">上传并关联文件<input type="file" data-inline-upload="trial"></label></fieldset>'
  );
}
function dynamicField(f, data) {
  const options =
    f.key === "tier"
      ? ["待定", "基础档", "丘奖目标档"]
      : f.key === "path"
        ? ["待定", "研究型", "应用型"]
        : null;
  if (options)
    return (
      "<label>" +
      esc(f.label) +
      '<select name="field-' +
      f.key +
      '">' +
      options
        .map(
          (v) =>
            "<option " +
            (v === data[f.key] ? "selected" : "") +
            ">" +
            esc(v) +
            "</option>",
        )
        .join("") +
      "</select></label>"
    );
  const field = textField(
    "field-" + f.key,
    f.label,
    data[f.key],
    f.key === "title" ? "text" : "textarea",
  );
  return f.competition
    ? "<div data-award-field " +
        (data.tier === "丘奖目标档" ? "" : "hidden") +
        ">" +
        field +
        "</div>"
    : field;
}
async function versionDialog(version) {
  const snapshot = await api(
    "projects/" +
      encodeURIComponent(state.project.id) +
      "/versions/" +
      encodeURIComponent(version),
  );
  const sections = snapshot.steps.map(step => {
    const rows = taskRows(step);
    return rows ? '<details class="doc-row"><summary>' + esc(step.title) + ' · ' +
      esc(statuses[step.status] || step.status) + '</summary><div class="doc-content"><dl>' +
      rows + '</dl></div></details>' : '';
  }).join("");
  dialog(
    "项目卡 · 版本 " + snapshot.version,
    '<div class="stack"><h3>' +
      esc(snapshot.title) +
      "</h3>" +
      (snapshot.activity?.requirements?.trim()
        ? '<p class="hint">当时的共同要求（版本 ' +
          esc(snapshot.activity.version) +
          "）　" +
          esc(snapshot.activity.requirements) +
          "</p>"
        : "") +
      "<div>" +
      (sections || '<p class="empty">这个版本尚未保存讨论成果。</p>') +
      "</div></div>",
  );
}
function paperInput(p = {}) {
  return (
    '<fieldset data-paper><legend>论文记录</legend><div class="form-stack">' +
    textField("paper-title", "论文题名", p.title, "text") +
    textField("paper-source", "论文原文链接（已上传文件可留空）", p.source, "text") +
    '<label>或关联已上传论文<select name="paper-file_id"><option value="">选择文件（可选）</option>' +
    (state.project.files || [])
      .map(
        (f) =>
          '<option value="' +
          esc(f.id) +
          '" ' +
          (String(p.file_id) === String(f.id) ? "selected" : "") +
          ">" +
          esc(f.name) +
          "</option>",
      )
      .join("") +
    '</select></label><label class="local-upload">上传这篇论文<input type="file" data-inline-upload="paper"></label>' +
    textField(
      "paper-location",
      "原文位置（页码、图表或段落）",
      p.location,
      "text",
    ) +
    textField("paper-finding", "研究对象、条件、方法及发现", p.finding) +
    textField("paper-limit", "这项证据能说明到哪里", p.limit) +
    textField(
      "paper-study",
      "这份证据来自哪项独立研究或实验",
      p.study,
      "text",
    ) +
    btn("remove-paper", "移除此条记录", "text-link") +
    "</div></fieldset>"
  );
}
function routeSelect(n, value) {
  const options =
    n === 3
      ? [
          ["continue", "值得投入一年，继续规划"],
          ["pilot", "先做小试，再判断价值"],
          ["revise", "调整研究问题"],
        ]
      : [
          ["continue", "沿用暂选问题"],
          ["revise", "调整研究问题"],
        ];
  return (
    '<label>我的选择<select name="field-route">' +
    options
      .map(
        ([k, v]) =>
          '<option value="' +
          k +
          '" ' +
          (value === k ? "selected" : "") +
          ">" +
          v +
          "</option>",
      )
      .join("") +
    "</select></label>"
  );
}
function editDialog() {
  if(isResearch())return researchProgressDialog();
  const s = current(),
    draft = readDraft(s.number),
    fresh =
      draft &&
      draft.version === state.project.version &&
      draft.requirement_version === state.project.activity?.version;
  const d = fresh ? draft.data : s.data || {};
  const earlier = draft && !fresh ? draft.data : draft?.earlier;
  const supplement=state.project.status==='active'&&state.project.review?.decision==='supplement';
  const fields = (s.fields || [])
    .filter((f) => f.key !== "route")
    .map((f) =>
      f.key === "papers"
        ? '<div class="stack"><div class="paper-head"><h3>共读论文</h3>' +
          btn("add-paper", icon("plus", 14) + " 增加论文") +
          '</div><p class="hint">上传或导师推荐均可，至少比较两篇独立来源，可随时继续增加。</p><div class="stack" id="paper-list">' +
          (d.papers || []).map(paperInput).join("") +
          "</div></div>"
        : f.key === "file_ids"
          ? attachmentInput("field-file_ids", d.file_ids)
          : dynamicField(f, d),
    )
    .join("");
  dialog(
    supplement?(s.number===6?'核对并重新提交':'填写补证成果'):"写进展",
    formStart("progress") +
      (supplement?'<div class="supplement-request"><strong>老师要求</strong><p>'+esc(state.project.review.deliverable)+'</p><span>'+esc(state.project.review.due)+' 前完成，供老师复核</span></div>':'')+
      (earlier
        ? '<div class="next"><strong>项目记录有更新</strong>请按最新要求核对，仍适用的草稿内容可以复制到下方。<details><summary>查看上次写下的内容</summary><dl class="value">' +
          earlierNotes(s, earlier) +
          "</dl></details></div>"
        : "") +
      '<details class="doc-row"><summary>本项任务怎样完成</summary><div class="doc-content">' +
      esc(acceptance[s.number - 1]) +
      "</div></details>" +
      fields +
      ([2, 3].includes(s.number) ? routeSelect(s.number, d.route) : "") +
      textField(
        "next_action",
        "自定下一步（可选）",
        fresh ? draft.next_action : "",
        "text",
      ) +
      '<label class="check"><input type="checkbox" name="confirmed" ' +
      (fresh && draft.confirmed ? "checked" : "") +
      '>'+(supplement&&s.number===6?'我已按老师要求补齐证据，并核对更新后的开题内容。':'我已核对本轮记录，内容符合自己的意思。')+'</label>' +
      formError +
      '<div class="form-foot"><button class="secondary" name="mode" value="draft">保存进展</button><button class="primary" name="mode" value="complete">' +
      (s.number === 6 ? (supplement?"重新提交老师审阅":"提交老师审阅") : supplement?"保存补证成果，继续核对":"提交本项成果") +
      "</button></div></form>",
    names[s.number - 1] + " · 可以只填写本轮新增的内容。",
  );
}
function progressPayload(form, complete) {
  const f = new FormData(form),
    s = current(),
    data = {};
  for (const field of s.fields) {
    const key = field.key;
    if (key === "papers") {
      data.papers = Array.from(form.querySelectorAll("[data-paper]"))
        .map((el) =>
          Object.fromEntries(
            Array.from(el.querySelectorAll("[name^=paper-]")).map((input) => [
              input.name.slice(6),
              input.value.trim(),
            ]),
          ),
        )
        .filter((p) => Object.values(p).some(Boolean));
    } else if (key === "file_ids") data.file_ids = f.getAll("field-file_ids");
    else data[key] = String(f.get("field-" + key) ?? "").trim();
  }
  if (f.has("field-route")) data.route = f.get("field-route");
  const payload = {
    step: s.number,
    data,
    complete,
    confirmed: f.has("confirmed"),
    version: state.project.version,
    requirement_version: state.project.activity.version,
    next_action: String(f.get("next_action") || "").trim(),
  };
  const existing = readDraft(s.number),
    serial = JSON.stringify(payload);
  return {
    ...payload,
    request_id: existing?.serial === serial ? existing.request_id : id(),
    serial,
  };
}
function keepDraft(form, complete = false) {
  const draft = progressPayload(form, complete);
  const prev = readDraft(draft.step);
  const outdated = prev && (prev.version !== draft.version || prev.requirement_version !== draft.requirement_version);
  setting(draftKey(draft.step), JSON.stringify({...draft, earlier:outdated ? prev.data : prev?.earlier}));
  return draft;
}
function activityDialog(edit = false) {
  const a = edit
    ? state.home.activities.find((x) => String(x.id) === state.activity)
    : {};
  dialog(
    edit ? "修改活动要求" : "发布开题活动",
    formStart(edit ? "edit-activity" : "publish") +
      textField("title", "活动名称", a?.title || "", "text", true) +
      textField(
        "requirements",
        "共同要求与成果标准",
        a?.requirements || "",
        "textarea",
        true,
      ) +
      textField("deadline", "开题期限", a?.deadline || "", "date", true) +
      (edit
        ? ""
        : "<fieldset><legend>参与学生</legend>" +
          state.home.students
            .map(
              (u) =>
                '<label class="check"><input name="student_ids" type="checkbox" value="' +
                esc(u.id) +
                '">' +
                esc(u.name) +
                "</label>",
            )
            .join("") +
          "</fieldset>") +
      formEnd(edit ? "保存新版要求" : "发布给所选学生") +
      "</form>",
    edit ? "保存后，学生会按新要求核对成果。" : "",
  );
}
const coachJobs = new Map();
const coachEndpoint = job => "projects/"+encodeURIComponent(job.project)+(job.kind==='review' ? "/review-coach" : "/coach");
function coachStageIdentity(p){return p.current_step+":"+(p.steps[p.current_step-1]?.cycle || 1);}
let waitingProject = null;
function coachNotice() {
  let box=document.getElementById('coach-notice');
  if(!box){box=document.createElement('aside');box.id='coach-notice';box.setAttribute('aria-label','导师准备状态');document.body.append(box);}
  const jobs=[...coachJobs.values()].filter(j=>j.user===state.user?.id && !(sheet.open && waitingProject===j.project));
  box.innerHTML=jobs.map(j=>'<div class="coach-notice-item"><span class="notice-light '+(j.status==='ready'?'ready':'')+'" aria-hidden="true"></span><div><strong>'+esc(j.status==='ready'?(j.kind==='review'?'辅助审阅已准备好':'导师已准备好'):j.status==='error'?'连接暂时中断':(j.kind==='review'?'正在准备辅助审阅':'导师正在准备'))+'</strong><small>'+esc(j.title)+'</small></div>'+btn(j.recovery?.action==='review'?'coach-recover':'coach-resume',j.recovery?.action==='review'?'核对已保存成果':j.status==='ready'?(j.kind==='review'?'进入 Codex':'进入讨论'):j.status==='error'?'重试':'查看','text-link','data-project="'+esc(j.project)+'"')+'</div>').join('');
}
function showCoachWait(job) {
  waitingProject=job.project;
  const review=job.kind==='review';
  if(!job.waitContext && state.project?.id===job.project) {
    job.waitContext={title:state.project.title,student:state.project.student_name};
  }
  const context=job.waitContext || {};
  const label=review?'正在审阅的项目':job.answer?'你刚才的话题':'本次讨论';
  const text=review?[context.student,context.title].filter(Boolean).join(' · '):job.answer || context.title || job.title;
  const message=review?'Codex 正在整理审阅建议，准备好后会自动打开审阅讨论。':'导师正在回复，准备好后会自动打开讨论';
  dialog(review?'正在准备审阅讨论':'正在准备你的讨论',
    '<section class="wait-context"><h3>'+label+'</h3><p>'+esc(text)+'</p></section>'+
    '<div class="coach-wait" role="status"><div class="waiting-garden" aria-hidden="true"><span class="waiting-orbit"></span><i></i><i></i><i></i></div><p class="wait-message">'+message+'</p><p class="wait-status">正在连接本地 Codex…</p></div>'+
    '<div class="wait-footer">'+btn('coach-background','先去看看项目','secondary')+'<span>切换页面后，准备好会提醒你。</span></div>');
  coachNotice();
}
async function openPreparedCoach(job, onlyIfActive=false) {
  // Only explicitly waiting in the foreground, or clicking “进入讨论”, opens Codex.
  const opened=await api(coachEndpoint(job),{background:false,...(onlyIfActive?{only_if_active:true}:{})});
  if(opened.opened===false)return false;
  coachJobs.delete(job.project);
  if(state.project?.id===job.project){state.coachUrl=job.url;renderProject();}
  if(waitingProject===job.project && sheet.open) sheet.close();
  coachNotice();
  return true;
}
async function prepareCoach(job) {
  try {
    let result=await api(coachEndpoint(job),{background:true,...(job.answer?{opening_answer:job.answer}:{})});
    while(result.status==='starting') {
      job.phase=result.phase;
      if(sheet.open && waitingProject===job.project){const line=sheet.querySelector('.wait-status');if(line)line.textContent=result.timeout_recovery||result.phase==='recovering_timeout'?'初稿生成较久，正在接续已有记录…':result.phase==='installing_skill'?'正在准备教练…':result.phase==='registering'?'正在设置 Codex…':result.phase==='recovering'?'上一轮未返回回复，正在接续已有记录…':result.phase==='composing'?(job.kind==='review'?'正在整理审阅建议…':'正在准备回复…'):'正在连接本地 Codex…';}
      await new Promise(resolve=>setTimeout(resolve,1200));
      if(state.user?.id!==job.user || coachJobs.get(job.project)!==job)return;
      result=await api(coachEndpoint(job));
    }
    if(state.user?.id!==job.user || coachJobs.get(job.project)!==job)return;
    if(result.status!=='ready'){job.recovery=result.recovery;throw Error(result.error || '连接中断，请重试。');}
    if(!/^codex:\/\/threads\/[0-9a-f-]+$/i.test(result.url || ''))throw Error('对话地址无效，请重试。');
    job.status='ready';job.url=result.url;
    if(state.project?.id===job.project)state.coachUrl=job.url;
    if(sheet.open && waitingProject===job.project && !document.hidden && document.hasFocus())await openPreparedCoach(job);
    else if(sheet.open && waitingProject===job.project && await openPreparedCoach(job,true)){}
    else {if(sheet.open && waitingProject===job.project)sheet.close();coachNotice();if(!document.hidden)chime();}
  } catch(error) {
    if(state.user?.id!==job.user || coachJobs.get(job.project)!==job)return;
    job.status='error';job.error=error.message;
    try {
      const latest=await api('projects/'+encodeURIComponent(job.project));
      if(state.project?.id===job.project){state.project=latest;state.step=latest.current_step;renderProject();}
      if(job.kind==='review'){
        const saved=await api('projects/'+encodeURIComponent(job.project)+'/review-draft');
        if(saved.draft&&!saved.stale)job.recovery={action:'review',message:'审阅草稿已保存，可以先核对；本轮回复尚未完成。'};
      }else job.recovery=(await api(coachEndpoint(job))).recovery;
    }catch(_){job.recovery=null;}
    if(sheet.open && waitingProject===job.project)showCoachError(job);
    coachNotice();
  }
}
function showCoachError(job) {
  const attrs='data-project="'+esc(job.project)+'"';
  dialog('本轮回复中断','<p class="error" role="alert">'+esc(job.error)+'</p>'+
    '<p>'+esc(job.recovery?.message || '可以继续原讨论，核对已保存记录后接续，不必重复回答。')+'</p>'+
    (job.recovery?.action==='review'?btn('coach-recover',job.kind==='review'?'核对已保存草稿':'核对已保存成果','primary',attrs):'')+
    btn('coach-resume','继续原讨论','secondary',attrs));
}
function workspaceDialog(continueAfter=false) {
  const w=state.project.workspace || {};
  dialog('设置课题文件夹', '<p class="workspace-intro">成果、文献和讨论记录将保存在这个文件夹。</p><form data-form="workspace" data-continue="'+(continueAfter?'yes':'no')+'"><label>存放位置<input name="parent" value="'+esc(w.recommended || '')+'" required autocomplete="off" spellcheck="false"></label><div class="workspace-choose">'+btn('pick-folder','选择其他文件夹…','text-link')+'</div><div class="workspace-preview"><span>将创建</span><strong>'+esc(w.folder_name || '我的研究项目')+'</strong><small>各阶段共用此文件夹。若重名，系统会自动加编号。</small></div><p class="error" role="alert"></p><button type="submit" class="primary">'+(continueAfter?'保存位置，开始讨论':'保存位置')+'</button></form>');
}
async function launchDialog() {
  if (state.project.plugin_pilot) return launchPluginDialog();
  if(state.project.workspace && !state.project.workspace.configured){workspaceDialog(true);return;}
  const project=state.project.id;
  if(state.project.opening_text && !coachJobs.has(project)) {
    dialog('先聊一件让你好奇的事', '<div class="static-opening">'+readableText(state.project.opening_text)+'</div><form data-form="opening-answer"><label>你的想法<textarea name="answer" rows="4" maxlength="4000" required placeholder="想到什么就说什么，不必组织成正式答案。"></textarea></label><p class="error" role="alert"></p><button type="submit" class="primary">发送想法 '+icon('arrow',16)+'</button></form>');
    return;
  }
  let job=coachJobs.get(project);
  if(job?.status==='ready'){await openPreparedCoach(job);return;}
  if(job?.status==='starting'){showCoachWait(job);return;}
  job={project,user:state.user.id,stage:coachStageIdentity(state.project),title:names[state.project.current_step-1],status:'starting'};
  coachJobs.set(project,job);showCoachWait(job);
  await prepareCoach(job);
}
async function launchPluginDialog() {
  const project = state.project, user = state.user.id;
  const active = () => state.project?.id === project.id && state.user?.id === user &&
    state.project.current_step === project.current_step && state.project.status === project.status &&
    JSON.stringify(state.project.submitted_deliverable) === JSON.stringify(project.submitted_deliverable);
  if (project.plugin_pilot.download) {
    const connection = await api('plugin-connection');
    if (!active()) return;
    if (connection.user?.id && connection.user.id !== user) throw Error('教学账号已切换，请刷新页面后再继续。');
    if (!connection.connected) return installCoachDialog(project, user);
  }
  const {os, path, openedHash} = pluginFolderPreference(project, user);
  if (path && openedHash) {
    try {
      const workspaceHash = await ProposalPluginPath.hash(path, os);
      if (!active()) return;
      if (workspaceHash === openedHash) {
        const entry = await api(`projects/${encodeURIComponent(project.id)}/plugin-entry`,
          {workspace_hash: workspaceHash, recovery: false, reuse: true});
        if (!active()) return;
        const url = ProposalPluginPath.link(entry, path, os);
        showPluginLaunchStatus(project, user, entry);
        window.location.href = url;
        return;
      }
    } catch (err) {
      if (active()) showPluginFolder(false, err.code === 'workspace_in_use'
        ? '这个文件夹已用于另一个课题。请换一个。' : err.message);
      return;
    }
  }
  showPluginFolder();
}

function pluginFolderPreference(project, user) {
  const os = ProposalPluginPath.platform(globalThis.navigator);
  const key = `proposal-${os}-folder:${user}:${project.id}`;
  const boundKey = `${key}:opened-hash`;
  try { return {os, key, boundKey, path:localStorage.getItem(key), openedHash:localStorage.getItem(boundKey)}; }
  catch { return {os, key, boundKey}; }
}
function pluginChangeFolderButton(isReview) {
  return '<button type="button" class="text-link" data-pilot-change-folder>更换'+(isReview?'审阅':'课题')+'文件夹</button>';
}

function pluginLaunchHelp(project, folderOptions) {
  return '<details class="coach-wizard-help" data-pilot-help><summary>如果打不开 Codex 或原来的讨论</summary>' +
    folderOptions + (project.plugin_pilot.download ? '<p>连接失效时，重新运行安装程序获取三位码。</p><button type="button" class="text-link" data-pilot-reconnect>重新连接 Codex</button>' : '') + '</details>';
}

function showPluginLaunchStatus(project, user, entry) {
  const isReview = teacher();
  dialog('打开 Codex', '<p>已请求打开 Codex。</p>' + pluginLaunchHelp(project,
    '<p>换了电脑或原文件夹不可用时，可以换一个文件夹继续'+(isReview?'审阅':'讨论')+'。</p>'+pluginChangeFolderButton(isReview)));
  const help = sheet.querySelector('[data-pilot-help]');
  sheet.querySelector('[data-pilot-change-folder]').addEventListener('click', () => showPluginFolder(false, '', true));
  sheet.querySelector('[data-pilot-reconnect]')?.addEventListener('click', () => installCoachDialog(project, user, true));
  if (entry.watch_open) waitForPluginBinding(entry.stage_session, () => sheet.open && help.isConnected);
}

async function waitForPluginBinding(session, isCurrent) {
  for (let check = 0; check < 30 && isCurrent(); check++) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    if (!isCurrent()) return;
    try {
      const status = await api('plugin-entry-status/' + encodeURIComponent(session));
      if (status.bound && isCurrent()) { sheet.close(); return; }
    } catch { return; }
  }
}

function showPluginFolder(justConnected = false, initialError = '', changingFolder = false) {
  const project = state.project, user = state.user.id, isReview = teacher();
  const {os, key, boundKey, path:remembered, openedHash:previousHash} = pluginFolderPreference(project, user);
  let openedHash = previousHash;
  dialog(isReview ? '选择审阅文件夹' : '选择课题文件夹',
    (justConnected ? installConnection.steps(3) + '<p class="coach-wizard-note">已连接。安装完成后，如果 Codex 正在运行，请先退出，再重新打开。</p>' : '') +
    '<p class="hint" id="pilot-path-help">每个课题使用独立文件夹。</p>' +
    '<div class="actions coach-folder-actions"><button type="button" class="secondary" data-pilot-choose>选择文件夹</button></div>' +
    '<label>' + (isReview ? '审阅文件夹' : '课题文件夹') + '<input data-pilot-folder aria-describedby="pilot-path-help pilot-path-error" autocomplete="off" spellcheck="false"' +
    ' placeholder="选好后自动填写"></label>' +
    '<p class="error" id="pilot-path-error" role="alert"></p>' +
    '<p data-pilot-status role="status"></p>' +
    '<p data-pilot-upgrade hidden><a href="/first-use.html">下载新版插件</a></p>' +
    '<div class="actions"><button type="button" class="primary" data-pilot-open>打开 Codex</button></div>' +
    pluginLaunchHelp(project, '<p>选好文件夹后，可接着'+(isReview?'审阅':'讨论')+'已保存的内容。</p>' +
      (remembered && !changingFolder ? pluginChangeFolderButton(isReview) : '') +
      '<button type="button" class="text-link" data-pilot-recover>恢复本机讨论</button>'));
  const folder = sheet.querySelector('[data-pilot-folder]');
  const choose = sheet.querySelector('[data-pilot-choose]');
  const open = sheet.querySelector('[data-pilot-open]');
  const recover = sheet.querySelector('[data-pilot-recover]');
  const error = sheet.querySelector('#pilot-path-error');
  const status = sheet.querySelector('[data-pilot-status]');
  const upgrade = sheet.querySelector('[data-pilot-upgrade]');
  const help = sheet.querySelector('[data-pilot-help]');
  const change = sheet.querySelector('[data-pilot-change-folder]');
  const active = () => state.project?.id === project.id && state.user?.id === user && sheet.open && folder.isConnected;
  let launchAttempt = 0;
  folder.value = remembered || '';
  error.textContent = initialError;
  if (changingFolder || initialError.includes('恢复本机讨论')) help.open = true;
  function validate() {
    try {
      const path = ProposalPluginPath.normalize(folder.value, os);
      folder.value = path;
      folder.removeAttribute('aria-invalid');
      error.textContent = '';
      return path;
    } catch (err) {
      folder.setAttribute('aria-invalid', 'true');
      error.textContent = err.message;
      return null;
    }
  }
  folder.addEventListener('blur', validate);
  folder.addEventListener('input', () => {
    folder.removeAttribute('aria-invalid');
    error.textContent = '';
    status.textContent = '';
  });
  async function selectFolder() {
    choose.disabled = open.disabled = recover.disabled = true;
    if (change) change.disabled = true;
    upgrade.hidden = true;
    status.textContent = '正在打开文件夹选择窗口…';
    try {
      const path = await ProposalPluginPath.pick('choose', active);
      if (!active()) return;
      if (path) {
        folder.value = path;
        validate();
      }
      status.textContent = '';
    } catch (err) {
      if (!active()) return;
      status.textContent = err.message;
      upgrade.hidden = err.code !== 'folder_helper_unavailable';
    } finally {
      choose.disabled = open.disabled = recover.disabled = false;
      if (change) change.disabled = false;
    }
  }
  async function launch(recovery) {
    if (!folder.value.trim()) {
      error.textContent = '请先选择文件夹。';
      choose.focus();
      return;
    }
    const path = validate();
    if (!path) { folder.focus(); return; }
    const attempt = ++launchAttempt;
    choose.disabled = open.disabled = recover.disabled = true;
    if (change) change.disabled = true;
    let occupied = false;
    try {
      const workspaceHash = await ProposalPluginPath.hash(path, os);
      const entry = await api(`projects/${encodeURIComponent(project.id)}/plugin-entry`, {workspace_hash: workspaceHash, recovery});
      if (state.project?.id !== project.id || state.user?.id !== user || !sheet.open || !folder.isConnected) return;
      if (!recovery && entry.thread_id && workspaceHash !== openedHash) throw Error('这个浏览器还没确认原来的课题文件夹。请点「恢复本机讨论」。');
      if (folder.value !== path) throw Error('路径已修改，请重新打开 Codex。');
      const url = ProposalPluginPath.link(entry, path, os);
      openedHash = workspaceHash;
      try {
        localStorage.setItem(key, path);
        localStorage.setItem(boundKey, workspaceHash);
      } catch { /* MCP still validates the actual folder. */ }
      status.textContent = '已请求打开 Codex。';
      window.location.href = url;
      if (entry.watch_open) waitForPluginBinding(entry.stage_session, () => active() && folder.value === path && launchAttempt === attempt);
    } catch (err) {
      if (state.project?.id !== project.id || state.user?.id !== user || !sheet.open || !folder.isConnected) return;
      error.textContent = err.code === 'workspace_in_use'
        ? '这个文件夹已用于另一个课题。请点「选择文件夹」换一个。'
        : err.message;
      if (err.code === 'workspace_in_use' && folder.value === path) {
        folder.setAttribute('aria-invalid', 'true');
        occupied = true;
      }
      if (err.message.includes('恢复本机讨论')) help.open = true;
    }
    finally {
      choose.disabled = open.disabled = recover.disabled = false;
      if (change) change.disabled = false;
      if (occupied) choose.focus();
    }
  }
  choose.addEventListener('click', selectFolder);
  change?.addEventListener('click', selectFolder);
  open.addEventListener('click', () => launch(false));
  recover.addEventListener('click', () => launch(true));
  sheet.querySelector('[data-pilot-reconnect]')?.addEventListener('click', () => installCoachDialog(project, user, true));
  if (justConnected || changingFolder) choose.focus();
}

function installCoachDialog(project, user, forcePair = false) {
  const downloads = project.plugin_pilot.downloads || {windows: project.plugin_pilot.download};
  const platform = ProposalPluginPath.platform(globalThis.navigator);
  const targets = [
    {key: 'windows', label: 'Windows', suffix: '.cmd'},
    {key: 'macos', label: 'macOS', suffix: '.command'}
  ].filter(target => downloads[target.key]);
  const preferred = targets.find(target => target.key === platform) || targets[0];
  const suffix = preferred?.suffix || '';
  const links = [preferred, ...targets.filter(target => target !== preferred)].filter(Boolean).map(target =>
    '<a class="coach-download '+(target === preferred ? 'coach-download-primary' : '')+'" href="'+esc(safeUrl(downloads[target.key]))+'" download>下载 '+target.label+' 安装包 <span aria-hidden="true">↓</span></a>'
  ).join('');

  function showInstall() {
    dialog('连接 Codex', installConnection.steps(1) +
      '<div class="coach-wizard-card"><h3>下载安装包</h3><div class="coach-downloads">'+links+'</div>' +
      '<p>解压后打开 <strong>安装开题手记'+suffix+'</strong>。确认网址，按回车，记下三位码。</p>' +
      (preferred?.key === 'macos' ? '<p class="hint">Mac 版需要 Python 3.12 或更新版本。</p>' : '') +
      '</div>' +
      '<div class="coach-wizard-actions"><button type="button" class="primary" data-coach-next>我已有三位连接码</button></div>');
    sheet.querySelector('[data-coach-next]').addEventListener('click', showPairing);
  }

  function showPairing() {
    dialog('连接 Codex', installConnection.steps(2) +
      '<div class="coach-wizard-card">' + installConnection.formMarkup + '</div>' +
      '<div class="coach-wizard-actions"><button type="button" class="text-link" data-coach-back>返回安装</button></div>');
    const form = sheet.querySelector('[data-install-connect]');
    sheet.querySelector('[data-coach-back]').addEventListener('click', showInstall);
    installConnection.mount(form, () => {
      if (state.project?.id !== project.id || state.user?.id !== user) return;
      showPluginFolder(true);
    }, {forcePair, focusPin: true, isActive: () => sheet.open && form.isConnected});
  }

  showInstall();
}
sheet.addEventListener('close',()=>{waitingProject=null;coachNotice();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)coachNotice();});
function reviewInputs(decision, draft = {}) {
  const f = (k, l, t = "textarea") => textField(k, l, draft[k] || "", t, true);
  return (
    f("value", "对研究价值的判断") +
    f("feasibility", "对当前活动可行性的判断") +
    textField("annual_acceptance", "当前活动验收依据", draft.annual_acceptance || "", "textarea", decision === "approve") +
    (decision === "approve"
      ? f("deliverable", "首项正式任务的交付物") +
        f("standard", "首项任务的完成标准")
      : decision === "supplement"
        ? '<label>回到哪项任务补证<select name="step">' +
          names
            .slice(0, 5)
            .map(
              (v, i) =>
                '<option value="' + (i + 1) + '" '+(Number(draft.step)===i+1?'selected':'')+'>' + esc(v) + "</option>",
            )
            .join("") +
          "</select></label>" +
          f("deliverable", "待补材料") + textField("standard", "补证完成标准", draft.standard || "", "textarea")
        : f("deliverable", "需要调整什么")) +
    textField("evidence", "判断依据", draft.evidence || "", "textarea") +
    textField("gaps", "待核实事项", draft.gaps || "", "textarea") +
    (decision === "redirect"
      ? ""
      : '<div class="pair">' +
        f("owner", "责任人", "text") +
        f("due", decision === "approve" ? "交付日期" : "复核日期", "date") +
        "</div>")
  );
}
async function verifyReviewDraft() {
  if (state.reviewEditingStale) throw Error("这份草稿已过期，请重新辅助审阅或重新手工审阅。");
}
function reviewDialog(manual = false) {
  if (!teacher()) return;
  const draft = manual ? {} : state.reviewDraft || {};
  const stale = !manual && state.reviewDraftStale && !!state.reviewDraft;
  state.reviewEditingStale = stale;
  state.reviewDraftRevision = state.reviewDraft?.revision ?? "";
  state.reviewEditing = {...draft};
  state.reviewVersions = {version:draft.project_version ?? state.project.version, requirement_version:draft.requirement_version ?? state.project.activity.version,...(isResearch()?{deliverable_version:draft.deliverable_version||state.project.submitted_deliverable,object_refs:draft.object_refs||[]}:{} )};
  dialog(
    "审阅开题卡",
    formStart("review") +
      (isResearch() && state.project.submitted_deliverable ? '<p class="hint">正在核对 '+esc(researchDeliverableLabel(state.project.submitted_deliverable))+'</p>' : '') +
      (stale ? '<p class="review-stale">这份草稿对应旧版材料。请关闭后重新审阅。</p>' : '') +
      '<label>审阅结论<select name="decision"><option value="approve">可开题</option><option value="supplement">补证后再判</option><option value="redirect">调整方向</option></select></label><div class="form-stack" id="review-fields">' +
      reviewInputs(draft.decision || "approve", draft) +
      "</div>" +
      '<div class="review-form-footer">' + formError + '<div class="review-form-actions">' + btn("save-review-draft", "暂存草稿", "secondary review-draft-save") + '<button class="primary" type="submit">确认并发布</button></div></div>' +
      "</form>",
  );
  sheet.querySelector('[name="decision"]').value = draft.decision || "approve";
  if (stale) sheet.querySelectorAll('[data-action="save-review-draft"], button[type="submit"]').forEach(button => button.disabled = true);
}
function coachStageChanged(next, previous) {
  return next.current_step !== previous?.current_step ||
    next.steps?.find(step => step.number === next.current_step)?.cycle !== previous?.steps?.find(step => step.number === previous.current_step)?.cycle;
}
async function acceptProject(project, message) {
  if (coachStageChanged(project, state.project)) state.coachUrl = "";
  state.project = project;
  state.step = project.current_step || state.step;
  if (sheet.open) sheet.close();
  renderProject();
  notify(message);
  chime();
}
function uploadDialog() {
  dialog(
    "上传研究材料",
    formStart("upload") +
      '<label>选择文件<input name="attachment" type="file" required></label><p class="hint">上传后可在阶段成果中引用。</p>' +
      formEnd("上传文件") +
      "</form>",
  );
}
function affectedOptions(start) {
  const candidates = state.project.steps.filter(
    (s) => s.number > start && s.number < 6 && s.status === "complete",
  );
  return candidates.length
    ? "<fieldset><legend>还需要重审哪些已完成任务？</legend>" +
        candidates
          .map(
            (s) =>
              '<label class="check"><input name="affected" value="' +
              s.number +
              '" type="checkbox" checked>' +
              esc(s.title) +
              "</label>",
          )
          .join("") +
        '<p class="hint">取消勾选可沿用仍然适用的成果。</p></fieldset>'
    : "";
}
async function uploadIntoDraft(input) {
  const file = input.files[0],
    form = input.form;
  if (!file?.size) throw Error("请选择有内容的文件。");
  if (form.dataset.busy) throw Error("正在保存，请稍后再试。");
  form.dataset.busy = "1";
  const previous = state.project;
  const known = new Set(previous.files.map((f) => f.id));
  input.disabled = true;
  try {
    const updated = await api(
      "projects/" + encodeURIComponent(previous.id) + "/files",
      { ...dataBase(), name: file.name, content_base64: await toBase64(file) },
    );
    const added = updated.files.find((f) => !known.has(f.id));
    state.project = updated;
    if (!added) throw Error("材料已保存，请从已上传文件中选择。");
    const paper = input.closest("[data-paper]");
    if (paper) {
      for (const select of form.querySelectorAll('[name="paper-file_id"]'))
        select.add(new Option(added.name, added.id));
      paper.querySelector('[name="paper-file_id"]').value = added.id;
    } else {
      input
        .closest("label")
        .insertAdjacentHTML(
          "beforebegin",
          '<label class="check"><input name="field-file_ids" type="checkbox" checked value="' +
            esc(added.id) +
            '">' +
            esc(added.name) +
            "</label>",
        );
    }
    keepDraft(form);
    notify("文件已上传并关联到本轮草稿");
  } finally {
    input.disabled = false;
    input.value = "";
    delete form.dataset.busy;
  }
}
async function toBase64(file) {
  if (file.size > 12 * 1024 * 1024)
    throw Error("单份材料限 12 MB，请拆分或压缩后再上传。");
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(Error("无法读取文件，请重新选择。"));
    r.onload = () => resolve(r.result.split(",")[1]);
    r.readAsDataURL(file);
  });
}
function report(err, form) {
  if (!form && sheet.open) form = sheet;
  const target = form?.querySelector(".error");
  if (target) {
    target.textContent = err.message;
    target.scrollIntoView({ block: "nearest" });
  } else notify(err.message);
}
function dataBase() {
  return {
    version: state.project.version,
    requirement_version: state.project.activity.version,
    request_id: id(),
  };
}
async function onAction(el) {
  const action = el.dataset.action;
  if(!el.closest?.('#sheet'))state.researchReviewActive=false;
  if(action.startsWith("research-")){await researchAction(el);return;}
  if(action==='quality-decide') { qualityDecisionDialog(el.dataset.id,el.dataset.decision); return; }
  if(action==='quality-refresh') { await refreshQualityDecision(); return; }
  if(action==='quality-evidence') { await qualityEvidence(el.dataset.evidenceId); return; }
  switch (action) {
    case "workspace":
      workspaceDialog(false);break;
    case "pick-folder": {
      const field=sheet.querySelector('[name="parent"]');
      const result=await api('projects/'+state.project.id+'/pick-folder',{});
      if(result.path && field?.isConnected)field.value=result.path;
      break;
    }
    case "open-folder":
      await api('projects/'+state.project.id+'/open-folder',{});break;
    case "coach-background":
      sheet.close();
      break;
    case "coach-recover": {
      const job=coachJobs.get(el.dataset.project);
      if(!job || job.user!==state.user?.id)break;
      sheet.close();await openProject(job.project);
      if(job.kind==='review')await onAction({dataset:{action:'review'}});
      else researchProgressDialog();
      coachJobs.delete(job.project);coachNotice();break;
    }
    case "coach-resume": {
      const job=coachJobs.get(el.dataset.project);
      if(!job || job.user!==state.user?.id)break;
      if(job.status==='ready')await openPreparedCoach(job);
      else if(job.status==='starting')showCoachWait(job);
      else {job.status='starting';showCoachWait(job);await prepareCoach(job);}
      break;
    }
    case "demo-student":
    case "demo-teacher":
      await signIn(
        action === "demo-student" ? "student" : "teacher",
        "yanjiu123",
      );
      break;
    case "logout":
      await api("logout", {});
      state.user = null;
      coachJobs.clear();coachNotice();
      state.home = null;
      state.project = null;
      login();
      break;
    case "sound":
      state.sound = !state.sound;
      setting("proposal.sound", state.sound ? "on" : "off");
      el.setAttribute("aria-pressed", String(state.sound));
      el.setAttribute(
        "aria-label",
        "提示音：" + (state.sound ? "已开启" : "已关闭"),
      );
      el.innerHTML = icon(state.sound ? "sound" : "mute");
      notify(state.sound ? "已开启保存提示音" : "已关闭提示音");
      chime();
      break;
    case "toggle-nav": craftToggleNav(); break;
    case "close-nav": craftCloseNav(true); break;
    case "projects":
    case "refresh-projects":
      state.home=await api("home"); state.project=null; renderHome(); break;
    case "project-tab":
      await openProject(el.dataset.id); state.tab=el.dataset.key; renderProject();
      if(state.tab==='learning')await loadDiscussions();
      break;
    case "home":
      await home();
      break;
    case "roster-filter":
      state.rosterFilter=el.dataset.key;
      renderHome();
      break;
    case "refresh-roster":
      await home();
      notify("已读取最新项目进度");
      break;
    case "project":
      await openProject(el.dataset.id);
      break;
    case "tab":
      state.tab = el.dataset.key;
      renderProject();
      if (state.tab === "learning") await loadDiscussions();
      break;
    case "retry-learning":
      await loadDiscussions();
      break;
    case "next-stage": {
      const milestone = state.project.milestone;
      setting(milestoneKey(), "seen");
      state.coachUrl = "";
      state.step = state.project.current_step;
      state.tab = milestone?.kind === "submitted" ? "card" : "work";
      renderProject();
      if (milestone?.kind !== "submitted") await launchDialog();
      break;
    }
    case "step":
      state.step = Number(el.dataset.n);
      state.tab = "work";
      renderProject();
      document.getElementById("tab-body").scrollIntoView({ block: "start" });
      break;
    case "publish":
      activityDialog();
      break;
    case "edit-activity":
      activityDialog(true);
      break;
    case "edit":
      editDialog();
      break;
    case "launch":
    case "prompt":
      await launchDialog();
      break;
    case "version":
      await versionDialog(el.dataset.version);
      break;
    case "add-paper":
      document
        .getElementById("paper-list")
        .insertAdjacentHTML("beforeend", paperInput());
      document
        .getElementById("paper-list")
        .lastElementChild.querySelector("input")
        .focus();
      break;
    case "remove-paper": {
      const row = el.closest("[data-paper]");
      row.remove();
      keepDraft(sheet.querySelector("form"));
      break;
    }
    case "comment":
      dialog(
        teacher() ? "写老师批注" : "给老师留言",
        formStart("comment") + researchCommentFields() +
          '<label>关联任务<select name="step">' +
          state.project.steps
            .map(
              (s) =>
                '<option value="' +
                s.number +
                '" ' +
                (s.number === state.step ? "selected" : "") +
                ">" +
                esc(names[s.number - 1]) +
                "</option>",
            )
            .join("") +
          "</select></label>" +
          textField(
            "text",
            teacher() ? "给学生的具体反馈" : "留言内容",
            "",
            "textarea",
            true,
          ) +
          formEnd("保存") +
          "</form>",
      );
      break;
    case "review-coach":
      await launchReviewCoach();
      break;
    case "save-review-draft": {
      await verifyReviewDraft();
      const form = el.closest("form");
      const values = Object.fromEntries(new FormData(form));
      if (values.step) values.step = Number(values.step);
      const result = await api("projects/"+state.project.id+"/review-draft", {...state.reviewEditing,...values,...state.reviewVersions,project_version:state.reviewVersions.version,draft_revision:state.reviewDraftRevision});
      state.reviewDraftRevision = result.draft?.revision ?? "";
      await loadReviewDraft();
      notify("审阅草稿已暂存");
      break;
    }
    case "review-manual":
      reviewDialog(true);
      break;
    case "review":
      reviewDialog();
      break;
    case "revise":
      dialog(
        "调整研究问题",
        formStart("revise") +
          textField(
            "title",
            "新一版研究问题",
            state.project.title,
            "text",
            true,
          ) +
          textField("reason", "什么依据让你调整问题？", "", "textarea", true) +
          '<label>从哪一项起重新核对<select name="from_step">' +
          names
            .slice(0, Math.min(5, state.project.current_step))
            .map(
              (s, i) =>
                '<option value="' + (i + 1) + '">' + esc(s) + "</option>",
            )
            .join("") +
          '</select></label><div id="affected-steps">' +
          affectedOptions(1) +
          '</div><label class="check"><input name="confirmed" type="checkbox" required>这是我选择的新方向，旧版本会保留。</label>' +
          formEnd("保存选题新版本") +
          "</form>",
      );
      break;
    case "reset-project":
      dialog('清空当前课题？',
        '<p class="focus-prompt">将删除这个课题在网站上的成果、材料、批注、版本和学习记录，并从第一项任务重新开始。</p>' +
        '<p class="hint">账号、老师要求和 Codex 聊天会保留。下次讨论会打开新聊天。</p>' +
        formStart('reset-project') + '<label class="check"><input type="checkbox" name="confirmed" required>我确认清空这个课题</label>' + formEnd('清除并重新开始') + '</form>');
      break;
    case "upload":
      uploadDialog();
      break;
    case "close":
      state.researchReviewActive=false;
      sheet.close();
      break;
  }
}
document.addEventListener("click", async (event) => {
  const el = event.target.closest("[data-action]");
  if (!el) return;
  event.preventDefault();
  if (el.dataset.busy) return;
  if(!["toggle-nav","close-nav"].includes(el.dataset.action))craftCloseNav();
  el.dataset.busy = "1";
  try {
    await onAction(el);
  } catch (e) {
    report(e, el.closest("form"));
  } finally {
    delete el.dataset.busy;
  }
});
document.addEventListener("change", (event) => {
  if (event.target.name === "from_step")
    document.getElementById("affected-steps").innerHTML = affectedOptions(
      Number(event.target.value),
    );
  if (event.target.matches("[data-inline-upload]")) {
    uploadIntoDraft(event.target).catch((err) => report(err, sheet));
    return;
  }
  if (event.target.id === "activity-filter") {
    state.activity = event.target.value;
    renderHome();
  }
  if (event.target.name === "field-tier")
    sheet.querySelectorAll("[data-award-field]").forEach((el) => {
      el.hidden = event.target.value !== "丘奖目标档";
    });
  if (event.target.name === "decision") {
    state.reviewEditing = {...state.reviewEditing,...Object.fromEntries(new FormData(event.target.form))};
    document.getElementById("review-fields").innerHTML = reviewInputs(event.target.value, state.reviewEditing);
  }
});
document.addEventListener("input", (event) => {
  const form = event.target.closest('[data-form="progress"]');
  if (form) keepDraft(form);
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  event.preventDefault();
  if (form.dataset.busy) return;
  form.dataset.busy = "1";
  const submitter = event.submitter || form.querySelector('[type="submit"]');
  if (submitter) submitter.disabled = true;
  const kind = form.dataset.form,
    f = new FormData(form),
    plain = Object.fromEntries(f);
  const target = form.querySelector(".error");
  if (target) target.textContent = "";
  try {
    if(kind?.startsWith("research-")){await researchSubmit(form,f);return;}
    if (kind === "quality-decision") {
      await submitQualityDecision(form, f);
      return;
    }
    if (form.id === "login-form") {
      await signIn(plain.username, plain.password);
      return;
    }
    if (kind === "workspace") {
      const continueAfter=form.dataset.continue==='yes';
      const project=state.project.id;
      await api('projects/'+project+'/workspace',{parent:String(f.get('parent') || '').trim()});
      state.project=await api('projects/'+project);sheet.close();renderProject();
      if(continueAfter)await launchDialog();
      return;
    }
    if (kind === "opening-answer") {
      const answer=String(f.get('answer') || '').trim();
      if(!answer)throw Error('先写一点你的想法。');
      const job={project:state.project.id,user:state.user.id,stage:coachStageIdentity(state.project),title:names[0],status:'starting',answer};
      coachJobs.set(job.project,job);delete state.project.opening_text;
      showCoachWait(job);await prepareCoach(job);return;
    }
    if (kind === "publish" || kind === "edit-activity") {
      if (kind === "publish") {
        plain.student_ids = f.getAll("student_ids");
        if (!plain.student_ids.length) throw Error("请选择至少一位参与学生。");
        const r = await api("activities", plain);
        state.activity = String(r.id || r.activity?.id || "");
      } else {
        const a = state.home.activities.find(
          (x) => String(x.id) === state.activity,
        );
        await api("activities/" + a.id, { ...plain, version: a.version });
      }
      sheet.close();
      await home();
      notify(kind === "publish" ? "开题活动已发布" : "新版活动要求已保存");
      chime();
      return;
    }
    const path = "projects/" + encodeURIComponent(state.project.id) + "/";
    let result;
    if (kind === "reset-project") {
      result = await api(path + "reset", {version:state.project.version,confirmed:f.has("confirmed")});
      coachJobs.delete(state.project.id);coachNotice();
      for (let step=1;step<=6;step++) setting(draftKey(step),null);
      sheet.close();
      history.replaceState(null,'',location.pathname+'?project='+encodeURIComponent(result.id));
      await openProject(result.id);
      notify('档案已清除，可以从第一项任务开始了');
      return;
    }
    if (kind === "progress") {
      const complete = submitter?.value === "complete";
      const payload = keepDraft(form, complete);
      if (!payload.confirmed)
        throw Error("请先核对本轮记录，再保存到个人项目。");
      delete payload.serial;
      result = await api(path + "progress", payload);
      setting(draftKey(payload.step), null);
      await acceptProject(
        result,
        complete ? "成果已提交，项目卡已更新" : "本轮进展已保存",
      );
      return;
    }
    if (kind === "comment") {
      result = await api(path + "comments", {
        ...dataBase(),
        ...plain,
        step: Number(plain.step),
        ...(isResearch()?researchCommentPayload(plain):{}),
      });
      state.tab = "feedback";
      await acceptProject(result, "批注与回应已保存");
      return;
    }
    if (kind === "review") {
      await verifyReviewDraft();
      result = await api(path + "review", {
        ...dataBase(),
        ...state.reviewVersions,
        draft_revision:state.reviewDraftRevision,
        ...plain,
        ...(plain.step ? { step: Number(plain.step) } : {}),
      });
      state.tab = "card";
      state.reviewDraft = null;
      await acceptProject(result, "审阅决定已发布");
      return;
    }
    if (kind === "revise") {
      result = await api(path + "revise", {
        ...dataBase(),
        ...plain,
        confirmed: f.has("confirmed"),
        from_step: Number(plain.from_step),
        affected_steps: f.getAll("affected").map(Number),
      });
      state.tab = "work";
      await acceptProject(result, "选题已更新，旧版本可在版本记录中查看");
      return;
    }
    if (kind === "upload") {
      const file = f.get("attachment");
      if (!file?.size) throw Error("请选择有内容的文件。");
      result = await api(path + "files", {
        ...dataBase(),
        name: file.name,
        content_base64: await toBase64(file),
      });
      state.tab = "files";
      await acceptProject(result, "材料已上传");
      return;
    }
  } catch (e) {
    if (e.status === 409 && state.project) {
      try {
        state.project = await api("projects/" + state.project.id);
        renderProject();
        if (kind === "progress") editDialog();
        report(
          Error("项目记录已更新。请核对最新要求和成果后重新提交。"),
          sheet,
        );
        return;
      } catch {}
    }
    report(e, form);
  } finally {
    delete form.dataset.busy;
    if (submitter) submitter.disabled = false;
  }
});
sheet.addEventListener("click", (e) => {
  if (e.target === sheet) {
    const r = sheet.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      sheet.close();
  }
});
let refreshing = false, refreshFailed = false;
async function refreshProject() {
  const old = state.project;
  if(!old && teacher() && state.home && !sheet.open && !document.hidden && !refreshing && !document.activeElement?.matches('input,textarea,select')) {
    const userId=state.user.id;
    refreshing=true;
    try {
      const latest=await api('home');
      if(!state.project && state.user?.id===userId && !sheet.open && JSON.stringify(latest)!==JSON.stringify(state.home)) {
        state.home=latest;preserveView(renderHome);
      }
      refreshFailed=false;
    } catch(error) { if(!refreshFailed)notify('记录暂未同步，正在重试。');refreshFailed=true; }
    finally {refreshing=false;}
    return;
  }
  if (!old || sheet.open || document.hidden || refreshing || document.activeElement?.matches("input,textarea,select")) return;
  refreshing = true;
  try {
    const fresh = await api("projects/" + encodeURIComponent(old.id));
    if (state.project !== old) return;
    const changedRequirements = fresh.activity?.version !== old.activity?.version;
    if (JSON.stringify(fresh) !== JSON.stringify(old)) {
      if (coachStageChanged(fresh, old)) state.coachUrl = "";
      state.project = fresh;
      if (fresh.current_step !== old.current_step || fresh.milestone?.version !== old.milestone?.version) state.step = fresh.current_step;
      preserveView(renderProject);
      if (changedRequirements) notify("老师已更新活动要求，请查看当前版本。");
    }
    if (teacher() && await loadReviewDraft()) preserveView(renderProject);
    if (refreshFailed) notify("已恢复同步，项目记录已更新。");
    refreshFailed = false;
    if (state.tab === "learning") await loadDiscussions();
  } catch (error) {
    if (!refreshFailed) notify(error.message + " 正在自动重试。");
    refreshFailed = true;
  } finally { refreshing = false; }
}
window.addEventListener("focus", refreshProject);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshProject(); });
sheet.addEventListener("close", refreshProject);
setInterval(refreshProject, 6000);

(async () => {
  try {
    const session = await api("me");
    state.demo = session.demo === true;
    state.user = session.user;
    if (state.user) await home();
    else login();
  } catch (e) {
    login();
    report(e, document.getElementById("login-form"));
  }
})();
