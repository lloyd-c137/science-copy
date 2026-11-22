"""Cloud-side account, stage binding and transcript receipts for the Windows plugin."""

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlsplit
from uuid import UUID
from zipfile import BadZipFile, ZipFile


SKILL = '$research-coach:research-proposal-coach'
MARKER = '开题手记会话：'
DOWNLOAD = '/downloads/proposal-coach-windows.zip'
MAC_DOWNLOAD = '/downloads/research-coach-macos.zip'


def download_packages(service):
    return (
        ('windows', DOWNLOAD, service.plugin_package),
        ('macos', MAC_DOWNLOAD, service.plugin_macos_package))


def downloads(service):
    return {target: route for target, route, package in download_packages(service) if package}


def download_metadata(service):
    result = {'versions': {}}
    for target, route, package in download_packages(service):
        if not package or not package.is_file():
            continue
        result[target] = route
        try:
            with ZipFile(package) as archive:
                manifest = next(name for name in archive.namelist()
                                if name.endswith('/plugins/research-coach/.codex-plugin/plugin.json'))
                version = json.loads(archive.read(manifest)).get('version')
        except (OSError, BadZipFile, ValueError, AttributeError, StopIteration):
            continue
        if isinstance(version, str) and version.strip():
            result['versions'][target] = version.strip()
    return result


