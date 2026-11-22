"""Project-only visible chat archive, evidence-linked feedback and handoff exports."""
import json
import os
import re
from pathlib import Path
from threading import Lock
import time
import uuid
import hashlib
from urllib.parse import parse_qs, urlsplit

try:
    from . import context_archive
    from .teaching_context import brief, empty_opening
except ImportError:
    import context_archive
    from teaching_context import brief, empty_opening


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def visible_messages(path):
    messages = []
    seen = set()
    for index, line in enumerate(path.read_text("utf-8").splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue  # The active rollout can end with an incomplete line.
        item = row.get("payload", {})
        if row.get("type") != "response_item" or item.get("type") != "message":
            continue
        role = item.get("role")
        if role == "assistant" and item.get("phase") != "final_answer":
            continue
        if role not in ("user", "assistant"):
            continue
        text = "\n".join(c.get("text", "") for c in item.get("content", [])
                         if c.get("type") in ("input_text", "output_text", "text"))
        # Codex records environment/AGENTS context as user messages too.
        if role == "user":
            if text.startswith(("# AGENTS.md", "<environment_context>", "<permissions", "<turn_aborted>", "<subagent_notification>")):
                continue
        if not text.strip():
            continue
        if role == "user" and re.match(r"开始.{1,100}开题讨论。请", text):
            continue  # App-generated launch prompt is not evidence of student ability.
        identity = item.get("id") or f"{path.stem}-message-{index}"
        if identity in seen:
            continue
        seen.add(identity)
        messages.append({"id": identity, "role": role, "text": text, "time": row.get("timestamp", "")})
    return messages


class ProjectArchive:
    def __init__(self, root, sessions=None, workspaces=None, uploaded=None, site_origin=None):
        self.root = Path(root)
        self.workspaces = workspaces
        self.uploaded = uploaded
        self.site_origin = urlsplit(site_origin or '')
        self.sessions = None if uploaded else Path(sessions or (Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"))
        self.lock = Lock()
        self.paths = {}
        self.checked = {}

    def folder(self, card):
        if self.workspaces:
            return self.workspaces.internal(card["student_id"],card["id"])
        return self.root / card["student_id"] / card["id"]

    def registered(self, folder):
        records = []
        for path in (folder / 'threads').glob('*.json'):
            try:
                record = json.loads(path.read_text('utf-8'))
                uuid.UUID(record['thread_id'])
                records.append(record)
            except (OSError, ValueError, KeyError):
                continue
        for path in [folder / 'conversation-history.json', *folder.glob('stages/*/conversation-history.json')]:
            if path.exists():
                for record in json.loads(path.read_text('utf8')):
                    if record.get('thread_id'):
                        uuid.UUID(record['thread_id'])
                        records.append(record)
        for path in [folder / "conversation.json", *folder.glob("stages/*/conversation.json")]:
            try:
                record = json.loads(path.read_text("utf-8"))
                if record.get("thread_id"):
                    uuid.UUID(record["thread_id"])
                    record["step"] = record.get("step", 0)
                    records.append(record)
            except (OSError, ValueError):
                continue
        return {r["thread_id"]: r for r in records}.values()

    def read(self, card, force=False):
        folder = self.folder(card)
        path = folder / "discussions.json"
        with self.lock:
            try:
                archive = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                archive = {"conversations": [], "feedback": [], "profile": {}}
            if self.uploaded:
                archive['conversations'], archive['sync'] = self.uploaded(card['id'])
                return archive
            if not force and time.monotonic() - self.checked.get(str(folder), 0) < 10:
                return archive
            self.checked[str(folder)] = time.monotonic()
            prior = {r["thread_id"]: r for r in archive["conversations"]}
            missing = False
            for record in self.registered(folder):
                tid = record["thread_id"]
                source = self.paths.get(tid)
                if source is None or not source.exists():
                    # Search only names belonging to this app's registered thread IDs.
                    source = next(self.sessions.rglob(f"*{tid}.jsonl"), None)
                    if source:
                        self.paths[tid] = source
                if source is None:
                    missing = True
                    continue
                try:
                    messages = visible_messages(source)
                except OSError:
                    missing = True
                    continue
                prior[tid] = {"thread_id": tid, "step": record["step"],
                    "title": record.get("title", "此前的开题讨论"), "messages": messages,
                    "updated": messages[-1]["time"] if messages else ""}
            archive["conversations"] = sorted(prior.values(), key=lambda r: r.get("updated", ""))
            archive["sync"] = {"status": "error" if missing else "ready",
                "message": "部分对话暂未取到，已保存的记录仍可查看。" if missing else "已同步本项目的对话"}
            atomic_json(path, archive)
            return archive

    def reflect(self, card, body):
        if type(body.get("step", card["current_step"])) is not int or not 1 <= body.get("step", card["current_step"]) <= 6:
            raise ValueError("学习反馈必须关联六项任务之一。")
        archive = self.read(card, force=True)
        evidence = {m["id"]: m for c in archive["conversations"] for m in c["messages"]}
        if body.get("evidence_id") not in evidence or evidence[body["evidence_id"]]["role"] != "user":
            raise ValueError("请引用本项目中一条学生原话的消息编号。")
        if not all(isinstance(body.get(k), str) and body[k].strip() for k in
                   ("dimension", "observation", "next_action", "request_id")):
            raise ValueError("学习反馈需要观察、学生原话依据和下一项练习。")
        if body["dimension"] not in ("提出问题", "使用证据", "独立判断", "解释限制"):
            raise ValueError("请选择已有的学习反馈维度。")
        with self.lock:
            # Reload under lock so concurrent reflections cannot overwrite one another.
            path = self.folder(card) / "discussions.json"
            if self.uploaded:
                try:
                    archive.update(json.loads(path.read_text('utf-8')))
                except FileNotFoundError:
                    pass
                archive['conversations'] = []  # Uploaded messages are held in SQLite.
            else:
                archive = json.loads(path.read_text("utf-8"))
            old = next((f for f in archive["feedback"] if f["id"] == body["request_id"]), None)
            row = {k: body[k] for k in ("dimension", "observation", "evidence_id", "next_action")}
            row.update(id=body["request_id"], step=body.get("step", card["current_step"]), source="AI 导师观察")
            if old and old != row:
                raise ValueError("此反馈编号已用于另一条记录。")
            if not old:
                archive["feedback"].append(row)
            # A learning profile is an evidenced, revisable set of observations, not a trait label.
            archive["profile"] = {f["dimension"]: {"observation": f["observation"],
                "next_action": f["next_action"], "evidence_id": f["evidence_id"]} for f in archive["feedback"]}
            atomic_json(path, archive)
        return {"saved": True, "feedback": row}

    def source(self, card, body):
        if not all(isinstance(body.get(k), str) and body[k].strip() for k in ('title', 'url', 'help', 'limit')):
            raise ValueError('请提供文章标题、原文链接、对本研究的帮助和局限。')
        if urlsplit(body['url']).scheme not in ('http', 'https') or not urlsplit(body['url']).netloc:
            raise ValueError('文章链接须为 HTTP 或 HTTPS 原文地址。')
        row = {k: body[k].strip() for k in ('title', 'url', 'help', 'limit')}
        row['id'] = hashlib.sha256(row['url'].encode()).hexdigest()[:20]
        row['step'] = card['current_step']
        with self.lock:
            path = self.folder(card) / 'sources.json'
            receipts_path = self.folder(card) / 'source-receipts.json'
            try:
                receipts = json.loads(receipts_path.read_text('utf-8'))
            except (OSError, ValueError):
                receipts = {}
            key = body.get('request_id')
            if not isinstance(key, str) or not key.strip():
                raise ValueError('保存材料需要提交编号。')
            prior = receipts.get(key)
            if prior:
                if any(prior.get(k) != row[k] for k in ('title', 'url', 'help', 'limit')):
                    raise ValueError('此提交编号已用于不同的材料内容。')
                return {'saved': True, 'source': prior}
            try:
                rows = json.loads(path.read_text('utf-8'))
            except (OSError, ValueError):
                rows = []
            rows = [r for r in rows if r['id'] != row['id']] + [row]
            atomic_json(path, rows)
            receipts[key] = row
            atomic_json(receipts_path, receipts)
        return {'saved': True, 'source': row}

    def enrich(self, card):
        card = dict(card)
        archive = self.read(card)
        card['student_message_ids']=[m['id'] for conversation in archive['conversations'] for m in conversation['messages'] if m['role']=='user']
        sources = {}
        # Existing literature outcomes become usable materials without model re-entry.
        for step in card['steps']:
            for paper in step['data'].get('papers', []):
                url = paper.get('source', '')
                if urlsplit(url).scheme not in ('http', 'https'):
                    continue
                sources[url] = {'id': hashlib.sha256(url.encode()).hexdigest()[:20],
                    'title': paper.get('title', url), 'url': url, 'help': paper.get('finding', ''),
                    'limit': paper.get('limit', ''), 'step': step['number']}
        # Preserve linked reading leads even if an old conversation never registered them.
        for conversation in archive['conversations']:
            for message in conversation['messages']:
                if message['role'] != 'assistant':
                    continue
                for match in re.finditer(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)', message['text']):
                    title, url = match.groups()
                    address = urlsplit(url)
                    project_link = address.path in ('', '/', '/index.html') and card['id'] in parse_qs(address.query).get('project', [])
                    same_site = bool(self.site_origin.netloc and address.netloc == self.site_origin.netloc)
                    if address.hostname in ('localhost', '127.0.0.1') or same_site or project_link or url in sources:
                        continue
                    paragraph = message['text'][max(0, message['text'].rfind('\n', 0, match.start())+1):message['text'].find('\n', match.end()) if '\n' in message['text'][match.end():] else len(message['text'])]
                    sources[url] = {'id': hashlib.sha256(url.encode()).hexdigest()[:20], 'title': title,
                        'url': url, 'help': paragraph, 'limit': '', 'step': conversation['step'], 'lead': True}
        try:
            for source in json.loads((self.folder(card) / 'sources.json').read_text('utf-8')):
                sources[source['url']] = source
        except (OSError, ValueError):
            pass
        card['materials'] = list(sources.values())
        if self.workspaces:
            card['workspace'] = self.workspaces.describe(card)
        if (card['current_step']==1 and card['status']=='active' and not card['files'] and not sources
                and not any(s['data'] for s in card['steps']) and not archive['conversations']
                and not card.get('research',{}).get('objects')
                and not list((self.folder(card)/'stages').glob('*/opening-answer.json'))):
            card['opening_text'] = empty_opening()
        card['learning_profile'] = archive.get('profile', {})
        card.setdefault('quality', {'records': []})
        card['learning_support'] = [r for r in card['quality']['records'] if r['kind'] == 'support']
        try:
            card['handoff_notes'] = json.loads((self.folder(card) / 'notes.json').read_text('utf-8'))
        except (OSError, ValueError):
            card['handoff_notes'] = []
        card['teaching_brief'] = brief(card)
        def signature(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        card['reading_items'] = {
            'card': [str(s['number'])+':'+signature(s['data']) for s in card['steps'] if s['data']],
            'files': [s['id']+':'+signature(s) for s in card['materials']] + [f['id'] for f in card['files']],
            'learning': [f['id'] for f in archive.get('feedback', [])] + [m['id'] for c in archive['conversations'] for m in [next((m for m in reversed(c['messages']) if m['role']=='assistant'), None)] if m]}
        return card

    def mirror_files(self, connection, card):
        folder = self.folder(card) / 'materials'
        notes = []
        for row in connection.execute('SELECT id,name,content FROM files WHERE project=?', (card['id'],)):
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / row['id']
            if not target.exists():
                temp = folder / (uuid.uuid4().hex+'.tmp')
                temp.write_bytes(row['content'])
                temp.replace(target)
            if self.workspaces:
                visible=self.workspaces.visible(card['student_id'],card['id'])
                if visible:
                    try:
                        from .readable_archive import export_attachment
                    except ImportError:
                        from readable_archive import export_attachment
                    export_attachment(visible,row['id'],row['name'],bytes(row['content']))
            if Path(row['name']).suffix.lower() in ('.md', '.txt', '.csv'):
                content = bytes(row['content']).decode('utf-8', errors='replace')
                notes.append({'file_id': row['id'], 'name': row['name'], 'text': content[:12000], 'truncated': len(content)>12000})
        atomic_json(self.folder(card) / 'notes.json', notes)

    def export(self, card):
        card = self.enrich(card)
        with self.lock:
            self._export(card)

    def context(self, card, known_hash=''):
        card = self.enrich(card)
        # Context is the handoff boundary: synchronize raw sources in code, not
        # through model turns, even if the ordinary UI archive cache is still warm.
        archive = self.read(card, force=True)
        with self.lock:
            latest = self.folder(card) / 'project.json'
            if latest.exists():
                saved = json.loads(latest.read_text('utf8'))
                if saved.get('version', 0) > card.get('version', 0):
                    card = saved
            notes = context_archive.load_notes(self.folder(card))
            visible = self.workspaces.visible(card['student_id'], card['id']) if self.workspaces else None
            if self.uploaded:
                visible = self.context_root(card)
                context_hash = context_archive.digest(['plugin-context-v1', card, archive, notes])
                if known_hash == context_hash and visible.is_dir():
                    return {'unchanged': True, 'context_hash': context_hash, 'version': card['version'],
                            'requirement_version': card.get('activity', {}).get('version'),
                            'current_step': card['current_step'], 'status': card['status']}
            paths = context_archive.export(visible, card, archive, notes) if visible else None
            packet = context_archive.packet(card, archive, notes, paths)
            if self.uploaded:
                packet['context_hash'] = context_hash
            return packet

    def context_root(self, card):
        return self.folder(card) / 'context-files'

    def save_continuity(self, card, body):
        archive = self.read(card, force=True)
        with self.lock:
            prior = context_archive.load_notes(self.folder(card))
            notes = context_archive.update_notes(prior, body, archive, card)
            atomic_json(self.folder(card) / 'continuity.json', notes)
        self.export(card)
        return {'saved': True, 'revision': notes['revision'], 'result_id': body['request_id']}

    def _export(self, card):
        folder = self.folder(card)
        try:
            previous=json.loads((folder / "project.json").read_text("utf-8"))
            if previous.get("version",0) > card.get("version",0):
                return
        except (OSError, ValueError):
            pass
        atomic_json(folder / "project.json", card)
        lines = ["# 项目交接", card["title"], "", f"当前任务：{card['current_step']}；状态：{card['status']}",
                 "下一动作：" + card["next_action"], "", "## 当前活动时间预算", json.dumps(card.get('budget',{}),ensure_ascii=False)]
        for step in card["steps"]:
            lines += ["", f"## {step['number']}. {step['title']} · {step['status']}"]
            for key, value in step["data"].items():
                lines.append(f"- {key}: " + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))
        lines += ["", "## 最近学习观察"]
        if card.get('quality', {}).get('records'):
            try:
                from .quality_records import markdown
            except ImportError:
                from quality_records import markdown
            lines += ['', markdown(card)]
        for source in card.get('materials', []):
            lines += ['', '### '+source['title'], source['url'], source['help'], source.get('limit', '')]
        for note in card.get('handoff_notes', []):
            lines += ['', '### 过程记录：'+note['name'], note['text']]
            if note['truncated']:
                lines.append('全文请通过 proposal_open_material 读取：'+note['file_id'])
        try:
            archive = json.loads((folder / "discussions.json").read_text("utf-8"))
            for feedback in archive.get("feedback", [])[-6:]:
                lines.append(f"- {feedback['dimension']}：{feedback['observation']}；下一练习：{feedback['next_action']}；原话编号：{feedback['evidence_id']}")
        except (OSError, ValueError):
            pass
        temporary=folder / (uuid.uuid4().hex+".tmp")
        temporary.write_text("\n".join(lines), encoding="utf-8")
        temporary.replace(folder / "交接手记.md")
        if self.workspaces:
            visible=self.workspaces.visible(card['student_id'],card['id'])
            if visible:
                try:
                    from .readable_archive import export_readable
                except ImportError:
                    from readable_archive import export_readable
                try:
                    archive=json.loads((folder/'discussions.json').read_text('utf-8'))
                except (OSError,ValueError):
                    archive={'conversations':[],'feedback':[]}
                export_readable(visible,card,archive)
                context_archive.export(visible, card, archive, context_archive.load_notes(folder))
