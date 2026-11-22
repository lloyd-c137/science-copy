"""Read visible completed Codex turns from the selected Windows project."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time


MARKER = '开题手记会话：'


@dataclass
class Turn:
    messages: dict = field(default_factory=dict)
    complete: bool = False
    aborted: bool = False


def events(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                if line.endswith('\n'):
                    raise ValueError('Codex 原文记录存在无法解析的完整行，保留待同步。') from None
                continue  # Desktop can still be flushing the final line.
            if not isinstance(row, dict):
                raise ValueError('Codex 原文记录格式已变化，保留待同步。')
            yield row


def transcript(path):
    rows = events(path)
    first = next(rows, {})
    meta = first.get('payload', {}) if first.get('type') == 'session_meta' else {}
    if not isinstance(meta, dict):
        raise ValueError('Codex 会话头格式已变化，保留待同步。')
    turns = {}
    active = None
    for row in rows:
        if row.get('type') != 'event_msg':
            continue
        event = row.get('payload', {})
        if not isinstance(event, dict):
            raise ValueError('Codex 事件格式已变化，保留待同步。')
        kind = event.get('type')
        key = event.get('turn_id')
        if key is not None and not isinstance(key, str):
            raise ValueError('Codex 轮次编号格式已变化，保留待同步。')
        if kind == 'task_started' and key:
            active = key
            turns.setdefault(key, Turn())
        elif key in turns and kind in ('task_complete', 'turn_aborted'):
            turns[key].complete = kind == 'task_complete'
            turns[key].aborted = kind == 'turn_aborted'
            if active == key:
                active = None
        elif key in turns and kind == 'item_completed' and event.get('thread_id') == meta.get('id'):
            item = event.get('item', {})
            if not isinstance(item, dict):
                raise ValueError('Codex 消息格式已变化，保留待同步。')
            if item.get('type') == 'UserMessage':
                role = 'user'
            elif item.get('type') == 'AgentMessage' and item.get('phase') == 'final_answer':
                role = 'assistant'
            else:
                continue
            content = item.get('content', [])
            if not isinstance(content, list) or any(not isinstance(part, dict) for part in content):
                raise ValueError('Codex 消息正文格式已变化，保留待同步。')
            text = '\n'.join(part['text'] for part in content
                             if part.get('type') in ('text', 'Text') and isinstance(part.get('text'), str))
            if text.strip() and isinstance(item.get('id'), str):
                turns[key].messages[item['id']] = dict(id=item['id'], role=role, text=text, time=row.get('timestamp', ''))
    return meta, turns, active


def owns_turns(turns, stage_session):
    first = next((m for turn in turns.values() for m in turn.messages.values() if m['role'] == 'user'), None)
    return bool(first and MARKER + stage_session in first['text'].splitlines())


def same_workspace(meta, workspace):
    return bool(meta.get('cwd') and os.path.normcase(str(Path(meta['cwd']).resolve())) == os.path.normcase(str(workspace)))


def find_active(sessions, workspace, stage_session, known=None):
    if known:
        candidates = [Path(known)]
    else:
        now = time.time()
        recent = [(path.stat().st_mtime, path) for path in sessions.glob('*/*/*/*.jsonl')]
        candidates = [path for stamp, path in sorted(recent, reverse=True)[:24] if now - stamp < 600]
    found = []
    for path in candidates:
        try:
            header = next(events(path), {})
            if header.get('type') != 'session_meta' or not same_workspace(header.get('payload', {}), workspace):
                continue
            meta, turns, active = transcript(path)
        except OSError:
            continue
        if active and owns_turns(turns, stage_session):
            found.append((path, meta['id'], turns, active))
    if len(found) != 1:
        raise ValueError('未找到唯一的课题聊天。请在该项目文件夹内从网页打开新讨论，保留网页给出的会话编号。')
    return found[0]