class PilotError(Exception):
    def __init__(self, status, message, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def canonical_origin(value):
    url = urlsplit(value)
    local = url.hostname in ('127.0.0.1', 'localhost', '::1')
    if (not url.netloc or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment
            or url.scheme != 'https' and not (url.scheme == 'http' and local)):
        raise ValueError('插件网站需使用 HTTPS 地址，本机开发可用 HTTP 回环地址。')
    return value.rstrip('/')


def init_schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS plugin_pairing (
        code TEXT PRIMARY KEY, challenge TEXT NOT NULL, user TEXT REFERENCES users(id), expires REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS plugin_devices (
        token TEXT PRIMARY KEY, user TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS plugin_local_pairing (
        code TEXT PRIMARY KEY REFERENCES plugin_pairing(code) ON DELETE CASCADE,
        pin TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, browser TEXT);
      CREATE TABLE IF NOT EXISTS plugin_browser_connections (
        browser TEXT PRIMARY KEY, device TEXT NOT NULL REFERENCES plugin_devices(token) ON DELETE CASCADE,
        saved INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS plugin_workspace_claims (
        device TEXT NOT NULL REFERENCES plugin_devices(token) ON DELETE CASCADE,
        workspace_hash TEXT NOT NULL, project TEXT NOT NULL,
        PRIMARY KEY(device, workspace_hash, project));
      CREATE TABLE IF NOT EXISTS plugin_entries (
        key TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        step INTEGER NOT NULL, cycle INTEGER NOT NULL, thread TEXT UNIQUE, created REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS plugin_entry_meta (
        entry TEXT PRIMARY KEY REFERENCES plugin_entries(key) ON DELETE CASCADE,
        owner TEXT NOT NULL, role TEXT NOT NULL, workspace_hash TEXT NOT NULL,
        scope TEXT NOT NULL, predecessor TEXT, current INTEGER NOT NULL DEFAULT 1);
      CREATE TABLE IF NOT EXISTS plugin_restores (
        entry TEXT PRIMARY KEY REFERENCES plugin_entries(key) ON DELETE CASCADE,
        token TEXT NOT NULL, thread TEXT NOT NULL, card_hash TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS plugin_leases (
        token TEXT PRIMARY KEY REFERENCES sessions(token) ON DELETE CASCADE,
        entry TEXT NOT NULL REFERENCES plugin_entries(key) ON DELETE CASCADE);
      CREATE TABLE IF NOT EXISTS plugin_lease_devices (
        token TEXT PRIMARY KEY REFERENCES plugin_leases(token) ON DELETE CASCADE,
        device TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS plugin_turns (
        turn TEXT PRIMARY KEY, entry TEXT NOT NULL REFERENCES plugin_entries(key) ON DELETE CASCADE,
        complete INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS plugin_messages (
        id TEXT PRIMARY KEY, turn TEXT NOT NULL REFERENCES plugin_turns(turn) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, stamp TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS plugin_entries_project ON plugin_entries(project,step,cycle);
      CREATE INDEX IF NOT EXISTS plugin_turns_entry ON plugin_turns(entry);
      CREATE INDEX IF NOT EXISTS plugin_messages_turn ON plugin_messages(turn,ordinal);
    ''')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def browser_student(handler, user):
    if not user or user['role'] != 'student' or handler.headers.get('Authorization'):
        raise PilotError(403, '请学生本人登录教学网站完成这一步。')


def fixed_submission(card):
    return json.dumps(card.get('submitted_deliverable') or card.get('submitted_deliverable_id')
                      or {'version': card.get('version')}, sort_keys=True, ensure_ascii=False)


def check_workspace(db, device, workspace_hash, project):
    if device and db.execute('''SELECT 1 FROM plugin_workspace_claims
        WHERE device=? AND workspace_hash=? AND project<>? LIMIT 1''',
        (device, workspace_hash, project)).fetchone():
        raise PilotError(409, '这个文件夹已用于另一个课题。请选择其他文件夹，或新建一个。',
                         'workspace_in_use')


def save_workspace_claims(db, device, claims):
    if not isinstance(claims, list):
        raise PilotError(422, '目录占用记录格式无效。')
    values = []
    for claim in claims:
        path_hash = claim.get('workspace_hash') if isinstance(claim, dict) else None
        project = claim.get('project') if isinstance(claim, dict) else None
        if (not isinstance(path_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', path_hash)
                or not isinstance(project, str) or not re.fullmatch(r'[A-Za-z0-9_-]{0,100}', project)):
            raise PilotError(422, '目录占用记录格式无效。')
        values.append((device, path_hash, project))
    db.executemany('INSERT OR IGNORE INTO plugin_workspace_claims VALUES (?,?,?)', values)


def entry(handler, db, card, user, body=None):
    body = body or {}
    if not user or user['role'] not in ('student', 'teacher') or handler.headers.get('Authorization'):
        raise PilotError(403, '请本人登录教学网站打开讨论。')
    role = user['role']
    if card['status'] != ('active' if role == 'student' else 'review'):
        raise PilotError(409, '请回网页查看当前课题状态。')
    workspace_hash = body.get('workspace_hash', '')
    if not isinstance(workspace_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', workspace_hash):
        raise PilotError(422, '请先确认完整的本机课题文件夹路径。')
    device = browser_device(handler, db, user)
    check_workspace(db, device, workspace_hash, card['id'])
    if body.get('reuse') is True and not db.execute('''SELECT 1 FROM plugin_workspace_claims
        WHERE device=? AND workspace_hash=? AND project=?''', (device, workspace_hash, card['id'])).fetchone():
        raise PilotError(409, '请在这台电脑上重新选择文件夹。', 'workspace_reselection_required')
    step = card['current_step'] if role == 'student' else 0
    cycle = card['steps'][step - 1].get('cycle', 1) if step else 1
    scope = f'{step}:{cycle}' if step else fixed_submission(card)
    recovery = body.get('recovery') is True
    saved = db.execute("""SELECT e.*,m.workspace_hash,m.predecessor FROM plugin_entries e
        JOIN plugin_entry_meta m ON e.key=m.entry WHERE e.project=? AND m.owner=? AND m.role=?
        AND m.scope=? AND m.current=1 AND m.predecessor IS NULL ORDER BY e.created DESC LIMIT 1""",
        (card['id'], user['id'], role, scope)).fetchone()
    # A replacement is current even though its predecessor is retained for history.
    bound = db.execute("""SELECT e.*,m.workspace_hash FROM plugin_entries e JOIN plugin_entry_meta m ON e.key=m.entry
        WHERE e.project=? AND m.owner=? AND m.role=? AND m.scope=? AND m.current=1 AND e.thread IS NOT NULL
        ORDER BY e.created DESC LIMIT 1""", (card['id'],user['id'],role,scope)).fetchone()
    if bound:
        saved = bound
    if recovery:
        if not bound:
            # Retrying an unbound initial entry is not a recovery that can bypass binding.
            recovery = False
        else:
            saved = db.execute("""SELECT e.*,m.workspace_hash FROM plugin_entries e JOIN plugin_entry_meta m ON e.key=m.entry
                WHERE m.predecessor=? AND m.current=1 AND e.thread IS NULL ORDER BY e.created LIMIT 1""", (bound['key'],)).fetchone()
    if saved and saved['workspace_hash'] != workspace_hash:
        if saved['thread']:
            raise PilotError(409, '路径已改变，请使用“恢复本机讨论”核验新目录。')
        db.execute('UPDATE plugin_entry_meta SET workspace_hash=? WHERE entry=?', (workspace_hash,saved['key']))
    if not saved:
        key = secrets.token_hex(16)
        db.execute('INSERT INTO plugin_entries VALUES (?,?,?,?,NULL,?)',(key,card['id'],step,cycle,time.time()))
        db.execute('INSERT INTO plugin_entry_meta VALUES (?,?,?,?,?,?,1)',
                   (key,user['id'],role,workspace_hash,scope,bound['key'] if recovery else None))
        thread = None
    else:
        key, thread = saved['key'], saved['thread']
    skill = SKILL if role == 'student' else '$research-coach:research-proposal-review'
    if role == 'teacher':
        task = '请帮我审阅学生这次提交的开题稿，整理供我核对的建议。'
    elif recovery:
        task = '请帮我恢复之前的开题讨论，从已保存的成果接着聊。'
    elif card['steps'][step - 1].get('cycle', 1) > 1 and (card.get('review') or {}).get('decision') == 'supplement':
        task = '请和我一起核对老师要求补充的证据。'
    elif step == 1 and card['version'] == 1:
        task = '请带我开始探索研究问题。'
    else:
        task = '请和我继续讨论当前的开题任务。'
    prompt = f'{skill}\n{MARKER}{key}\n{task}'
    return dict(stage_session=key,prompt=prompt,thread_id=thread,watch_open=thread is None,step=step,cycle=cycle,
                role=role,version=card['version'],workspace_hash=workspace_hash,recovery=recovery)


def entry_status(handler, db, key, user):
    if handler.headers.get('Authorization'):
        raise PilotError(403, '请在教学网站查看打开状态。')
    row = db.execute('''SELECT e.thread FROM plugin_entries e JOIN plugin_entry_meta m ON m.entry=e.key
        WHERE e.key=? AND m.owner=? AND m.role=? AND m.current=1''', (key, user['id'], user['role'])).fetchone()
    if not row:
        raise PilotError(404, '找不到本次打开记录。')
    return {'bound': row['thread'] is not None}


def pairing(handler, db, action, body, user):
    now = time.time()
    if action == 'device-request':
        challenge = body.get('challenge', '')
        if not isinstance(challenge, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', challenge):
            raise PilotError(400, '连接请求无效。')
        key = secrets.token_urlsafe(24)
        db.execute('DELETE FROM plugin_pairing WHERE expires<=?', (now,))
        db.execute('DELETE FROM plugin_devices WHERE expires<=?', (now,))
        local = body.get('local') is True
        db.execute('INSERT INTO plugin_pairing VALUES (?,?,NULL,?)', (digest(key), challenge, now + (86400 if local else 600)))
        if local:
            pin = f'{secrets.randbelow(1000):03d}'
            db.execute('INSERT INTO plugin_local_pairing(code,pin) VALUES (?,?)', (digest(key), pin))
            return {'device_code': key, 'pin': pin}
        return {'device_code': key, 'verify_url': f'{handler.server.plugin_origin}/plugin-connect.html?device={key}'}
    key = body.get('device_code', '')
    row = db.execute('SELECT * FROM plugin_pairing WHERE code=? AND expires>?', (digest(key), now)).fetchone() if isinstance(key, str) else None
    if not row:
        raise PilotError(400, '连接已过期，请重新打开安装程序或运行连接。')
    local = db.execute('SELECT * FROM plugin_local_pairing WHERE code=?', (row['code'],)).fetchone()
    if action == 'authorize':
        if not user or user['role'] not in ('student', 'teacher') or handler.headers.get('Authorization'):
            raise PilotError(403, '请本人登录教学网站连接插件。')
        if row['user'] and row['user'] != user['id']:
            raise PilotError(409, '这次连接已由其他账号批准。')
        if local:
            if body.get('account') != user['id']:
                raise PilotError(409, '教学账号已切换，请刷新页面后重新确认。')
            browser = browser_connection_cookie(handler)
            if row['user'] and (not browser or digest(browser) != local['browser']):
                raise PilotError(409, '这次连接已经确认。请在原页面等待安装完成。')
            if local['attempts'] >= 5:
                raise PilotError(429, '连接码尝试次数已用完，请重新运行连接。')
            pin = body.get('pin')
            if not isinstance(pin, str) or not re.fullmatch(r'[0-9]{3}', pin) or not hmac.compare_digest(pin, local['pin']):
                db.execute('UPDATE plugin_local_pairing SET attempts=attempts+1 WHERE code=?', (row['code'],))
                return {'authorized': False, 'error': '连接码不正确，请核对安装窗口。'}
            if not row['user']:
                browser = secrets.token_urlsafe(32)
                db.execute('UPDATE plugin_local_pairing SET browser=? WHERE code=?', (digest(browser), row['code']))
                secure = '; Secure' if handler.server.plugin_origin.startswith('https:') else ''
                handler.extra_headers = {'Set-Cookie': f'{connection_cookie_name(handler)}={browser}; HttpOnly; SameSite=Strict; Path=/; Max-Age=7776000{secure}'}
        db.execute('UPDATE plugin_pairing SET user=? WHERE code=?', (user['id'], row['code']))
        return {'authorized': True}
    verifier = body.get('verifier', '')
    if not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', verifier):
        raise PilotError(400, '连接校验失败。')
    proof = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    if not hmac.compare_digest(proof, row['challenge']):
        raise PilotError(400, '连接校验失败。')
    if row['user'] is None:
        return {'pending': True}
    token = secrets.token_urlsafe(32)
    db.execute('INSERT INTO plugin_devices VALUES (?,?,?)', (digest(token), row['user'], now + 90 * 86400))
    if local:
        db.execute('INSERT INTO plugin_browser_connections(browser,device) VALUES (?,?)', (local['browser'], digest(token)))
    db.execute('DELETE FROM plugin_pairing WHERE code=?', (row['code'],))
    return {'token': token, 'account': row['user']}


def browser_connection_cookie(handler):
    from http.cookies import SimpleCookie
    cookies = SimpleCookie(handler.headers.get('Cookie', ''))
    name = connection_cookie_name(handler)
    return cookies[name].value if name in cookies else ''


def connection_cookie_name(handler):
    origin = getattr(handler.server, 'plugin_origin', '')
    return 'coach_device_' + digest(origin or '')[:12]


def browser_device(handler, db, user):
    browser = browser_connection_cookie(handler)
    if not browser or not user:
        return None
    row = db.execute('''SELECT b.device FROM plugin_browser_connections b JOIN plugin_devices d ON b.device=d.token
        WHERE b.browser=? AND d.user=? AND d.expires>? AND b.saved=1''', (digest(browser), user['id'], time.time())).fetchone()
    return row['device'] if row else None


def browser_connected(handler, db, user):
    return browser_device(handler, db, user) is not None


def parse_uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise PilotError(422, 'Codex 聊天或轮次编号无效。') from None


def authorize_binding(handler, db, body, bind):
    header = handler.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        raise PilotError(401, '请先连接教学账号。')
    device = db.execute('SELECT user FROM plugin_devices WHERE token=? AND expires>?',
                        (digest(header[7:]), time.time())).fetchone()
    if not device:
        raise PilotError(401, '设备连接已失效，请重新连接教学账号。')
    key = body.get('stage_session')
    thread = parse_uuid(body.get('thread'))
    row = db.execute("""SELECT e.*,p.student,p.card,m.owner,m.role,m.workspace_hash,m.scope,m.predecessor,m.current
        FROM plugin_entries e JOIN projects p ON p.id=e.project JOIN plugin_entry_meta m ON m.entry=e.key
        JOIN activities a ON a.id=p.activity WHERE e.key=? AND m.owner=?
        AND ((m.role='student' AND p.student=m.owner) OR (m.role='teacher' AND a.teacher=m.owner))""",
        (key,device['user'])).fetchone() if isinstance(key,str) else None
    if not row:
        raise PilotError(403, '这个聊天入口不属于当前连接的教学账号。')
    if row['thread'] not in (None,thread) or (row['thread'] is None and not bind):
        raise PilotError(409, '这个入口已绑定其他聊天，请在网页使用恢复本机讨论。')
    if bind and (not isinstance(body.get('workspace_hash'),str) or
                 not hmac.compare_digest(row['workspace_hash'],body['workspace_hash'])):
        raise PilotError(409, '实际工作目录与网页确认的目录不符，请回网页改填或恢复本机讨论。')
    return row,thread


def active_entry(row, card):
    stage = row['step']
    if row['role'] == 'student':
        return (card['status'] == 'active' and card['current_step'] == stage and
                card['steps'][stage-1].get('cycle', 1) == row['cycle'])
    return card['status'] == 'review' and fixed_submission(card) == row['scope']


def bind_session(db,row,thread,restore_token=None,device_token=None):
    card=json.loads(row['card'])
    stage=row['step']
    if not row['current'] or not active_entry(row,card):
        raise PilotError(409,'本次讨论已结束或被恢复替代，请回网页继续。')
    device = digest(device_token) if device_token else None
    check_workspace(db, device, row['workspace_hash'], row['project'])
    used=db.execute('SELECT key FROM plugin_entries WHERE thread=? AND key<>?',(thread,row['key'])).fetchone()
    if used:
        raise PilotError(409,'该聊天已用于另一入口，请从网页开启新聊天。')
    if row['predecessor'] and row['thread'] is None:
        proof=db.execute('SELECT * FROM plugin_restores WHERE entry=?',(row['key'],)).fetchone()
        if not proof or proof['thread']!=thread or proof['card_hash']!=digest(row['card']) or not isinstance(restore_token,str) or not hmac.compare_digest(proof['token'],digest(restore_token)):
            raise PilotError(409,'请先重新读取恢复接续资料，再确认替代聊天。')
        previous=db.execute('SELECT current FROM plugin_entry_meta WHERE entry=?',(row['predecessor'],)).fetchone()
        if not previous or not previous['current']:
            raise PilotError(409,'该恢复请求已过期，请回网页重新恢复。')
        db.execute('UPDATE plugin_entry_meta SET current=0 WHERE entry=?',(row['predecessor'],))
    changed=db.execute('UPDATE plugin_entries SET thread=? WHERE key=? AND (thread IS NULL OR thread=?)',
                       (thread,row['key'],thread)).rowcount
    if changed!=1:
        raise PilotError(409,'入口已绑定其他聊天。')
    token=secrets.token_urlsafe(32)
    hashed=digest(token)
    db.execute('INSERT INTO sessions VALUES (?,?,?)',(hashed,row['owner'],time.time()+8*3600))
    if row['role']=='student':
        db.execute('INSERT INTO coach_sessions VALUES (?,?,?,?)',(hashed,row['project'],stage,row['cycle']))
    else:
        db.execute('INSERT INTO scoped_sessions VALUES (?,?)',(hashed,row['project']))
    db.execute('INSERT INTO plugin_leases VALUES (?,?)',(hashed,row['key']))
    if device:
        db.execute('INSERT INTO plugin_lease_devices VALUES (?,?)', (hashed, device))
        db.execute('INSERT OR IGNORE INTO plugin_workspace_claims VALUES (?,?,?)',
                   (device, row['workspace_hash'], row['project']))
    return dict(token=token,account=row['owner'],project=row['project'],step=stage,cycle=row['cycle'],role=row['role'],
                reusable=bool(device_token))


def validate_lease(db,token,is_post=True):
    row=db.execute("""SELECT m.*,e.step,e.cycle,p.card,ld.device,d.expires AS device_expires
        FROM plugin_leases l JOIN plugin_entry_meta m ON m.entry=l.entry
        JOIN plugin_entries e ON e.key=m.entry JOIN projects p ON p.id=e.project
        LEFT JOIN plugin_lease_devices ld ON ld.token=l.token
        LEFT JOIN plugin_devices d ON d.token=ld.device AND d.user=m.owner WHERE l.token=?""",(token,)).fetchone()
    if row and (is_post or row['device']):
        if row['device'] and (row['device_expires'] is None or row['device_expires'] <= time.time()):
            raise PilotError(401,'设备连接已失效，请重新连接教学账号。')
        if not row['current'] or not active_entry(row,json.loads(row['card'])):
            raise PilotError(409,'本次讨论已结束或已被替代，请回网页打开当前讨论。')
    return bool(row)


def export_project(handler,db,row,body):
    if row['role']!='student' or not row['current']:
        return {'inactive':True}
    if __package__:
        from .server import project_for
        from . import context_archive
    else:
        from server import project_for
        import context_archive
    user=db.execute('SELECT * FROM users WHERE id=?',(row['owner'],)).fetchone()
    card=project_for(db,user,row['project'])
    card=handler.server.project_archive.enrich(card)
    conversations,sync=discussions(db,row['project'])
    archive=handler.server.project_archive.read(card,force=True)
    archive.update(conversations=conversations,sync=sync)
    notes=context_archive.load_notes(handler.server.project_archive.folder(card))
    payload=dict(project=card,archive=archive,notes=notes)
    hashed=digest(json.dumps(payload,ensure_ascii=False,sort_keys=True))
    if body.get('known_hash')==hashed:
        return dict(unchanged=True,context_hash=hashed)
    return dict(payload,unchanged=False,context_hash=hashed)


def receive(db, binding, body):
    turn = parse_uuid(body.get('turn'))
    rows, complete = body.get('messages'), body.get('complete')
    abandoned = body.get('abandoned', False)
    if not isinstance(rows, list) or len(rows) > 40 or type(complete) is not bool:
        raise PilotError(422, '同步请求格式无效。')
    if type(abandoned) is not bool or abandoned and (rows or complete):
        raise PilotError(422, '取消同步请求格式无效。')
    if complete and (not rows or not any(isinstance(row, dict) and row.get('role') == 'assistant' for row in rows)):
        raise PilotError(422, '该轮尚无最终导师回复。')
    if not complete and any(not isinstance(row, dict) or row.get('role') != 'user' for row in rows):
        raise PilotError(422, '等待最终回复时仅可补充已发送的学生原文。')
    stamp = datetime.now(timezone.utc).isoformat()
    prior = db.execute('SELECT entry, complete FROM plugin_turns WHERE turn=?', (turn,)).fetchone()
    if prior and prior['entry'] != binding['key']:
        raise PilotError(409, '该轮次属于其他聊天。')
    if abandoned:
        if not prior:
            db.execute('INSERT INTO plugin_turns VALUES (?,?,?,?)', (turn, binding['key'], -1, stamp))
        elif prior['complete'] == 0:
            db.execute('UPDATE plugin_turns SET complete=-1,updated=? WHERE turn=?', (stamp, turn))
        return {'saved': True, 'complete': False, 'turn': turn, 'messages': 0}
    if not prior:
        db.execute('INSERT INTO plugin_turns VALUES (?,?,?,?)', (turn, binding['key'], complete, stamp))
    elif complete and prior['complete'] != 1:
        db.execute('UPDATE plugin_turns SET complete=1,updated=? WHERE turn=?', (stamp, turn))
    for ordinal, row in enumerate(rows):
        if (not isinstance(row, dict) or set(row) != {'id', 'role', 'text', 'time'}
                or row['role'] not in ('user', 'assistant') or not isinstance(row['text'], str)
                or not row['text'].strip() or len(row['text']) > 200000 or not isinstance(row['time'], str)
                or len(row['time']) > 40 or not isinstance(row['id'], str) or not re.fullmatch(r'[\w-]{1,150}', row['id'])):
            raise PilotError(422, '收到无效的聊天消息。')
        item = (row['id'], turn, ordinal, row['role'], row['text'], row['time'])
        existing = db.execute('SELECT * FROM plugin_messages WHERE id=?', (row['id'],)).fetchone()
        if existing and tuple(existing) != item:
            raise PilotError(409, '同一消息编号的原文不一致。')
        if not existing:
            if prior and prior['complete'] == 1:
                raise PilotError(409, '已同步的完整轮次不能添加消息。')
            db.execute('INSERT INTO plugin_messages VALUES (?,?,?,?,?,?)', item)
    return {'saved': True, 'complete': complete, 'turn': turn, 'messages': len(rows)}


def handle(handler, db, action, body, user):
    if action == 'device-saved':
        header = handler.headers.get('Authorization', '')
        token = digest(header[7:]) if header.startswith('Bearer ') else ''
        updated = db.execute('''UPDATE plugin_browser_connections SET saved=1 WHERE device=? AND
            EXISTS (SELECT 1 FROM plugin_devices WHERE token=? AND expires>?)''', (token, token, time.time())).rowcount
        if not updated:
            raise PilotError(401, '连接确认已失效，请重新连接。')
        if 'workspace_claims' in body:
            save_workspace_claims(db, token, body['workspace_claims'])
        previous = body.get('previous_token')
        if isinstance(previous, str) and 32 <= len(previous) <= 100 and digest(previous) != token:
            db.execute('DELETE FROM plugin_devices WHERE token=?', (digest(previous),))
        return {'saved': True}
    if action == 'runtime-settings':
        header = handler.headers.get('Authorization', '')
        device = db.execute('SELECT user FROM plugin_devices WHERE token=? AND expires>?',
                            (digest(header[7:]), time.time())).fetchone() if header.startswith('Bearer ') else None
        if not device:
            raise PilotError(401, '设备连接已失效，请重新连接教学账号。')
        if __package__:
            from . import runtime_config
        else:
            import runtime_config
        role = db.execute('SELECT role FROM users WHERE id=?', (device['user'],)).fetchone()[0]
        config = runtime_config.public_config(getattr(handler.server, 'runtime_config_path', None))
        return dict(config['roles'][role], revision=config['revision'])
    if action in ('device-request', 'authorize', 'device-token'):
        return pairing(handler, db, action, body, user)
    if action not in ('session', 'archive', 'export', 'recovery-context'):
        raise PilotError(404, '找不到插件接口。')
    row, thread = authorize_binding(handler, db, body, action in ('session','recovery-context'))
    if action == 'recovery-context':
        if not row['predecessor'] or row['thread']:
            return {'recovery':False, 'project_id': row['project']}
        payload=export_project(handler,db,row,{})
        if row['role']=='teacher':
            payload={'project':json.loads(row['card']),'archive':{},'context_hash':digest(row['card'])}
        token=secrets.token_urlsafe(32)
        db.execute('INSERT OR REPLACE INTO plugin_restores VALUES (?,?,?,?)',(row['key'],digest(token),thread,digest(row['card'])))
        return dict(payload,recovery=True,restore_token=token,project_id=row['project'])
    if action == 'export':
        return export_project(handler,db,row,body)
    if action == 'archive' and row['role'] != 'student':
        raise PilotError(403,'老师辅助审阅不写入学生讨论档案。')
    if action == 'session':
        return bind_session(db, row, thread, body.get('restore_token'), handler.headers['Authorization'][7:])
    return receive(db, row, body)


def discussions(db, project):
    conversations = {}
    for row in db.execute('''SELECT e.thread,e.step,m.id,m.role,m.text,m.stamp FROM plugin_entries e
        JOIN plugin_turns t ON e.key=t.entry JOIN plugin_messages m ON t.turn=m.turn
        WHERE e.project=? ORDER BY m.stamp,t.turn,m.ordinal''', (project,)):
        conversation = conversations.setdefault(row['thread'], {'thread_id': row['thread'], 'step': row['step'],
                                                                  'title': f'第 {row["step"]} 阶段讨论', 'messages': []})
        conversation['messages'].append({'id': row['id'], 'role': row['role'], 'text': row['text'], 'time': row['stamp']})
        conversation['updated'] = row['stamp']
    pending = db.execute('''SELECT 1 FROM plugin_entries e JOIN plugin_turns t ON e.key=t.entry
                             WHERE e.project=? AND t.complete=0 LIMIT 1''', (project,)).fetchone()
    receipt = db.execute('''SELECT t.turn,t.updated FROM plugin_turns t JOIN plugin_entries e ON e.key=t.entry
        WHERE e.project=? AND t.complete=1 ORDER BY t.updated DESC LIMIT 1''',(project,)).fetchone()
    sync = {'status': 'syncing' if pending else 'received' if receipt else 'unconfirmed',
            'last_complete_turn': receipt['turn'] if receipt else None,
            'last_receipt_at': receipt['updated'] if receipt else None}
    if conversations:
        sync['updated'] = max(c['updated'] for c in conversations.values())
    return list(conversations.values()), sync
