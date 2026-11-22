"""Local research coaching service. Run with python proposal_app/server.py."""
import argparse
import base64
import binascii
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
import uuid
from threading import Thread
from contextlib import closing
from datetime import date, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit
if __package__:
    from .coach_launcher import CoachLauncher
    from .review_launcher import ReviewLauncher
    from .project_archive import ProjectArchive
    from .workspace_store import WorkspaceStore
    from . import project_files, plugin_site, context_archive, runtime_config
    from . import skill_distribution
    from . import quality_records, research_service, workflow, research_export
else:
    from coach_launcher import CoachLauncher
    from review_launcher import ReviewLauncher
    from project_archive import ProjectArchive
    from workspace_store import WorkspaceStore
    import project_files, plugin_site, context_archive, runtime_config
    import skill_distribution
    import quality_records, research_service, workflow, research_export

ROOT = Path(__file__).resolve().parent
MAX_FILE = 12 * 1024 * 1024

TASKS = workflow.TASKS
NEXT = workflow.NEXT
VALUE_OPTIONS = {
    "path":"项目路径","tier":"本人确认的目标档位","subject":"拟报学科",
    "competitiveness":"目前的竞争力及判断依据","award_evidence":"什么证据会改变这个判断",
    "retained":"即使没有获奖，我仍想保留什么",
}
AWARD_FIELDS = {"subject","competitiveness","award_evidence","retained"}

class Problem(Exception):
    def __init__(self, status, message, missing=None):
        super().__init__(message)
        self.status, self.missing = status, missing

def uid(prefix):
    return prefix + uuid.uuid4().hex[:14]

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",",":"), sort_keys=True)

def clean(value):
    return value.strip() if isinstance(value, str) else ""

def required(body, keys):
    missing = [k for k in keys if not clean(body.get(k))]
    if missing:
        raise Problem(422, "请补全必填内容。", missing)

def step_number(value, maximum=6):
    if type(value) is not int or not 1 <= value <= maximum:
        raise Problem(422, "任务编号超出范围。")
    return value

def valid_date(value):
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise Problem(422, "请填写有效的日期。")

def connect(path):
    conn = sqlite3.connect(path, timeout=12)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def make_card(project, activity, student, name):
    return dict(id=project, activity_id=activity, student_id=student, student_name=name,
        title="正在探索的方向", workflow_version="tanyue-v1", tutor_mode="observation", current_step=1, status="active", version=1, next_action=NEXT[0],
        steps=[dict(number=i+1,title=t,goal=g,output=o,
            fields=[dict(key=k,label=l) for k,l in fields],data={},status="active" if i==0 else "pending")
            for i,(t,g,o,fields) in enumerate(TASKS)], review=None, files=[],comments=[],history=[])

def insert_card(conn, activity, student, demo=False):
    pid = uid("P")
    card = make_card(pid, activity, student["id"], student["name"])
    conn.execute("INSERT INTO projects VALUES(?,?,?,?)",(pid,activity,student["id"],dump(card)))

