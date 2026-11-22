"""Desktop plugin bridge with an in-process, durable transcript archive loop."""

import argparse
import base64
from contextlib import closing, contextmanager
from dataclasses import astuple, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
import ntpath
import posixpath
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import threading
import time
from urllib.parse import quote
from unicodedata import normalize
import webbrowser

if __package__:
    from . import coach_mcp as mcp, context_archive, pilot_history, project_files, readable_archive, review_mcp, pilot_defaults
    from .workspace_store import atomic_json
else:
    import coach_mcp as mcp
    import context_archive
    import pilot_history
    import pilot_defaults
    import project_files
    import readable_archive
    import review_mcp
    from workspace_store import atomic_json


@dataclass(frozen=True)
class Job:
    owner: str
    stage: str
    thread: str
    turn: str
    log: str
    workspace: str

    def payload(self, messages, complete):
        return {'stage_session': self.stage, 'thread': self.thread, 'turn': self.turn,
                'messages': messages, 'complete': complete}


class Journal:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.open() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (owner TEXT, stage TEXT, thread TEXT, turn TEXT,
                       log TEXT, workspace TEXT, announced INTEGER DEFAULT 0, done INTEGER DEFAULT 0,
                       PRIMARY KEY(owner,turn))''')
            if 'completed' not in {row[1] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute('ALTER TABLE jobs ADD COLUMN completed INTEGER DEFAULT 0')
            db.execute('''CREATE TABLE IF NOT EXISTS local_bindings (owner TEXT, stage TEXT, log TEXT, workspace TEXT,
                       PRIMARY KEY(owner,stage))''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(local_bindings)')}
            for name, declaration in {'thread': "TEXT DEFAULT ''", 'project': "TEXT DEFAULT ''",
                    'role': "TEXT DEFAULT 'student'", 'cursor': "TEXT DEFAULT ''", 'scan_stamp': "TEXT DEFAULT ''",
                    'error': "TEXT DEFAULT ''", 'receipt': "TEXT DEFAULT ''", 'last_turn': "TEXT DEFAULT ''",
                    'export_hash': "TEXT DEFAULT ''"}.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE local_bindings ADD COLUMN {name} {declaration}')

    @contextmanager
    def open(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            yield db

    def enqueue(self, job):
        with self.open() as db:
            db.execute('INSERT OR IGNORE INTO jobs (owner,stage,thread,turn,log,workspace) VALUES (?,?,?,?,?,?)', astuple(job))

    def jobs(self, owner):
        with self.open() as db:
            return [(Job(*row[:6]), bool(row[6])) for row in db.execute(
                'SELECT owner,stage,thread,turn,log,workspace,announced FROM jobs WHERE owner=? AND done=0 ORDER BY rowid', (owner,))]

    def update(self, job, done=False, completed=False, error=''):
        with self.open() as db:
            db.execute('UPDATE jobs SET announced=1,done=MAX(done,?),completed=MAX(completed,?) WHERE owner=? AND turn=?',
                       (done, completed, job.owner, job.turn))
            # Out-of-order acknowledgements from two MCP processes cannot move the cutoff backwards.
            latest = db.execute('SELECT turn FROM jobs WHERE owner=? AND stage=? AND completed=1 ORDER BY rowid DESC LIMIT 1',
                                (job.owner, job.stage)).fetchone()
            db.execute('UPDATE local_bindings SET receipt=?,last_turn=COALESCE(?,last_turn),error=? WHERE owner=? AND stage=?',
                (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), latest[0] if latest else None, error, job.owner, job.stage))

    def binding(self, owner, stage):
        with self.open() as db:
            return db.execute('SELECT log,workspace FROM local_bindings WHERE owner=? AND stage=?', (owner, stage)).fetchone()

    def remember(self, owner, stage, log, workspace, thread='', project='', role='student'):
        with self.open() as db:
            db.execute('''INSERT INTO local_bindings (owner,stage,log,workspace,thread,project,role) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(owner,stage) DO UPDATE SET thread=excluded.thread,project=excluded.project,role=excluded.role''',
                (owner, stage, str(log), str(workspace), thread, project, role))

    def bindings(self, owner):
        with self.open() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM local_bindings WHERE owner=?', (owner,))]

    def workspace_claims(self, owner):
        with self.open() as db:
            rows = db.execute("SELECT DISTINCT owner, workspace, project FROM local_bindings WHERE project<>''")
            claims = {(workspace_hash(workspace), project if bound_owner == owner else '')
                      for bound_owner, workspace, project in rows}
        return [{'workspace_hash': path_hash, 'project': project} for path_hash, project in sorted(claims)]

    def state(self, owner, stage, **fields):
        allowed = {'cursor', 'scan_stamp', 'error', 'receipt', 'last_turn', 'export_hash'}
        if not fields or set(fields) - allowed:
            raise ValueError('Unknown archive state field')
        with self.open() as db:
            db.execute('UPDATE local_bindings SET ' + ','.join(key+'=?' for key in fields) + ' WHERE owner=? AND stage=?',
                       (*fields.values(), owner, stage))


