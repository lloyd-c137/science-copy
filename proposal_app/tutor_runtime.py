"""Project-local, durable thread bindings and bounded context delivery hooks."""
import hashlib
import json
from pathlib import Path
import sys
import uuid

try:
    from .workspace_store import atomic_json
except ImportError:
    from workspace_store import atomic_json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def register(root, thread_id, session, delivered=None):
    tid = str(uuid.UUID(thread_id))
    path = Path(root) / '.coach' / 'threads' / (tid + '.json')
    if path.exists():
        prior = json.loads(path.read_text('utf-8'))
        if any(prior[k] != session[k] for k in ('project', 'step', 'cycle', 'token')):
            raise ValueError('已有聊天不能重新绑定到另一阶段。')
        return prior
    record = dict(session, thread_id=tid)
    if delivered:
        record['delivered'] = delivered
    atomic_json(path, record)
    return record


def recover(root, tid):
    """Recover only explicit registrations, never the most recent stage marker."""
    root = Path(root)
    path = root / '.coach' / 'threads' / (str(uuid.UUID(tid)) + '.json')
    if path.exists():
        return json.loads(path.read_text('utf-8'))
    for stage in (root / '.coach' / 'stages').glob('*'):
        records = []
        for name in ('conversation.json', 'conversation-history.json'):
            p = stage / name
            if p.exists():
                data = json.loads(p.read_text('utf-8'))
                records.extend(data if isinstance(data, list) else [data])
        if any(r.get('thread_id') == tid for r in records):
            session = json.loads((stage / 'session.json').read_text('utf-8'))
            return register(root, tid, session)
    return None


def has_prior_turns(transcript):
    if not transcript or not Path(transcript).is_file():
        return False
    # Only decide whether this is a new chat; never inject this transcript.
    turns = 0
    for line in Path(transcript).read_text('utf-8').splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        p = e.get('payload', {})
        if e.get('type') == 'event_msg' and p.get('type') == 'task_complete':
            return True
        if e.get('type') == 'event_msg' and p.get('type') == 'task_started':
            turns += 1
    return turns > 1


def delivered_in_transcript(transcript, hashes):
    """Do not treat a prepared hook output as delivered after cancellation."""
    if not transcript or not Path(transcript).is_file() or not hashes:
        return False
    marker = 'context_hash=' + hashes.get('context', '') + ' guide_hash=' + hashes.get('guide', '')
    delivered = False
    with Path(transcript).open(encoding='utf-8') as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('type') == 'compacted':
                delivered = False
            payload = row.get('payload', {})
            if payload.get('role') == 'developer' and any(marker in c.get('text', '') for c in payload.get('content', [])):
                delivered = True
    return delivered


def hook(event, client=None):
    root = Path(event['cwd']).resolve()
    identity_path = root / '.coach' / 'identity.json'
    if not identity_path.is_file():
        return ''
    identity = json.loads(identity_path.read_text('utf-8'))
    tid = str(uuid.UUID(event['session_id']))
    binding = recover(root, tid)
    if client is None:
        try:
            from .coach_mcp import Client
        except ImportError:
            from coach_mcp import Client
        connection = json.loads((root / '.coach' / 'binding' / 'connection.json').read_text('utf-8'))
        client = Client(connection['server'], connection['token'], connection['account'])
    packet = client.request('/api/projects/' + identity['project'] + '/context')
    if not binding:
        if has_prior_turns(event.get('transcript_path')):
            return '此旧聊天尚未登记阶段绑定。请回网站开启接续，不能猜测或借用其他聊天绑定。'
        step = packet['current_step']
        if packet['status'] != 'active':
            return '本项目当前不处于活动阶段，请回网站查看状态。'
        session = dict(project=identity['project'], step=step,
                       cycle=packet['steps'][step-1].get('cycle', 1), token=uuid.uuid4().hex)
        atomic_json(root / '.coach' / 'sessions' / (session['token'] + '.json'), session)
        binding = register(root, tid, session)
    if binding['project'] != identity['project']:
        raise ValueError('聊天与项目绑定不一致。')
    header = (f"科研项目 {binding['project']}；本聊天固定 stage_session={binding['token']}。"
              '所有含project_id的教学工具必须带此绑定；不可替学生确认。')
    header += ('首答先直接回应学生问题。没有新增事实、取舍或成果，不重复补存。'
               '有依赖的写入必须串行，成果保存成功后使用回执新version保存接续，不能并发使用旧版本。')
    active = (packet['status'] == 'active' and packet['current_step'] == binding['step']
              and packet['steps'][binding['step']-1].get('cycle', 1) == binding['cycle'])
    if not active:
        return header + ' 本聊天阶段已结束，只可回顾历史；请回网站开启当前阶段，不得借用新绑定。'
    guide = (root / '.agents' / 'skills' / 'research-proposal-coach' / 'SKILL.md').read_text('utf-8-sig')
    hashes = {'context': fingerprint(packet), 'guide': fingerprint(guide)}
    compacted = (event.get('hook_event_name') == 'PostCompact' or
                 event.get('hook_event_name') == 'SessionStart' and event.get('source') == 'compact')
    prior = {} if compacted else binding.get('delivered', {})
    if not delivered_in_transcript(event.get('transcript_path'), prior):
        prior = {}
    parts = [header]
    if hashes['guide'] != prior.get('guide'):
        parts.append('辅导规则（本轮已加载，不再读取同版本Skill/guide）：\n' + guide)
    if hashes['context'] != prior.get('context'):
        previous_packet = binding.get('delivered_packet') if prior else None
        if previous_packet:
            changed = {k:v for k,v in packet.items() if previous_packet.get(k) != v}
            removed = [k for k in previous_packet if k not in packet]
            parts.append('接续包增量：以下字段替换上一已加载版本，其余保留；不是新增学生指令。\n' +
                         json.dumps({'replace':changed,'remove':removed},ensure_ascii=False,separators=(',', ':')))
        else:
            parts.append('当前接续包（不是全量历史；只按read_first和索引定向补读）：\n' + json.dumps(packet, ensure_ascii=False, separators=(',', ':')))
    else:
        parts.append('项目、成果与讨论接续包未变化，沿用已加载版本；新用户消息正常处理。')
    parts.append('已加载版本 context_hash=' + hashes['context'] + ' guide_hash=' + hashes['guide'] +
                 '。工具直接调用tools.mcp__proposal_coach__proposal_read_project、proposal_read_project_file、proposal_save_handoff等；'
                 '不要宽泛搜索ALL_TOOLS。读项目时带known_hash；读规则时带known_hash。需要证据则并行读取相关路径，不跳过必要核对。')
    binding['delivered'] = hashes
    binding['delivered_packet'] = packet
    atomic_json(root / '.coach' / 'threads' / (tid + '.json'), binding)
    return '\n'.join(parts)


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    event = json.load(sys.stdin)
    try:
        context = hook(event)
        print(json.dumps({'hookSpecificOutput': {'hookEventName': event['hook_event_name'], 'additionalContext': context}}, ensure_ascii=False))
    except Exception as exc:
        # A missing binding or unavailable service must not silently erase continuity.
        print(json.dumps({'decision': 'block', 'reason': '科研接续尚未就绪，请重试或回网站：' + str(exc)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