def init_db(path, demo=True):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    if Path(path).exists():
        with closing(connect(path)) as old:
            if old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='projects'").fetchone():
                if any(json.loads(r[0]).get('workflow_version') != 'tanyue-v1' for r in old.execute('SELECT card FROM projects')):
                    raise ValueError('这是旧六阶段数据库。请为新版指定独立 --db 路径；旧库与原服务保持不变。')
    with closing(connect(path)) as c, c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
          CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE,name TEXT,role TEXT,salt BLOB,pw BLOB);
          CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user TEXT REFERENCES users(id),expires REAL);
          CREATE TABLE IF NOT EXISTS activities(id TEXT PRIMARY KEY,teacher TEXT REFERENCES users(id),title TEXT,requirements TEXT,deadline TEXT,version INTEGER);
          CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,activity TEXT REFERENCES activities(id),student TEXT REFERENCES users(id),card TEXT,UNIQUE(activity,student));
          CREATE TABLE IF NOT EXISTS review_drafts(project TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,draft TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS scoped_sessions(token TEXT PRIMARY KEY REFERENCES sessions(token) ON DELETE CASCADE,project TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS coach_sessions(token TEXT PRIMARY KEY REFERENCES sessions(token) ON DELETE CASCADE,project TEXT NOT NULL,step INTEGER NOT NULL,cycle INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS revisions(project TEXT,version INTEGER,card TEXT,PRIMARY KEY(project,version));
          CREATE TABLE IF NOT EXISTS requests(project TEXT,actor TEXT,key TEXT,digest TEXT,result TEXT,PRIMARY KEY(project,actor,key));
          CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,project TEXT REFERENCES projects(id),name TEXT,content BLOB);
          CREATE TABLE IF NOT EXISTS activity_versions(activity TEXT,version INTEGER,record TEXT,PRIMARY KEY(activity,version));
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE IF NOT EXISTS project_resets(id TEXT PRIMARY KEY,owner TEXT,created TEXT,snapshot TEXT);
        """)
        research_service.init_schema(c)
        c.execute("CREATE TABLE IF NOT EXISTS activity_config(activity TEXT PRIMARY KEY REFERENCES activities(id), budget TEXT NOT NULL)")
        c.execute("BEGIN IMMEDIATE")
        if demo and not c.execute("SELECT 1 FROM users").fetchone():
            c.execute("INSERT OR REPLACE INTO settings VALUES('demo','1')")
            for key,login,name,role in [("U1","teacher","周老师","teacher"),("U2","student","林知遥","student"),("U3","student2","陈以安","student")]:
                salt = secrets.token_bytes(16)
                pw = hashlib.pbkdf2_hmac("sha256", b"yanjiu123", salt, 240000)
                c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",(key,login,name,role,salt,pw))
            c.execute("INSERT INTO activities VALUES(?,?,?,?,?,?)",("A001","U1","高二科研开题","从自己的兴趣或老师给的方向出发，选择一个值得投入一年的问题。用文献和小试说明你的选择、价值与限制。","2026-12-04",1))
            for s in c.execute("SELECT * FROM users WHERE role='student'").fetchall():
                insert_card(c,"A001",s,True)

def public_user(row):
    return {k:row[k] for k in ("id","name","role","username")}

def activity_budget(c, aid, supplied=None):
    row=c.execute('SELECT budget FROM activity_config WHERE activity=?',(aid,)).fetchone()
    prior=json.loads(row[0]) if row else dict(workflow.BUDGET)
    if supplied is None: return prior
    if not isinstance(supplied,dict) or set(supplied)!=set(workflow.BUDGET):
        raise Problem(422,'请提供完整的课程工时配置。')
    if any(type(v) not in (int,float) or not 0 < v <= 10000 for v in supplied.values()):
        raise Problem(422,'课程工时必须为有效正数。')
    if abs(supplied['student_hours']-supplied['teacher_hours']-supplied['research_hours'])>0.001:
        raise Problem(422,'总工时应等于自主研究加师生指导，指导工时不重复相加。')
    if abs(supplied['weeks']*supplied['weekly_minutes']/60-supplied['student_hours'])>0.001:
        raise Problem(422,'周数、每周分钟数与学生总工时不一致。')
    c.execute('INSERT INTO activity_config VALUES(?,?) ON CONFLICT(activity) DO UPDATE SET budget=excluded.budget',(aid,dump(supplied)))
    return supplied


def project_for(c, user, pid):
    row = c.execute("SELECT p.card,a.* FROM projects p JOIN activities a ON p.activity=a.id WHERE p.id=? AND (p.student=? OR a.teacher=?)",(pid,user["id"],user["id"])).fetchone()
    if not row:
        raise Problem(404,"找不到这个项目，或当前账号没有访问权限。")
    card=json.loads(row["card"])
    card["activity"]={k:row[k] for k in ("id","title","requirements","deadline","version")}
    budget_row=c.execute('SELECT budget FROM activity_config WHERE activity=?',(card['activity_id'],)).fetchone()
    card["budget"] = json.loads(budget_row[0]) if budget_row else dict(workflow.BUDGET)
    card["stage_contract"] = {"active_step": card["current_step"], "save_drafts_ahead": True,
        "completion": "仅提交当前任务且 complete=true 成功，才表示该阶段完成；完成后回网站，不在本对话启动下一阶段。"}
    card.setdefault('quality', {'records': []})
    card['teaching_skill_version'] = skill_distribution.version()
    research_service.enrich(c,card)
    return card

def assert_role(user, role):
    if user["role"] != role:
        raise Problem(403,"当前账号不能执行此操作。")

def validate_papers(papers, file_ids):
    if not isinstance(papers,list) or any(not isinstance(p,dict) for p in papers):
        raise Problem(422,"请按篇记录论文。")
    studies=set()
    used_titles=set()
    used_refs=set()
    for paper in papers:
        ref=clean(paper.get("file_id"))
        if ref and ref not in file_ids:
            raise Problem(422,"论文引用的材料不属于本项目。")
        source=clean(paper.get("source"))
        try:
            address=urlsplit(source)
            shared_link=address.scheme.lower() in ("http","https") and bool(address.hostname)
        except ValueError:
            shared_link=False
        reference=ref or (source.partition("#")[0].casefold() if shared_link else "")
        if not all(clean(paper.get(k)) for k in ("title","study","location","finding","limit")) or not reference:
            continue
        study=clean(paper["study"]).casefold()
        title=clean(paper["title"]).casefold()
        if title not in used_titles and reference not in used_refs:
            studies.add(study)
            used_titles.add(title)
            used_refs.add(reference)
    return len(studies)>=2

def current(card, step):
    workflow.set_navigation_stage(card,step)
    card["status"]="active"
    card["steps"][step-1]["status"]="active"
    card["next_action"]=NEXT[step-1]

def reopen(card, step, through=6):
    for s in card["steps"][step-1:through]:
        s["status"]="pending"
        s["cycle"]=s.get("cycle",1)+1
    card.pop("milestone",None)
    current(card,step)

def save_progress(card,b,user):
    assert_role(user,"student")
    if quality_records.unresolved_calculations(card,b.get('step',6)) and b.get('complete'):
        raise Problem(422,'仍有算式复算不一致的关键判断，请更正依据后再完成。')
    try:
        return workflow.save_progress(card,b,user)
    except research_service.Conflict as error:
        raise Problem(409,str(error)) from error
    except ValueError as error:
        raise Problem(422,str(error)) from error


def revision(card,b,user):
    raise Problem(422,'请对具体研究对象保存修改建议，再由学生在网站决定；不直接改写题目。')


def review(card,b,user):
    assert_role(user,'teacher')
    refs=b.get('object_refs',[])
    if not isinstance(refs,list): raise Problem(422,'请使用对象版本列表定位审阅。')
    for ref in refs:
        if not isinstance(ref,dict) or not any(o['id']==ref.get('id') and o['revision']==ref.get('revision') for o in card.get('research',{}).get('objects',[])):
            raise Problem(409,'审阅对象版本已变化。')
    try:
        result=workflow.review(card,b,user)
    except research_service.Conflict as error: raise Problem(409,str(error)) from error
    except ValueError as error: raise Problem(422,str(error)) from error
    return result


def read_review_draft(c,pid):
    row=c.execute("SELECT draft FROM review_drafts WHERE project=?",(pid,)).fetchone()
    draft=json.loads(row[0]) if row else None
    if draft:
        # Older local drafts get a stable revision without changing state on GET.
        draft.setdefault("revision",str(uuid.uuid5(uuid.NAMESPACE_URL,dump(draft))))
    return draft


def check_draft_revision(c,pid,revision):
    if revision is not None and not isinstance(revision,str):
        raise Problem(422,"草稿版本应为字符串或 null。")
    draft=read_review_draft(c,pid)
    expected=draft["revision"] if draft else ""
    if (revision or "")!=expected:
        raise Problem(409,"审阅草稿已有更新，请重新读取后核对，避免覆盖老师的修改。")


def review_draft(c,user,card,b=None):
    assert_role(user,"teacher")
    draft=read_review_draft(c,card["id"])
    if b is not None:
        if "draft_revision" not in b or (b["draft_revision"] is not None and not isinstance(b["draft_revision"],str)):
            raise Problem(422,"保存草稿需要读取时的草稿版本；首次保存请传 null。")
        check_draft_revision(c,card["id"],b["draft_revision"])
        if (type(b.get("project_version")) is not int or type(b.get("requirement_version")) is not int):
            raise Problem(422,"草稿需要当前项目版本和要求版本。")
        if b["project_version"]!=card["version"] or b["requirement_version"]!=card["activity"]["version"]:
            raise Problem(409,"项目或老师的要求已有更新，请重新读取后核对。")
        if b.get("decision")=="supplement":
            step_number(b.get("step"),5)
        # Reuse the publishing validation on a copy; drafts never mutate the card.
        review(json.loads(dump(card)),b,user)
        if b.get("due"):
            valid_date(b["due"])
        for key in ("evidence","gaps"):
            if key in b and (not isinstance(b[key],str) or len(b[key])>4000):
                raise Problem(422,"依据和缺口应为简短文字。")
        fields=("decision","value","feasibility","annual_acceptance","deliverable","standard","owner","due","evidence","gaps")
        draft={key:clean(b.get(key)) for key in fields}
        draft['deliverable_version']=card.get('submitted_deliverable') or card.get('submitted_deliverable_id')
        draft['object_refs']=b.get('object_refs',[])
        draft.update(step=b.get("step") if b["decision"]=="supplement" else (1 if b["decision"]=="redirect" else None),
                     project_version=card["version"],requirement_version=card["activity"]["version"],updated=now(),revision=str(uuid.uuid4()))
        c.execute("INSERT INTO review_drafts VALUES(?,?) ON CONFLICT(project) DO UPDATE SET draft=excluded.draft",(card["id"],dump(draft)))
    stale=bool(draft and (draft["project_version"]!=card["version"] or draft["requirement_version"]!=card["activity"]["version"] or card["status"]!="review"))
    return dict(draft=draft,stale=stale)


def attachment(c,card,b):
    required(b,["name","content_base64"])
    name=Path(b["name"].replace("\\","/")).name
    if not name or len(name)>240 or any(ord(x)<32 for x in name):
        raise Problem(422,"文件名无效。")
    try:
        content=base64.b64decode(b["content_base64"],validate=True)
    except (binascii.Error,ValueError):
        raise Problem(422,"文件内容无法读取，请重新选择。")
    if not content or len(content)>MAX_FILE:
        raise Problem(413,"单份材料需大于零字节且不超过 12 MiB。")
    fid=uid("F")
    c.execute("INSERT INTO files VALUES(?,?,?,?)",(fid,card["id"],name,content))
    origin=b.get('material_origin', 'unspecified')
    if origin not in ('ai_generated','student_selected','unspecified'): origin='unspecified'
    card["files"].append(dict(id=fid,name=name,size=len(content),url="/api/files/"+fid,created=now(),material_origin=origin,sha256=hashlib.sha256(content).hexdigest()))
    return "添加材料："+name

def write_card(c,user,card,action,b,student_messages=None,coach=False):
    key=clean(b.get("request_id"))
    if (action in ("revise","progress","quality","quality-decision") or action.startswith("research-")) and (not key or type(b.get("version")) is not int):
        raise Problem(422,"提交需要当前项目版本和写入编号。")
    digest=hashlib.sha256((action+dump(b)).encode()).hexdigest()
    if key:
        prior=c.execute("SELECT * FROM requests WHERE project=? AND actor=? AND key=?",(card["id"],user["id"],key)).fetchone()
        if prior:
            if prior["digest"]!=digest:
                raise Problem(409,"这个写入编号已经用于不同的提交。")
            saved=json.loads(prior['result']) if prior['result'].startswith('{') else None
            return dict(saved or card,result_id=(saved or {}).get('result_id',prior['result']))
    if b.get("version",card["version"])!=card["version"] or b.get("requirement_version",card["activity"]["version"])!=card["activity"]["version"]:
        raise Problem(409,"项目或老师的要求已有更新，请重新读取后核对。")
    before=dump({k:v for k,v in card.items() if k not in ("history","_student_messages","student_message_ids")})
    if action.startswith('research-'):
        assert_role(user,'student')
        if card['status'] != 'active': raise Problem(409,'当前项目不在讨论阶段。')
        reason=research_service.mutate(c,card,action,b,user,coach=coach,student_messages=student_messages)
    elif action=="progress":
        if (b.get('complete') or b.get('confirmed')) and coach:
            raise Problem(403,'请学生回网站核对并最终提交。')
        card['_student_messages']=student_messages or {}
        reason=save_progress(card,b,user)
        if b.get('step')==3 and b.get('complete') is True:
            research_service.capture_reading_sources(c,card)
    elif action=="revise":
        reason=revision(card,b,user)
    elif action=="review":
        if "draft_revision" in b:
            check_draft_revision(c,card["id"],b["draft_revision"])
        reason=review(card,b,user)
        c.execute("DELETE FROM review_drafts WHERE project=?",(card["id"],))
    elif action=="files":
        reason=attachment(c,card,b)
    elif action=="comments":
        required(b,["text"])
        n=step_number(b.get("step",card["current_step"]))
        card["comments"].append(dict(id=uid("C"),step=n,name=user["name"],role=user["role"],text=b["text"].strip(),created=now()))
        comment=card['comments'][-1]
        if b.get('object_id'):
            if not any(o['id']==b['object_id'] and o['revision']==b.get('object_revision') for o in card.get('research',{}).get('objects',[])):
                raise Problem(409,'批注对象已有新版本，请刷新核对。')
            comment.update(object_id=b['object_id'],object_revision=b['object_revision'])
        if b.get('peer_name'):
            comment.update(peer_name=clean(b['peer_name'])[:100],recorded_by=user['name'],feedback_type='peer_recorded')
        reason="老师批注" if user["role"]=="teacher" else "学生回应"
    elif action in ('quality', 'quality-decision'):
        assert_role(user, 'student')
        if card['status'] != 'active':
            raise Problem(409, '当前项目不在讨论阶段，请先回网站查看老师决定。')
        try:
            if action == 'quality' and b.get('kind') == 'proposal' and b.get('record',{}).get('target_object_id'):
                row=research_service.object_proposal(card,b,dict(user,name='AI 导师' if coach else user['name'],actor_type='ai' if coach else 'student'),student_messages=student_messages)
                for previous in card.get('quality',{}).get('records',[]):
                    if previous['id'] in row.get('supersedes_proposals',[]):previous.update(status='superseded',superseded_by=row['id'])
                card.setdefault('quality',{}).setdefault('records',[]).append(row)
            elif action == 'quality-decision' and any(r.get('id')==b.get('record_id') and r.get('target_object_id') for r in card.get('quality',{}).get('records',[])):
                row=research_service.decide(c,card,b,user,student_messages=student_messages)
            else:
                row = quality_records.add(card, b, 'AI 导师' if coach else user['name'], student_messages) if action == 'quality' else quality_records.decide(card, b)
        except (quality_records.StaleProposal,research_service.Conflict) as error:
            raise Problem(409, str(error))
        except ValueError as error:
            raise Problem(422, str(error))
        reason = '保存依据与选择：' + row['kind'] if action == 'quality' else '学生决定：' + row['status']
    else:
        raise Problem(404,"没有这项操作。")
    c.execute("INSERT INTO revisions VALUES(?,?,?)",(card["id"],card["version"],before))
    card["version"]+=1
    result=uid("R")
    card["history"].append(dict(version=card["version"],title=card["title"],reason=reason,created=now(),author=user["name"],result_id=result))
    card["result_id"]=result
    card.pop("_student_messages",None)
    research_service.enrich(c,card)
    c.execute("UPDATE projects SET card=? WHERE id=?",(dump({k:v for k,v in card.items() if k not in ("activity","research","materials","learning_profile","learning_support","reading_items","opening_text","teaching_brief","handoff_notes","_student_messages","student_message_ids")}),card["id"]))
    if key:
        c.execute("INSERT INTO requests VALUES(?,?,?,?,?)",(card["id"],user["id"],key,digest,dump(card)))
    return card

class Handler(BaseHTTPRequestHandler):
    server_version="ResearchCoach/1"
    def respond(self, status, data, mime="application/json; charset=utf-8", headers=None):
        if not isinstance(data,bytes):
            data=dump(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","same-origin")
        for key,value in (headers or {}).items():
            self.send_header(key,value)
        self.end_headers()
        self.wfile.write(data)

    def get_user(self,c):
        token=""
        auth=self.headers.get("Authorization","")
        if auth.startswith("Bearer "):
            token=auth[7:]
        else:
            jar=SimpleCookie()
            jar.load(self.headers.get("Cookie",""))
            if jar.get("coach_session"):
                token=jar["coach_session"].value
        self.token_hash=hashlib.sha256(token.encode()).hexdigest()
        row=c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user WHERE s.token=? AND s.expires>?",(self.token_hash,time.time())).fetchone()
        return public_user(row) if row else None

    def body(self):
        try:
            size=int(self.headers.get("Content-Length","0"))
        except ValueError:
            raise Problem(400,"请求长度无效。")
        if not 0<=size<=MAX_FILE*4//3+1048576:
            raise Problem(413,"材料过大，每份上限 12 MiB。")
        if self.headers.get_content_type()!="application/json" and size:
            raise Problem(415,"请以 JSON 提交。")
        try:
            obj=json.loads(self.rfile.read(size)) if size else {}
        except (ValueError,UnicodeError):
            raise Problem(400,"无法读取提交内容。")
        if not isinstance(obj,dict):
            raise Problem(400,"提交内容应为对象。")
        return obj

    def login(self,c,b):
        row=c.execute("SELECT * FROM users WHERE username=?",(clean(b.get("username")),)).fetchone()
        password = b.get("password")
        if not row or not isinstance(password, str) or not hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",password.encode(),row["salt"],240000),row["pw"]):
            raise Problem(401,"账号或密码不正确。")
        token=secrets.token_urlsafe(32)
        c.execute("DELETE FROM sessions WHERE expires<=?",(time.time(),))
        c.execute("INSERT INTO sessions VALUES(?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),row["id"],time.time()+7*86400))
        secure = '; Secure' if (self.server.plugin_origin or '').startswith('https://') else ''
        self.extra_headers={"Set-Cookie":f"coach_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800{secure}"}
        return dict(user=public_user(row),token=token)

    def project_url(self, pid):
        origin = self.server.plugin_origin or f'http://127.0.0.1:{self.server.server_port}'
        return f'{origin}/?project={pid}'

    def api(self,c,path,b,is_post):
        user=self.get_user(c)
        if self.server.plugin_origin and is_post and path.startswith('/api/plugin/'):
            return plugin_site.handle(self, c, path.rsplit('/', 1)[-1], b, user)
        if self.server.plugin_origin:
            valid_lease = plugin_site.validate_lease(c, self.token_hash, is_post and not path.endswith('/plugin-context-file'))
            if path == '/api/plugin-lease' and not is_post:
                if not user or not valid_lease or not self.headers.get('Authorization'):
                    raise Problem(403, '请从已连接的 Codex 聊天使用本机资料。')
                return {'active': True}
        coach_scope=c.execute('SELECT project FROM coach_sessions WHERE token=?', (self.token_hash,)).fetchone()
        if coach_scope:
            base='/api/projects/'+coach_scope['project']
            allowed=path == base or path.startswith(base+'/')
            if not is_post and path.startswith('/api/files/'):
                allowed=bool(c.execute('SELECT 1 FROM files WHERE id=? AND project=?', (path.rsplit('/',1)[-1],coach_scope['project'])).fetchone())
            if not allowed:
                raise Problem(403, '导师凭证只能访问绑定的学生项目。')
        scope=c.execute("SELECT project FROM scoped_sessions WHERE token=?",(self.token_hash,)).fetchone()
        if scope:
            pid=scope["project"]
            base="/api/projects/"+pid
            allowed=(path==base+"/review-draft" or (not is_post and (path in (base,base+"/discussions") or re.fullmatch(re.escape(base)+r"/versions/\d+",path))))
            if not is_post and re.fullmatch(r"/api/files/[A-Za-z0-9_-]+",path):
                allowed=bool(c.execute("SELECT 1 FROM files WHERE id=? AND project=?",(path.rsplit("/",1)[1],pid)).fetchone())
            if not allowed:
                raise Problem(403,"辅助审阅凭证只能读取指定项目和保存审阅草稿。")
        if path=="/api/me" and not is_post:
            demo=c.execute("SELECT 1 FROM settings WHERE key='demo' AND value='1'").fetchone()
            return dict(user=user,demo=bool(demo))
        if path == '/api/plugin-downloads' and not is_post:
            return plugin_site.download_metadata(self.server)
        if path=="/api/login" and is_post:
            return self.login(c,b)
        if not user:
            raise Problem(401,"请先登录。")
        if path == '/api/plugin-connection' and not is_post and self.server.plugin_origin:
            return dict(connected=plugin_site.browser_connected(self,c,user), user=user)
        if not is_post and self.server.plugin_origin:
            launch_status = re.fullmatch(r'/api/plugin-entry-status/([a-f0-9]{32})', path)
            if launch_status:
                return plugin_site.entry_status(self, c, launch_status[1], user)
        if path == '/api/runtime-settings':
            config_path = getattr(self.server, 'runtime_config_path', None)
            if is_post:
                if user['role'] != 'teacher' or self.headers.get('Authorization'):
                    raise Problem(403, '请老师本人登录网站修改系统设置。')
                try:
                    return runtime_config.save_defaults(b, config_path)
                except ValueError as error:
                    raise Problem(409 if '更新' in str(error) else 422, str(error)) from error
            return dict(runtime_config.public_config(config_path), editable=user['role'] == 'teacher')
        if path=="/api/logout" and is_post:
            c.execute("DELETE FROM sessions WHERE token=?",(self.token_hash,))
            self.extra_headers={"Set-Cookie":"coach_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"}
            return dict(user=None)
        if path=="/api/home" and not is_post:
            activities=[dict(r) for r in c.execute("SELECT DISTINCT a.* FROM activities a LEFT JOIN projects p ON p.activity=a.id WHERE a.teacher=? OR p.student=? ORDER BY a.rowid DESC",(user["id"],user["id"]))]
            students=[dict(r) for r in c.execute("SELECT id,name FROM users WHERE role='student' ORDER BY id")] if user["role"]=="teacher" else []
            cards=[]
            for r in c.execute("SELECT p.card FROM projects p JOIN activities a ON a.id=p.activity WHERE p.student=? OR a.teacher=? ORDER BY p.rowid DESC",(user["id"],user["id"])):
                item=json.loads(r[0])
                summary={k:item[k] for k in ("id","activity_id","student_id","student_name","title","current_step","status","version","next_action")}
                summary["review"]={k:v for k,v in (item.get("review") or {}).items() if k in ("decision","deliverable","owner","due","step")}
                summary['tutor_mode']=item.get('tutor_mode','observation')
                summary['workflow_version']=item.get('workflow_version')
                summary['needs_review_count']=sum(1 for obj in (json.loads(r[0]) for r in c.execute('SELECT data FROM research_objects WHERE project_id=?',(item['id'],))) if obj.get('status')=='confirmed' and obj.get('needs_review'))
                summary['last_choice']=next((r.get('decision_reason','') for r in reversed(item.get('quality',{}).get('records',[])) if r.get('kind')=='proposal' and r.get('decisions')), '')
                cards.append(summary)
            return dict(user=user,activities=activities,students=students,projects=cards)
        if path=="/api/activities" and is_post:
            assert_role(user,"teacher")
            required(b,["title","requirements","deadline"])
            valid_date(b["deadline"])
            ids=b.get("student_ids")
            if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids):
                raise Problem(422,"请至少选择一名学生。")
            roster={r["id"]:r for r in c.execute("SELECT id,name FROM users WHERE role='student'")}
            if set(ids)-roster.keys():
                raise Problem(422,"名单中的学生不存在。")
            aid=uid("A")
            c.execute("INSERT INTO activities VALUES(?,?,?,?,?,?)",(aid,user["id"],b["title"],b["requirements"],b["deadline"],1))
            activity_budget(c,aid,b.get("budget",dict(workflow.BUDGET)))
            for sid in dict.fromkeys(ids):
                insert_card(c,aid,roster[sid])
            return dict(id=aid,title=b["title"],version=1)
        match=re.fullmatch(r"/api/activities/([A-Za-z0-9_-]+)",path)
        if match and is_post:
            assert_role(user,"teacher")
            aid=match[1]
            row=c.execute("SELECT * FROM activities WHERE id=? AND teacher=?",(aid,user["id"])).fetchone()
            if not row:
                raise Problem(404,"活动不存在。")
            if row["version"]!=b.get("version"):
                raise Problem(409,"要求已有新版本，请先刷新。")
            required(b,["title","requirements","deadline"])
            valid_date(b["deadline"])
            old_budget=activity_budget(c,aid)
            budget_changed=b.get('budget',old_budget)!=old_budget
            requirements_changed=b['requirements']!=row['requirements']
            deadline_changed=b['deadline']!=row['deadline']
            title_changed=b['title']!=row['title']
            if not (budget_changed or requirements_changed or deadline_changed or title_changed): return dict(row)
            c.execute("INSERT INTO activity_versions VALUES(?,?,?)",(aid,row["version"],dump(dict(row,budget=old_budget))))
            previous_cards=[project_for(c,user,r['id']) for r in c.execute('SELECT id FROM projects WHERE activity=?',(aid,)).fetchall()]
            activity_budget(c,aid,b.get("budget"))
            affected_steps={1,2,3,4,5,6} if requirements_changed else ({4,5,6} if budget_changed or deadline_changed else {5,6})
            c.execute("UPDATE activities SET title=?,requirements=?,deadline=?,version=version+1 WHERE id=?",(b["title"],b["requirements"],b["deadline"],aid))
            for project in previous_cards:
                c.execute('INSERT INTO revisions VALUES(?,?,?)',(project['id'],project['version'],dump(project)))
                for st in project['steps']:
                    if st['number'] in affected_steps:
                        st['cycle']=st.get('cycle',1)+1
                        if st['status'] in ('complete','review'): st['status']='pending'
                    elif st.get('requirement_version')==row['version']:
                        st['requirement_version']=row['version']+1
                project['status']='active'
                for st in project['steps']:
                    if st['status']=='active': st['status']='pending'
                workflow.set_navigation_stage(project,next((st['number'] for st in project['steps'] if st['status']!='complete'),6))
                project['steps'][project['current_step']-1]['status']='active'
                project['next_action']='活动要求已更新，请核对受影响阶段；原成果已保留。'
                project.pop('milestone',None)
                project['version']+=1
                project['history'].append(dict(version=project['version'],title=project['title'],reason='老师更新活动要求，重开相关核对',created=now(),author=user['name']))
                c.execute('UPDATE projects SET card=? WHERE id=?',(dump({k:v for k,v in project.items() if k not in ('activity','research')}),project['id']))
            return dict(c.execute("SELECT * FROM activities WHERE id=?",(aid,)).fetchone())
        match=re.fullmatch(r"/api/projects/([A-Za-z0-9_-]+)(?:/(context|continuity|progress|files|comments|revise|quality|quality-decision|review|review-draft|review-coach|coach|discussions|reflections|sources|search-project-files|read-project-file|workspace|open-folder|pick-folder|reset|plugin-entry|plugin-context-file|research-export|research-objects|research-focus|research-search|research-check|research-deliverable|research-recheck|research-review|research-handoff|versions/\d+))?",path)
        if match:
            pid,action=match.groups()
            pilot = self.server.plugin_origin is not None
            card=self.server.project_archive.enrich(project_for(c,user,pid))
            research_service.enrich(c,card)
            if pilot and action in ('coach', 'review-coach', 'workspace', 'pick-folder', 'open-folder', 'search-project-files', 'read-project-file'):
                raise Problem(409, '请在学生电脑上的 Codex 插件中操作。')
            if action == 'plugin-entry' and pilot and is_post:
                if plugin_site.downloads(self.server) and not plugin_site.browser_connected(self,c,user):
                    raise Problem(409, '请先连接这台电脑。')
                return plugin_site.entry(self, c, card, user, b)
            if action == 'plugin-context-file' and pilot and is_post:
                relative = b.get('path')
                if not isinstance(relative, str) or not relative.startswith(context_archive.PREFIX + '/'):
                    raise Problem(422, '请选择接续索引中的资料。')
                return project_files.read(self.server.project_archive.context_root(card), relative, b.get('offset', 0), b.get('limit', 12000))
            if action in ('plugin-entry', 'plugin-context-file'):
                raise Problem(404, '插件接入未启用。')
            coach_session = c.execute('SELECT * FROM coach_sessions WHERE token=?', (self.token_hash,)).fetchone()
            if coach_session and coach_session['project'] != pid:
                raise Problem(403, '导师会话只能访问绑定项目。')
            if is_post and (action in ('quality-decision','research-recheck','research-review') or (action == 'progress' and (b.get('complete') or b.get('confirmed')))) and (coach_session or self.headers.get('Authorization')):
                raise Problem(403, '请学生在网站决定，导师工具不能代为接受或拒绝。')
            if is_post and coach_session and action not in ('search-project-files', 'read-project-file'):
                if pilot and action in ('sources', 'reflections', 'files'):
                    if b.get('version', b.get('project_version')) != card['version']:
                        raise Problem(409, '项目已有更新，请先读取最新状态再保存。')
                n = coach_session['step']
                if card['status'] != 'active' or card['current_step'] != n or card['steps'][n-1].get('cycle', 1) != coach_session['cycle']:
                    prior=c.execute('SELECT digest FROM requests WHERE project=? AND actor=? AND key=?',(pid,user['id'],clean(b.get('request_id')))).fetchone()
                    if prior and prior['digest']==hashlib.sha256((action+dump(b)).encode()).hexdigest():
                        result=write_card(c,user,card,action,b,coach=True)
                        result['return_url']=self.project_url(pid)
                        complete=bool(b.get('complete') and result.get('milestone',{}).get('version')==result['version'])
                        result['receipt']=dict(saved=True,step=b.get('step'),stage_complete=complete,complete=complete,status=result['status'],current_step=result['current_step'],next_action=result['next_action'],return_url=result['return_url'])
                        return result
                    raise Problem(409, '本会话阶段已结束，请回网站接续。')
                try:
                    quality_records.guard_agent_changes(card, action, b)
                except ValueError as error:
                    raise Problem(409, str(error))
                if action in ('reset', 'coach', 'workspace', 'pick-folder', 'open-folder'):
                    raise Problem(403, '请学生在网站执行此操作。')
            student_messages = None
            if (action in ('quality','quality-decision','progress') or (action or '').startswith('research-')) and is_post:
                archive = self.server.project_archive.read(card, force=True)
                student_messages = {m['id']: m['text'] for conversation in archive['conversations'] for m in conversation['messages'] if m['role'] == 'user'}
            if action in ('search-project-files','read-project-file'):
                if not is_post: raise Problem(405,'请提供检索或读取参数。')
                root=self.server.workspaces.visible(card['student_id'],pid)
                if root is None: raise Problem(409,'请先设置当前项目文件夹。')
                try:
                    if action=='search-project-files':
                        return project_files.search(root,b.get('query',''),b.get('offset',0),b.get('limit',30))
                    return project_files.read(root,b.get('path',''),b.get('offset',0),b.get('limit',12000))
                except (OSError,ValueError,TypeError):
                    raise Problem(422,'无法读取该项目资料，请使用搜索结果中的有效路径及分页参数。')
            if action in ('workspace','open-folder','pick-folder'):
                assert_role(user,'student')
                if self.client_address[0] not in ('127.0.0.1','::1') or self.server.server_address[0] not in ('127.0.0.1','::1'):
                    raise Problem(409,'请在安装了 Codex 的本机工作台设置项目文件夹。')
                try:
                    if action=='pick-folder':
                        if not is_post: raise Problem(405,'请点击选择文件夹。')
                        c.commit()
                        return {'path':self.server.workspaces.pick(user['id'])}
                    if action=='open-folder':
                        if not is_post: raise Problem(405,'请点击打开项目文件夹。')
                        c.commit()
                        self.server.workspaces.open(card)
                        return {'opened':True}
                    if is_post:
                        self.server.workspaces.select(card,b.get('parent'))
                        self.server.project_archive.mirror_files(c,card)
                        self.server.project_archive.export(card)
                    return self.server.workspaces.describe(card)
                except ValueError as error:
                    raise Problem(422,str(error))
                except OSError:
                    raise Problem(422,'无法写入这个文件夹，请选择有写入权限且可用的本机位置。')
            self.server.project_archive.mirror_files(c,card)
            if action == 'research-export' and not is_post:
                self.mime='application/zip'
                self.extra_headers={'Content-Disposition':'attachment; filename="research-records.zip"'}
                self.server.project_archive.export(card)
                return research_export.bundle(card,self.server.workspaces.visible(card['student_id'],pid) if self.server.workspaces else None,
                    c.execute('SELECT name,content FROM files WHERE project=?',(pid,)).fetchall())
            if action == "reset" and is_post:
                assert_role(user,"student")
                if b.get("confirmed") is not True:
                    raise Problem(422,"请确认清除本项目档案并重新开始。")
                if b.get("version") != card["version"]:
                    raise Problem(409,"项目有新记录，请刷新后再确认清除。")
                # Keep a recovery snapshot outside active projects. A new ID isolates
                # old Codex bindings, archive workers, browser drafts and late writes.
                snapshot={"card":card,"revisions":[dict(r) for r in c.execute("SELECT * FROM revisions WHERE project=?",(pid,))],
                    "files":[dict(id=r["id"],name=r["name"],content_base64=base64.b64encode(r["content"]).decode()) for r in c.execute("SELECT * FROM files WHERE project=?",(pid,))]}
                c.execute("INSERT INTO project_resets VALUES(?,?,?,?)",(pid,user["id"],now(),dump(snapshot)))
                for table in ("files","revisions","requests"):
                    c.execute(f"DELETE FROM {table} WHERE project=?",(pid,))
                for table in ('research_objects','object_revisions','research_links','research_events','research_reference_snapshots','deliverable_versions'):
                    c.execute(f"DELETE FROM {table} WHERE project_id=?",(pid,))
                c.execute("DELETE FROM projects WHERE id=?",(pid,))
                fresh=make_card(uid("P"),card["activity_id"],user["id"],user["name"])
                c.execute("INSERT INTO projects VALUES(?,?,?,?)",(fresh["id"],fresh["activity_id"],user["id"],dump(fresh)))
                return project_for(c,user,fresh["id"])
            if action in ('sources','reflections') and is_post:
                assert_role(user,'student')
                if self.server.workspaces and not self.server.workspaces.get(card['student_id'],pid):
                    raise Problem(409,'请先在网站选择项目存储位置，再保存讨论材料。')
            if action == "sources" and is_post:
                assert_role(user,"student")
                try:
                    result=self.server.project_archive.source(card,b)
                    self.server.project_archive.export(card)
                    return result
                except ValueError as error:
                    raise Problem(422,str(error))
            if action == 'context' and not is_post:
                known_hash = parse_qs(urlsplit(self.path).query).get('known_hash', [''])[0]
                return self.server.project_archive.context(card, known_hash=known_hash)
            if action == 'continuity' and is_post:
                assert_role(user, 'student')
                try:
                    return self.server.project_archive.save_continuity(card, b)
                except ValueError as error:
                    raise Problem(422, str(error))
            if action == "discussions" and not is_post:
                return self.server.project_archive.read(card)
            if action == "reflections" and is_post:
                assert_role(user,"student")
                try:
                    result=self.server.project_archive.reflect(card,b)
                    self.server.project_archive.export(card)
                    return result
                except ValueError as error:
                    raise Problem(422,str(error))
            if action == "review-draft":
                result=review_draft(c,user,card,b if is_post else None)
                if is_post:
                    result.update(saved=True,return_url=self.project_url(pid))
                return result
            if action == "review-coach":
                assert_role(user,"teacher")
                if self.client_address[0] not in ("127.0.0.1","::1") or self.server.server_address[0] not in ("127.0.0.1","::1"):
                    raise Problem(409,"请在安装了 Codex 的本机工作台开始辅助审阅。")
                if not is_post:
                    return self.server.review_launcher.read(user["id"],pid,card)
                if card["status"]!="review":
                    raise Problem(409,"请等待学生提交当前版本的开题卡。")
                token=secrets.token_urlsafe(32)
                token_hash=hashlib.sha256(token.encode()).hexdigest()
                c.execute("INSERT INTO sessions VALUES(?,?,?)",(token_hash,user["id"],time.time()+7*86400))
                c.execute("INSERT INTO scoped_sessions VALUES(?,?)",(token_hash,pid))
                c.commit()
                try:
                    return self.server.review_launcher.start(user,self.server.project_archive.enrich(card),f"http://127.0.0.1:{self.server.server_port}",token,background=b.get("background") is True,only_if_active=b.get("only_if_active") is True)
                except (ValueError,OSError) as error:
                    c.execute("DELETE FROM sessions WHERE token=?",(token_hash,))
                    c.commit()
                    raise Problem(503,str(error))
            if action == "coach":
                assert_role(user,"student")
                if self.client_address[0] not in ("127.0.0.1", "::1") or self.server.server_address[0] not in ("127.0.0.1", "::1"):
                    raise Problem(409,"请在安装了 Codex 的电脑上打开本地开题工作台，再开始讨论。")
                if not is_post:
                    return self.server.coach_launcher.read(user["id"],pid,card)
                if card["status"]!="active":
                    raise Problem(409,"本轮已提交，请先回网站查看老师反馈。")
                if not self.server.workspaces.get(user['id'],pid):
                    raise Problem(409,'请先为这个项目选择存储文件夹。')
                self.server.project_archive.export(card)
                token=secrets.token_urlsafe(32)
                c.execute("INSERT INTO sessions VALUES(?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),user["id"],time.time()+7*86400))
                c.execute('INSERT INTO coach_sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),pid,card['current_step'],card['steps'][card['current_step']-1].get('cycle',1)))
                c.commit()
                try:
                    launch_card = self.server.project_archive.enrich(card)
                    launch_card['_launch_context'] = self.server.project_archive.context(card)
                    return self.server.coach_launcher.start(user,launch_card,f"http://127.0.0.1:{self.server.server_port}",token,background=b.get("background") is True,only_if_active=b.get("only_if_active") is True,opening_answer=clean(b.get("opening_answer"))[:4000] if b.get("opening_answer") else None)
                except (ValueError,OSError) as error:
                    raise Problem(503,str(error))
            if not is_post and action is None:
                card = self.server.project_archive.enrich(card)
                if pilot:
                    downloads = plugin_site.downloads(self.server)
                    card['plugin_pilot'] = {'download': next(iter(downloads.values()), None), 'downloads': downloads,
                                            'connected': plugin_site.browser_connected(self,c,user)}
                return card
            if not is_post and action and action.startswith("versions/"):
                version=int(action.split("/")[-1])
                if version==card["version"]:
                    return card
                snapshot=c.execute("SELECT card FROM revisions WHERE project=? AND version=?",(pid,version)).fetchone()
                if snapshot:
                    return json.loads(snapshot[0])
                raise Problem(404,"找不到这个项目版本。")
            if is_post and action:
                result=write_card(c,user,card,action,b,student_messages,bool(coach_session))
                result["return_url"]=self.project_url(pid)
                result["receipt"]={"saved":True,"step":b.get("step"),"stage_complete":bool(b.get("complete") and result.get("milestone",{}).get("version")==result["version"]),
                    "complete":bool(b.get("complete") and result.get("milestone",{}).get("version")==result["version"]),
                    "status":result["status"],"current_step":result["current_step"],"next_action":result["next_action"],"return_url":result["return_url"]}
                current=project_for(c,user,pid)
                self.server.project_archive.mirror_files(c,current)
                self.server.project_archive.export(current)
                return result
        match=re.fullmatch(r"/api/files/([A-Za-z0-9_-]+)",path)
        if match and not is_post:
            row=c.execute("SELECT project,name FROM files WHERE id=?",(match[1],)).fetchone()
            if not row:
                raise Problem(404,"材料不存在。")
            project_for(c,user,row["project"])
            self.extra_headers={"Content-Disposition":"attachment; filename*=UTF-8''"+quote(row["name"],safe="")}
            self.mime="application/octet-stream"
            return c.execute("SELECT content FROM files WHERE id=?",(match[1],)).fetchone()[0]
        raise Problem(404,"找不到请求的内容。")

    def dispatch(self,is_post):
        try:
            path=urlsplit(self.path).path
            self.mime="application/json; charset=utf-8"
            self.extra_headers={}
            if is_post and self.headers.get("Origin"):
                if urlsplit(self.headers["Origin"]).netloc!=self.headers.get("Host"):
                    raise Problem(403,"请从本教学网站操作。")
            if path in (plugin_site.DOWNLOAD, plugin_site.MAC_DOWNLOAD) and not is_post:
                macos = path == plugin_site.MAC_DOWNLOAD
                package = self.server.plugin_macos_package if macos else self.server.plugin_package
                if not package:
                    raise Problem(404, '这个系统的安装包尚未发布。')
                filename = 'research-coach-macos.zip' if macos else 'research-coach-windows.zip'
                self.respond(200, package.read_bytes(), 'application/zip', {
                    'Content-Disposition': f'attachment; filename="{filename}"'})
            elif path in (skill_distribution.DOWNLOAD, '/downloads/research-proposal-review.zip') and not is_post:
                self.respond(200,skill_distribution.bundle(name=skill_distribution.REVIEW_NAME if path.endswith("research-proposal-review.zip") else skill_distribution.NAME),"application/zip",{
                    "Content-Disposition":'attachment; filename="'+path.rsplit('/',1)[-1]+'"',
                    "Cache-Control":"no-cache"})
            elif path.startswith("/api/"):
                body=self.body() if is_post else {}
                with closing(connect(self.server.db_path)) as c, c:
                    c.execute("BEGIN IMMEDIATE" if is_post else "BEGIN")
                    result=self.api(c,path,body,is_post)
                self.respond(200,result,self.mime,self.extra_headers)
            elif not is_post:
                root=(ROOT/"static").resolve()
                target=(root/(path.lstrip("/") or "index.html")).resolve()
                if root not in target.parents or not target.is_file():
                    raise Problem(404,"页面不存在。")
                mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self.respond(200,target.read_bytes(),mime+("; charset=utf-8" if mime.startswith("text/") or mime=="application/javascript" else ""))
            else:
                raise Problem(404,"操作不存在。")
        except (Problem, plugin_site.PilotError) as exc:
            payload={"error":str(exc)}
            if getattr(exc, 'code', None):
                payload["code"]=exc.code
            if getattr(exc, 'missing', None):
                payload["missing"]=exc.missing
            self.respond(exc.status,payload)
        except PermissionError as exc:
            self.respond(403,{'error':str(exc)})
        except research_service.Conflict as exc:
            self.respond(409,{'error':str(exc)})
        except ValueError as exc:
            self.respond(422,{'error':str(exc)})
        except sqlite3.OperationalError as exc:
            self.log_error("Database unavailable: %s",exc)
            self.respond(503,{"error":"教学服务暂时繁忙，请用同一次提交重试。"})
        except (ConnectionResetError,BrokenPipeError):
            pass

    def do_GET(self):
        self.dispatch(False)
    def do_POST(self):
        self.dispatch(True)

def serve(path,port,host="127.0.0.1",demo=True,*,plugin_origin=None,plugin_package=None,plugin_macos_package=None):
    remote = host not in ("127.0.0.1","localhost")
    plugin_origin = plugin_site.canonical_origin(plugin_origin) if plugin_origin else None
    if any(package and (not plugin_origin or not Path(package).is_file())
           for package in (plugin_package, plugin_macos_package)):
        raise ValueError('请为插件模式提供可用的 Windows 安装包。')
    if remote and demo:
        raise ValueError("校内共享请使用 --no-demo 和独立教学数据库。")
    init_db(path,demo)
    if remote:
        with closing(connect(path)) as conn:
            if conn.execute("SELECT 1 FROM settings WHERE key='demo' AND value='1'").fetchone() or conn.execute("SELECT 1 FROM users WHERE username IN ('student','student2','teacher') AND id IN ('U1','U2','U3')").fetchone():
                raise ValueError("请使用没有演示账号的独立教学数据库。")
    server=ThreadingHTTPServer((host,port),Handler)
    server.db_path=path
    server.plugin_origin = plugin_origin
    server.plugin_package = Path(plugin_package).resolve() if plugin_package else None
    server.plugin_macos_package = Path(plugin_macos_package).resolve() if plugin_macos_package else None
    if plugin_origin:
        with closing(connect(path)) as connection, connection:
            plugin_site.init_schema(connection)

        def uploaded(project):
            with closing(connect(path)) as connection:
                return plugin_site.discussions(connection, project)

        server.workspaces = server.coach_launcher = server.review_launcher = None
        server.project_archive = ProjectArchive(Path(path).resolve().with_suffix('.plugin-data'), uploaded=uploaded, site_origin=plugin_origin)
        return server
    server.workspaces=WorkspaceStore(Path(path).resolve().with_suffix('.workspaces.json'))
    server.coach_launcher=CoachLauncher(Path(path).resolve().with_suffix(".coaching"),workspaces=server.workspaces)
    server.review_launcher=ReviewLauncher(Path(path).resolve().with_suffix(".reviews"))
    server.project_archive=ProjectArchive(server.coach_launcher.folder,workspaces=server.workspaces)
    # Enrol previously issued project bindings without changing student files.
    with closing(connect(path)) as conn, conn:
        for record in conn.execute('SELECT student,card FROM projects').fetchall():
            card=json.loads(record['card'])
            roots=[server.workspaces.internal(record['student'],card['id']), server.coach_launcher.folder/record['student']/card['id']]
            for root in roots:
                for binding in [root/'binding'/'connection.json', *root.glob('stages/*/binding/connection.json')]:
                    if not binding.is_file(): continue
                    try:
                        connection=json.loads(binding.read_text('utf-8'))
                        digest=hashlib.sha256(connection['token'].encode()).hexdigest()
                        session=conn.execute('SELECT user FROM sessions WHERE token=?', (digest,)).fetchone()
                        if not session or session['user'] != record['student']: continue
                        stage,cycle=0,0  # Unknown old bindings stay read-only until website reconnects.
                        if binding.parent.parent.parent.name == 'stages':
                            stage,cycle=map(int,binding.parent.parent.name.split('-'))
                        elif (root/'active-stage.txt').is_file():
                            active=(root/'active-stage.txt').read_text('utf-8').strip()
                            if re.fullmatch(r'[1-6]-[1-9][0-9]*',active):
                                stage,cycle=map(int,active.split('-'))
                        if 0 <= stage <= 6:
                            conn.execute('INSERT OR IGNORE INTO coach_sessions VALUES(?,?,?,?)',(digest,card['id'],stage,cycle))
                    except (OSError,ValueError,KeyError,TypeError):
                        continue
    server.archive_worker=None
    server.archive_due=0
    def archive_tick():
        if time.monotonic()<server.archive_due or (server.archive_worker and server.archive_worker.is_alive()):
            return
        server.archive_due=time.monotonic()+20
        def sync_registered():
            try:
                with closing(connect(path)) as conn:
                    rows=conn.execute("SELECT student,card FROM projects").fetchall()
                    for row in rows:
                        raw=json.loads(row["card"])
                        if not server.project_archive.folder(raw).exists():
                            continue
                        card=project_for(conn,{"id":row["student"]},raw["id"])
                        server.project_archive.mirror_files(conn,card)
                        server.project_archive.read(card)
                        server.project_archive.export(card)
            except (OSError,ValueError,sqlite3.Error):
                # Per-project read exposes sync failure; next tick retries without blocking HTTP.
                pass
        server.archive_worker=Thread(target=sync_registered,daemon=True)
        server.archive_worker.start()
    server.service_actions=archive_tick
    return server

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="科研开题工作台 · 本地教学演示")
    parser.add_argument("--db",default=os.getenv("COACH_DB",str(ROOT/"local_data"/"tanyue.sqlite3")))
    parser.add_argument("--port",type=int,default=8767)
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--no-demo",action="store_true",help="不创建演示账号，供独立教学数据库使用")
    parser.add_argument('--plugin-origin', default=os.getenv('COACH_PLUGIN_ORIGIN'), help='开题手记的完整公开地址，启用插件试教模式')
    parser.add_argument('--plugin-package', default=os.getenv('COACH_PLUGIN_PACKAGE'), help='发布的 Windows 插件 ZIP 路径')
    parser.add_argument('--plugin-macos-package', default=os.getenv('COACH_PLUGIN_MACOS_PACKAGE'), help='发布的 macOS 插件 ZIP 路径')
    args=parser.parse_args()
    with serve(args.db,args.port,args.host,not args.no_demo,plugin_origin=args.plugin_origin,plugin_package=args.plugin_package,
               plugin_macos_package=args.plugin_macos_package) as server:
        print(f"科研开题工作台  http://{args.host}:{server.server_port}",flush=True)
        server.serve_forever()