def discover(journal, owner):
    """Only inspect explicitly registered logs, including after a process restart."""
    for binding in journal.bindings(owner):
        if binding['role'] != 'student':
            continue
        try:
            log = Path(binding['log'])
            stat = log.stat()
            stamp = f'{stat.st_size}:{stat.st_mtime_ns}'
            if stamp == binding['scan_stamp']:
                continue
            meta, turns, _ = pilot_history.transcript(log)
            if (meta.get('id') != binding['thread'] or not pilot_history.same_workspace(meta, Path(binding['workspace']))
                    or not pilot_history.owns_turns(turns, binding['stage'])):
                raise ValueError('聊天记录与登记不符，原文仍待同步。')
            for turn in turns:
                journal.enqueue(Job(owner, binding['stage'], binding['thread'], turn, str(log), binding['workspace']))
            journal.state(owner, binding['stage'], scan_stamp=stamp, cursor=next(reversed(turns), ''), error='')
        except (OSError, ValueError) as error:
            journal.state(owner, binding['stage'], error=str(error))


def process_jobs(journal, owner, publish):
    progress = False
    for job, announced in journal.jobs(owner):
        try:
            meta, turns, _ = pilot_history.transcript(Path(job.log))
            if (meta.get('id') != job.thread or not pilot_history.same_workspace(meta, Path(job.workspace))
                    or not pilot_history.owns_turns(turns, job.stage) or job.turn not in turns):
                raise ValueError('聊天原文与登记不符或源格式已变化，保留待同步。')
            turn = turns[job.turn]
            messages = list(turn.messages.values())
            ready = turn.complete and any(message['role'] == 'assistant' for message in messages)
            format_error = '已见结束标记但未读到完整最终回复，原文保留待同步；请检查 Codex 记录格式。' if turn.complete and not ready else ''
            if format_error:
                journal.state(owner, job.stage, error=format_error)
            if turn.aborted:
                # Retain the user's words even when the assistant never finished.
                sources = [row for row in messages if row['role'] == 'user']
                if sources and publish(job.payload(sources, False)).get('saved') is not True:
                    continue
                payload = dict(job.payload([], False), abandoned=True)
            elif ready:
                payload = job.payload(messages, True)
            elif not announced:
                payload = job.payload([], False)
            else:
                continue
            if publish(payload).get('saved') is True:
                journal.update(job, done=ready or turn.aborted, completed=ready, error=format_error)
                progress = True
        except (OSError, ValueError, mcp.ToolError) as error:
            journal.state(owner, job.stage, error=str(error))
            continue  # The next poll or the next Codex chat retries the same messages.
    return progress


def state_folder():
    return Path(os.environ.get('PROPOSAL_PILOT_STATE', Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ProposalCoachPilot' / 'state'))


def load_device(origin, folder):
    try:
        binding = json.loads((folder / 'device.json').read_text('utf-8'))
        if binding['origin'] == origin:
            return mcp.Client(origin, binding['token'], binding['account'])
    except (OSError, ValueError, KeyError):
        pass
    raise mcp.ToolError('请运行安装包中的「安装开题手记」，在教学网页完成连接。')


def local_connection(origin, device_code):
    class Handoff(BaseHTTPRequestHandler):
        def reply(self, preflight):
            if (self.path != '/pairing' or self.headers.get('Origin') != origin or
                    self.headers.get('Host') != '127.0.0.1:48767'):
                self.send_error(403)
                return
            self.send_response(204 if preflight else 200)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if not preflight:
                self.wfile.write(json.dumps({'device_code': device_code}).encode('ascii'))

        def do_GET(self):
            self.reply(False)

        def do_OPTIONS(self):
            self.reply(True)

        def log_message(self, *args):
            pass

    @contextmanager
    def running():
        with ThreadingHTTPServer(('127.0.0.1', 48767), Handoff) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                yield
            finally:
                server.shutdown()
                worker.join()
    return running()


def pair(origin, folder, open_browser=webbrowser.open, *, local=False):
    client = mcp.Client(origin)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    pairing = client.request('/api/plugin/device-request', {'challenge': challenge, 'local': local})
    if local:
        if not re.fullmatch(r'[0-9]{3}', pairing.get('pin', '')):
            raise mcp.ToolError('此网站还不支持三位连接码，请核对开题手记网址。')
        with local_connection(client.origin, pairing['device_code']):
            print(f"\n连接码：{pairing['pin']}\n回开题手记的连接向导，点「我已有三位连接码」并输入。\n请保持本窗口打开，直到连接完成。", flush=True)
            wait_for_connection(client, folder, pairing['device_code'], verifier, local=True)
        return
    address = pairing['verify_url']
    if not address.startswith(client.origin + '/plugin-connect.html?device='):
        raise mcp.ToolError('教学网站给出的连接地址无效。')
    print('请在浏览器登录教学网站并批准这台电脑。', flush=True)
    if not open_browser(address):
        print(address, flush=True)
    wait_for_connection(client, folder, pairing['device_code'], verifier)


def wait_for_connection(client, folder, code, verifier, *, local=False):
    started = time.monotonic()
    deadline = started + (86400 if local else 600)
    request = {'device_code': code, 'verifier': verifier}
    try:
        previous = load_device(client.origin, folder).token if local else ''
    except mcp.ToolError:
        previous = ''
    while time.monotonic() < deadline:
        try:
            result = client.request('/api/plugin/device-token', request)
        except mcp.Offline:
            result = {'pending': True}
        if not result.get('pending'):
            atomic_json(folder / 'device.json', dict(origin=client.origin, token=result['token'], account=result['account']))
            if local:
                device = load_device(client.origin, folder)
                claims = Journal(folder / 'archives.sqlite3').workspace_claims(device.owner)
                for attempt in range(5):
                    try:
                        device.request('/api/plugin/device-saved', {'previous_token': previous, 'workspace_claims': claims})
                        break
                    except mcp.Offline:
                        if attempt == 4:
                            raise
                        time.sleep(2)
            try:
                pilot_defaults.sync(load_device(client.origin, folder), folder)
            except (mcp.ToolError, OSError, ValueError, sqlite3.Error) as error:
                print('教学账号已连接；默认模型待同步：' + str(error), flush=True)
            return
        elapsed = time.monotonic() - started
        time.sleep(15 if local and elapsed > 120 else 2)
    raise mcp.ToolError('连接已超时，请重新运行「安装开题手记」。')


def workspace_hash(root):
    path = str(root)
    if path.startswith('/'):
        normalized = 'macos:' + normalize('NFC', posixpath.normpath('/' + path.lstrip('/')))
    else:
        normalized = ntpath.normpath(path.replace('/', '\\')).lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


@contextmanager
def workspace_lock(root):
    """Serialize generated-file ownership and publication across MCP processes."""
    if not Path(root).is_dir():
        raise ValueError('课题目录不可用，请在网页恢复本机讨论。')
    path = readable_archive._path(Path(root), '.coach/plugin-export-lock.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=20)) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            yield
        finally:
            db.rollback()


def claim_workspace(root, owner, project, *, locked=False):
    if not locked:
        with workspace_lock(root):
            return claim_workspace(root, owner, project, locked=True)
    path = readable_archive._path(Path(root), '.coach/plugin-owner.json')
    identity = {'owner': owner, 'project': project}
    if path.exists():
        if json.loads(path.read_text('utf-8')) != identity:
            raise mcp.ToolError('这个文件夹已属于其他教学账号或课题，请在网页选择独立的课题文件夹。')
    else:
        atomic_json(path, identity)


def protected_export(root, result, *, owner=None, locked=False):
    """Preserve user edits even to a previously generated file."""
    root = Path(root)
    if not locked:
        with workspace_lock(root):
            return protected_export(root, result, owner=owner, locked=True)
    if owner is not None:
        claim_workspace(root, owner, result['project']['id'], locked=True)
    hashes_path = readable_archive._path(root, '.coach/plugin-export-hashes.json')
    version_path = readable_archive._path(root, '.coach/plugin-export-version.json')
    with readable_archive._LOCK:
        if version_path.exists():
            saved = json.loads(version_path.read_text('utf-8'))
            if saved.get('project') != result['project']['id']:
                raise mcp.ToolError('本机成果属于另一个课题，请选择独立文件夹。')
            if saved.get('version', 0) > result['project'].get('version', 0):
                return  # A recovery response must not overwrite a later background export.
        try:
            previous = json.loads(hashes_path.read_text('utf-8'))
        except (OSError, ValueError):
            previous = {}
        manifest = readable_archive._load(root)
        for key, relative in list(manifest.items()):
            path = readable_archive._path(root, relative)
            if relative in previous and path.is_file():
                if hashlib.sha256(path.read_bytes()).hexdigest() != previous[relative]:
                    del manifest[key]  # _write allocates a new file, preserving this edited copy.
        readable_archive._save(root, manifest)
        readable_archive.export_readable(root, result['project'], result['archive'])
        context_archive.export(root, result['project'], result['archive'],
                               result.get('notes') or {'revision': 0, 'entries': [], 'coverage': {}})
        current = readable_archive._load(root)
        hashes = {relative: hashlib.sha256(readable_archive._path(root, relative).read_bytes()).hexdigest()
                  for relative in current.values() if readable_archive._path(root, relative).is_file()}
        atomic_json(hashes_path, hashes)
        atomic_json(version_path, {'project': result['project']['id'], 'version': result['project'].get('version', 0)})


ARCHIVE_TOOL = mcp.tool('schedule_archive', '加速本轮原文归档；后台也会自动发现登记聊天的新轮次。'
                        '需要引用本轮学生原话时用 include_evidence=true，一轮内复用返回的编号；evidence_pending 表示没有可引用的当轮用户消息，先保存不需原话的草稿，不循环重试。',
                        {'project_id': mcp.PROJECT, 'include_evidence': {'type': 'boolean'}}, ['include_evidence'])
TOOLS = [*mcp.TOOLS, ARCHIVE_TOOL, *review_mcp.TOOLS]
TOOLS = [entry for entry in TOOLS if entry['name'] not in ('proposal_list_projects', 'proposal_recheck', 'proposal_revise')]
SCHEMAS = {}
for entry in TOOLS:
    original = entry['inputSchema']
    schema = {**original, 'properties': dict(original['properties']), 'required': list(original.get('required', []))}
    if entry['name'].startswith('review_'):
        schema['properties'].update(project_id=mcp.PROJECT, stage_session=mcp.text_field('网页给出的审阅会话编号。'))
        schema['required'].append('project_id')
    if 'project_id' in schema['properties']:
        schema['required'].append('stage_session')
        schema['required'] = [key for key in schema['required'] if key != 'project_id']
        if entry['name'] in ('proposal_read_project', 'review_read_project'):
            schema['properties']['workspace'] = mcp.text_field('首次读取时传当前 Codex 工作目录的绝对路径（环境上下文的 cwd）。')
    if entry['name'] in ('proposal_source', 'proposal_reflect', 'proposal_record', 'proposal_upload'):
        schema['required'].append('version')
    SCHEMAS[entry['name']] = schema
TOOLS = [dict(entry, inputSchema=SCHEMAS[entry['name']]) for entry in TOOLS]


class Bridge:
    def __init__(self, origin, folder, sessions=None):
        self.origin = origin
        self.folder = folder
        self.sessions = sessions or Path(os.environ.get('PROPOSAL_CODEX_SESSIONS',
                                                         Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'sessions'))
        self.journal = Journal(folder / 'archives.sqlite3')
        self.stopping = threading.Event()
        self.wake = threading.Event()
        self.worker = None
        self.export_lock = threading.RLock()
        self.leases = {}

    def start(self):
        if self.worker is None:
            self.worker = threading.Thread(target=self._background, name='proposal-archive', daemon=True)
            self.worker.start()
        return self

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.worker is not None:
            self.worker.join(timeout=2)

    def _background(self):
        next_export = 0
        next_defaults = 0
        while not self.stopping.is_set():
            try:
                device = load_device(self.origin, self.folder)
                if time.monotonic() >= next_defaults:
                    next_defaults = time.monotonic() + 30
                    try:
                        pilot_defaults.sync(device, self.folder)
                    except (mcp.ToolError, OSError, ValueError, sqlite3.Error):
                        pass  # A configuration failure must not block transcript receipts.
                discover(self.journal, device.owner)
                progress = process_jobs(self.journal, device.owner,
                                        lambda body: device.request('/api/plugin/archive', body))
                if progress or time.monotonic() >= next_export:
                    for binding in self.journal.bindings(device.owner):
                        if self.stopping.is_set():
                            break
                        self.refresh_export(device, binding)
                    next_export = time.monotonic() + 15
            except (mcp.ToolError, OSError, ValueError, sqlite3.Error, KeyError, TypeError):
                pass  # Credentials and durable jobs are retried in this same process.
            self.wake.wait(1)
            self.wake.clear()

    def refresh_export(self, device, binding):
        if binding['role'] != 'student' or not binding['project']:
            return
        try:
            with self.export_lock:
                root = Path(binding['workspace'])
                if not root.is_dir():
                    raise ValueError('课题目录不可用，请在网页恢复本机讨论。')
                result = device.request('/api/plugin/export', {'stage_session': binding['stage'],
                    'thread': binding['thread'], 'known_hash': binding['export_hash']})
                if result.get('inactive') or result.get('unchanged'):
                    return
                if result['project']['id'] != binding['project']:
                    raise ValueError('导出课题与本机登记不符。')
                protected_export(root, result, owner=device.owner)
                self.journal.state(device.owner, binding['stage'], export_hash=result['context_hash'])
        except (mcp.ToolError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            self.journal.state(device.owner, binding['stage'], error='本机导出待重试：' + str(error))

    def __call__(self, name, args):
        if name not in SCHEMAS:
            raise mcp.ToolError('未知教学工具。')
        if name == 'proposal_read_project_file' and isinstance(args, dict) and type(args.get('limit')) is int:
            maximum = SCHEMAS[name]['properties']['limit']['maximum']
            if args['limit'] > maximum:
                args = dict(args, limit=maximum)
        mcp.validate(SCHEMAS[name], args)
        if name == 'proposal_guide':
            return mcp.run_tool(name, args)
        device = load_device(self.origin, self.folder)
        if 'project_id' not in SCHEMAS[name]['properties']:
            return mcp.run_tool(name, args, client=device)
        stage = args['stage_session']
        if not re.fullmatch(r'[a-f0-9]{32}', stage):
            raise mcp.ToolError('请使用网页生成的本次聊天会话编号。')
        prior = self.journal.binding(device.owner, stage)
        if prior and args.get('workspace') and Path(args['workspace']).resolve() != Path(prior[1]).resolve():
            raise mcp.ToolError('已有聊天目录与当前目录不符，请回网页使用“恢复本机讨论”。')
        root = Path(prior[1] if prior else args.get('workspace', ''))
        if not root.is_absolute() or not root.is_dir():
            raise mcp.ToolError('请从绑定课题文件夹的 Codex 聊天中读取项目。首次读取需要传入当前工作目录。')
        root = root.resolve()
        if root in (Path(root.anchor), Path.home().resolve()) or root.is_relative_to(self.sessions.parent.resolve()):
            raise mcp.ToolError('请在 Codex 打开独立的课题文件夹。')
        for attempt in range(12):
            try:
                log, thread, turns, turn = pilot_history.find_active(self.sessions, root, stage, prior[0] if prior else None)
                break
            except ValueError:
                if attempt == 11:
                    raise
                time.sleep(0.15)
        else:
            raise AssertionError('No active Codex turn')
        binding_request = {'stage_session': stage, 'thread': thread, 'workspace_hash': workspace_hash(root)}
        recovery = device.request('/api/plugin/recovery-context', binding_request) if not prior else {}
        if prior:
            project = next(row['project'] for row in self.journal.bindings(device.owner) if row['stage'] == stage)
        else:
            project = recovery.get('project_id') or args.get('project_id')
        if not project or args.get('project_id', project) != project:
            raise mcp.ToolError('聊天只属于网页指定的课题。请回网页重新打开。')
        args = dict(args, project_id=project)
        if not name.startswith('review_'):
            for binding in self.journal.bindings(device.owner):
                if (binding['project'] and binding['project'] != project
                        and Path(binding['workspace']).resolve() == root):
                    raise mcp.ToolError('该文件夹已用于另一个课题。请在网页为本课题选择独立文件夹。')
        if recovery.get('recovery'):
            binding_request['restore_token'] = recovery['restore_token']
        with workspace_lock(root):
            owner_path = readable_archive._path(root, '.coach/plugin-owner.json')
            if owner_path.exists() and json.loads(owner_path.read_text('utf-8')) != {
                    'owner': device.owner, 'project': args['project_id']}:
                raise mcp.ToolError('这个文件夹已属于其他教学账号或课题，请在网页选择独立的课题文件夹。')
            # The server revalidates device and stage on each request.
            cache_key = (device.token, stage, thread)
            cached = self.leases.get(cache_key)
            reused = cached is not None and time.monotonic() < cached[0]
            lease = cached[1] if reused else device.request('/api/plugin/session', binding_request)
            if lease['project'] != args['project_id']:
                raise mcp.ToolError('聊天只属于网页指定的课题。')
            role = lease.get('role', 'student')
            if name.startswith('review_') != (role == 'teacher'):
                raise mcp.ToolError('请使用与当前学生讨论或老师审阅入口对应的工具。')
            claim_workspace(root, device.owner, lease['project'], locked=True)
            if not reused and lease.get('reusable'):
                self.leases[cache_key] = (time.monotonic() + 8 * 3600 - 60, lease)
        self.journal.remember(device.owner, stage, log, root, thread, lease['project'], role)
        recovery_context = None
        if recovery.get('recovery') and role == 'student':
            if recovery['project']['id'] != lease['project']:
                raise mcp.ToolError('恢复资料课题不符，请回网页重新恢复。')
            with self.export_lock:
                protected_export(root, recovery, owner=device.owner)
            recovery_context = context_archive.packet(recovery['project'], recovery['archive'], recovery.get('notes'))
            recovery_context['recovery_notice'] = '已从服务端收到的成果与原文接续；旧设备尚未上传的记录和个人文件需在旧设备补传或自行转移。'
        self.wake.set()
        client = mcp.Client(device.origin, lease['token'], lease['account'])
        if name == 'proposal_schedule_archive':
            if lease.get('reusable'):
                client.request('/api/plugin-lease')
            return self.schedule(device, stage, log, root, thread, turns, turn, args.get('include_evidence', False))
        body = {k: v for k, v in args.items() if k not in ('workspace', 'stage_session')}
        if name.startswith('review_'):
            body.pop('project_id')
            return review_mcp.run_tool(name, body, client=client, project=lease['project'], folder=root)
        if name == 'proposal_search_project_files':
            if lease.get('reusable'):
                client.request('/api/plugin-lease')
            found = project_files.search(root, body.get('query', ''), body.get('offset', 0), body.get('limit', 30))
            return dict(found, teaching_index=context_archive.PREFIX + '/INDEX.md')
        if name == 'proposal_read_project_file':
            relative = body['path'].replace('\\', '/')
            if relative.startswith(context_archive.PREFIX + '/'):
                path = '/api/projects/' + quote(args['project_id'], safe='') + '/plugin-context-file'
                return client.request(path, dict(path=relative, offset=body.get('offset', 0), limit=body.get('limit', 12000)))
            if lease.get('reusable'):
                client.request('/api/plugin-lease')
            return project_files.read(root, relative, body.get('offset', 0), body.get('limit', 12000))
        if name == 'proposal_upload':
            path = Path(body['path'])
            if not path.is_absolute():
                raise mcp.ToolError('请使用课题文件夹内的材料路径。')
            project_files.checked(root, path.relative_to(root))
        result = mcp.run_tool(name, body, client=client)
        if recovery_context is not None and isinstance(result, dict):
            result['recovery_context'] = recovery_context
        # Export and archive on the background worker so model replies do not
        # wait for another server request and a local mirror write.
        self.wake.set()
        if name == 'proposal_read_project' and isinstance(result, dict):
            binding = next(row for row in self.journal.bindings(device.owner) if row['stage'] == stage)
            result['plugin_sync'] = {key: binding[key] for key in ('cursor', 'last_turn', 'receipt', 'error')}
            result['plugin_sync']['note'] = '原文由本进程自动补传；回执仅覆盖已经收到的轮次，本机文件更新不表示导师已读取。'
        return result

    def schedule(self, device, stage, log, root, thread, turns, turn, include_evidence):
        current = Job(device.owner, stage, thread, turn, str(log), str(root))
        for key, item in turns.items():
            if key == turn or item.complete and any(m['role'] == 'assistant' for m in item.messages.values()):
                self.journal.enqueue(Job(device.owner, stage, thread, key, str(log), str(root)))
        self.wake.set()
        receipt = {'scheduled': True, 'turn': turn}
        if include_evidence:
            sources = [row for row in turns[turn].messages.values() if row['role'] == 'user']
            if not sources:
                return dict(receipt, evidence_pending=True)
            device.request('/api/plugin/archive', current.payload(sources, False))
            receipt['student_messages'] = sources
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('serve', 'connect'))
    parser.add_argument('--origin', required=True)
    parser.add_argument('--local', action='store_true')
    args = parser.parse_args()
    origin = mcp.server_url(args.origin)
    folder = state_folder()
    os.environ['PROPOSAL_CLIENT_DIR'] = str(folder / 'tool-state')
    try:
        if args.action == 'connect':
            pair(origin, folder, local=args.local)
            print('教学账号已连接。回开题手记，打开或继续 Codex 聊天。', flush=True)
        else:
            bridge = Bridge(origin, folder).start()
            try:
                mcp.serve(tools=TOOLS, runner=bridge)
            finally:
                bridge.close()
    except (mcp.ToolError, ValueError, OSError, sqlite3.Error) as error:
        sys.exit(str(error))


if __name__ == '__main__':
    main()
