"""Bounded launch packets and lossless, individually addressable local sources.

No semantic summarization here: continuity entries are authored by the tutor.
"""
import hashlib
import json
from pathlib import Path

try:
    from . import readable_archive as files
except ImportError:
    import readable_archive as files

LIMIT = 10000
PREFIX = '研究过程/导师上下文'


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def messages(archive):
    return [dict(m, thread_id=c['thread_id'], step=c.get('step'))
            for c in archive.get('conversations', []) for m in c.get('messages', [])]


def load_notes(folder):
    path = Path(folder) / 'continuity.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else {'revision': 0, 'entries': [], 'coverage': {}, 'requests': {}}


def update_notes(prior, body, archive, card):
    """Validate exact source quotations, concurrency and explicit supersession."""
    key = body.get('request_id')
    if not isinstance(key, str) or not key or len(key) > 100:
        raise ValueError('接续记录需要有效request_id。')
    signature = digest(body)
    if key in prior.get('requests', {}):
        if prior['requests'][key] != signature:
            raise ValueError('request_id已用于其他接续记录。')
        return prior
    if body.get('revision') != prior['revision'] or body.get('project_version') != card.get('version'):
        raise ValueError('接续记录或成果版本已改变，请重读后保存。')
    raw = {m['id']: m for m in messages(archive)}
    entries = body.get('entries')
    coverage = body.get('coverage')
    if not isinstance(entries, list) or not entries or len(entries) > 40 or not isinstance(coverage, dict):
        raise ValueError('需要1至40条有原文依据的接续记录及coverage。')
    result = json.loads(encode(prior))
    known = {e['id']: e for e in result['entries']}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get('kind') not in ('consensus', 'decision', 'open'):
            raise ValueError('接续类型应为consensus、decision或open。')
        if not isinstance(entry.get('text'), str) or not 1 <= len(entry['text']) <= 1000:
            raise ValueError('每条接续信息需要1至1000字符完整表述。')
        sources = entry.get('sources')
        if not isinstance(sources, list) or not sources or len(sources) > 12:
            raise ValueError('每条接续信息须有原文依据。')
        for source in sources:
            if not isinstance(source, dict) or source.get('message_id') not in raw:
                raise ValueError('依据消息不属于当前项目已同步的讨论。')
            quote = source.get('quote')
            if not isinstance(quote, str) or not quote.strip() or len(quote) > 2000 or quote not in raw[source['message_id']]['text']:
                raise ValueError('依据引文必须逐字存在于所引用消息。')
        replaces = entry.get('supersedes', [])
        if not isinstance(replaces, list) or any(x not in known for x in replaces):
            raise ValueError('supersedes必须引用已有接续条目；不能静默覆盖历史取舍。')
        row = dict(id='N' + digest([key, i])[:14], kind=entry['kind'], text=entry['text'],
                   sources=sources, supersedes=replaces, step=card.get('current_step'), project_version=card.get('version'))
        result['entries'].append(row)
        known[row['id']] = row
    for tid, end_id in coverage.items():
        conversation = next((c for c in archive.get('conversations', []) if c['thread_id'] == tid), None)
        if not conversation or end_id not in [m['id'] for m in conversation['messages']]:
            raise ValueError('coverage必须指向当前项目对话中的消息。')
        seq = conversation['messages']
        stop = next(i for i, m in enumerate(seq) if m['id'] == end_id)
        covered = {m['id']: digest(m) for m in seq[:stop+1]}
        result['coverage'].update(covered)
    result['revision'] += 1
    result['requests'][key] = signature
    return result


def active_notes(notes):
    retired = {x for e in notes['entries'] for x in e.get('supersedes', [])}
    return [e for e in notes['entries'] if e['id'] not in retired]


def export(root, card, archive, notes):
    """Write immutable individual sources, then publish the directory last.

    Card fields can be reconstructed exactly using the returned catalog. No
    aggregate full-project file is offered as the default read entry point.
    """
    with files._LOCK:
        manifest = files._load(root)
        catalog = {}
        groups = {}

        def write(key, preferred, content):
            previous = manifest.get(key)
            if previous:
                path = files._path(root, previous)
                if path.is_file() and not path.is_symlink() and path.read_text('utf8') == content:
                    return previous
            return files._write(root, manifest, key, preferred, content)

        def put(group, locator, value):
            hashed = digest(value)
            path = write('context:doc:' + digest([locator, hashed]),
                                f'{PREFIX}/资料/{digest(locator)[:16]}-{hashed[:16]}.json', encode(value))
            catalog[locator] = path
            label = value.get('id', '') if isinstance(value, dict) else ''
            content = value.get('content', value) if isinstance(value, dict) else {}
            title = next((content[k] for k in ('title', 'puzzle', 'wording', 'text', 'observation', 'explanation', 'query') if content.get(k)), '') if isinstance(content, dict) else ''
            groups.setdefault(group, []).append({'key': locator, 'id': label, 'label': str(title)[:100],
                                                  'status': value.get('status') if isinstance(value, dict) else None, 'path': path})

        for key, value in card.items():
            if key.startswith('_'):
                continue
            parts = value.items() if key in ('research', 'quality') and isinstance(value, dict) else [(None, value)]
            for subkey, content in parts:
                group = key + ('.' + subkey if subkey else '')
                if isinstance(content, list) and content:
                    for i, row in enumerate(content):
                        put(group, f'{group}/{i}', row)
                else:
                    put(group, group, content)
        for c in archive.get('conversations', []):
            put('discussions', 'thread/' + c['thread_id'], {k:v for k,v in c.items() if k != 'messages'})
            for i, m in enumerate(c.get('messages', [])):
                put('discussions', 'message/' + m['id'], dict(m, thread_id=c['thread_id'], step=c.get('step'), position=i))
        for key, value in archive.items():
            if key != 'conversations':
                put('discussion_metadata', 'archive/' + key, value)
        for entry in notes['entries']:
            put('continuity', 'note/' + entry['id'], entry)
        put('continuity_coverage', 'coverage', {'revision': notes['revision'], 'covered_messages': notes['coverage']})
        indexes = {}
        for group, rows in groups.items():
            next_path = None
            for start in reversed(range(0, len(rows), 20)):
                page = {'category': group, 'total': len(rows), 'entries': rows[start:start+20], 'next': next_path}
                next_path = write('context:index:' + digest(page),
                                        f'{PREFIX}/索引/{digest(page)[:24]}.json', encode(page))
            indexes[group] = next_path
        index = {'project_id': card.get('id'), 'version': card.get('version'), 'continuity_revision': notes['revision'],
                 'read': '只读取当前问题相关类别和条目；next为索引下一页。资料按read_project_file的next_offset分页，禁止遍历展开全部上下文。',
                 'categories': indexes}
        root_index = write('context:root', f'{PREFIX}/INDEX.md', '# 导师资料索引\n\n' + encode(index))
        paths = {'index': root_index, 'categories': indexes, 'catalog': catalog}
        write('context:brief', f'{PREFIX}/接续简报.json', encode(packet(card, archive, notes, paths)))
        files._save(root, manifest)
        return paths


def packet(card, archive=None, notes=None, paths=None):
    archive = archive or {}
    notes = notes or {'revision': 0, 'entries': [], 'coverage': {}}
    paths = paths or {'index': PREFIX + '/INDEX.md', 'categories': {}, 'catalog': {}}
    catalog = paths['catalog']
    out = {k: card.get(k) for k in ('id', 'version', 'current_step', 'status', 'workflow_version')}
    out['requirement_version'] = card.get('activity', {}).get('version')
    out['activity'] = {'version': out['requirement_version']}
    out['steps'] = [{'number': s.get('number'), 'cycle': s.get('cycle', 1)} for s in card.get('steps', [])]
    out['index'] = paths['index']
    out['read_policy'] = '判断科学有效性、引用学生原话或改变已有取舍时，核对必要的原文及对象版本。recent_messages已含原文时直接使用。普通草稿用工具schema和当前版本保存；特殊阶段条件不清楚时才按read_first定向查契约，同版本无需重读。'
    out['continuity_revision'] = notes['revision']

    def section(name, rows, budget):
        selected = []
        for row in rows:
            if len(encode(selected + [row])) > budget:
                continue
            selected.append(row)
        out[name] = {'items': selected, 'omitted': len(rows) - len(selected)}

    section('task', [{'activity': card.get('teaching_brief', {}).get('purpose'),
                      'focus_object_id': card.get('teaching_brief', {}).get('focus_object_id')},
                     {'title': card.get('title')}, {'next_action': card.get('next_action')}, {'budget': card.get('budget')}], 600)
    objects = card.get('research', {}).get('objects', [])
    priorities = {1: ('topic', 'curiosity', 'question'), 2: ('problem', 'question', 'topic'),
                  3: ('rq', 'hypothesis', 'problem'), 4: ('framework', 'check', 'rq'),
                  5: ('proposal', 'framework', 'rq'), 6: ('defense', 'proposal', 'rq')}.get(card.get('current_step'), ())
    focus = card.get('teaching_brief', {}).get('focus_object_id')
    candidates = []
    for i, obj in enumerate(objects):
        content = obj.get('content', {})
        selected = {}
        # Verbatim fields only; never infer the main idea from arbitrary prose.
        for key in ('population_or_object', 'question', 'puzzle', 'wording', 'title', 'explanation', 'mechanism', 'prediction', 'scope', 'grouping_reason', 'observation', 'exploration_reason'):
            if key in content and len(encode(dict(selected, **{key: content[key]}))) <= 650:
                selected[key] = content[key]
        if not selected:
            continue
        value = {k: obj.get(k) for k in ('id', 'kind', 'status', 'revision', 'needs_review')}
        value.update(content=selected, omitted_fields=len(content)-len(selected), path=catalog.get(f'research.objects/{i}'))
        priority = -1 if obj.get('id') == focus else priorities.index(obj.get('kind')) if obj.get('kind') in priorities else 99
        candidates.append((priority, obj.get('updated_at', ''), value))
    candidates.sort(key=lambda row: row[1], reverse=True)
    candidates.sort(key=lambda row: row[0])
    section('current_results', [row[2] for row in candidates], 1800)
    out['current_results']['omitted'] = len(objects) - len(out['current_results']['items'])
    for kind, budget in [('consensus', 900), ('decision', 1400), ('open', 900)]:
        entries = [e for e in active_notes(notes) if e['kind'] == kind]
        entries.sort(key=lambda e: e.get('step') == card.get('current_step'), reverse=True)
        section(kind, [dict(id=e['id'], text=e['text'], path=catalog.get('note/' + e['id'])) for e in entries], budget)
    raw = messages(archive)
    section('recent_messages', [dict(id=m['id'], role=m['role'], text=m['text'], path=catalog.get('message/' + m['id'])) for m in reversed(raw[-6:])], 1200)
    uncovered = [m for c in archive.get('conversations', []) for m in c.get('messages', [])
                 if notes.get('coverage', {}).get(m['id']) != digest(m)]
    out['coverage'] = {'discussion_hash': digest(raw), 'uncovered_count': len(uncovered), 'first_uncovered': uncovered[0]['id'] if uncovered else None,
                       'sync': archive.get('sync', {}).get('status'), 'status': 'needs_reading' if uncovered else 'covered',
                       'project_changed_since_notes': bool(notes['entries']) and max(e.get('project_version', 0) for e in notes['entries']) != card.get('version')}
    section('source_indexes', [{'category': k, 'path': paths['categories'][k]} for k in
                              ('comments', 'quality.records', 'continuity', 'discussions', 'research.objects', 'research.contract', 'research.review_readiness', 'steps')
                              if k in paths['categories']], 1100)
    # Website-authored changes are not necessarily present in chat messages or
    # tutor-authored notes. Preserve their exact text, or require the original.
    website_rows = []
    for i, comment in enumerate(card.get('comments', [])):
        if comment.get('role') == 'teacher':
            website_rows.append((comment.get('created', ''), 'comments/'+str(i),
                {'kind':'teacher_comment', **{k:comment.get(k) for k in ('id','step','text')},
                 'path':catalog.get('comments/'+str(i))}))
    for i, record in enumerate(card.get('quality', {}).get('records', [])):
        if record.get('decision_reason'):
            website_rows.append((record.get('decided_at',record.get('created','')), 'quality.records/'+str(i),
                {'kind':'student_decision', **{k:record.get(k) for k in ('id','step','status','text','decision_reason','target_object_id')},
                 'path':catalog.get('quality.records/'+str(i))}))
    website_rows.sort(key=lambda row:row[0],reverse=True)
    selected_updates=[]
    for _, locator, value in website_rows[:4]:
        if len(encode(selected_updates+[value])) > 950:
            value={k:value[k] for k in ('kind','id','step','path')}
            value['needs_read']=True
        if len(encode(selected_updates+[value])) <= 950:
            selected_updates.append(value)
    out['website_updates']={'items':selected_updates,'omitted':len(website_rows)-len(selected_updates)}
    out['read_policy'] += ' 网站最新对象与本人选择优先于旧接续笔记；website_updates中needs_read为true时必须补读原文，不能仅凭版本号猜测变化。'
    # Direct addresses eliminate index-discovery turns. Selection uses existing
    # explicit links only; this is not a semantic summary or a coverage update.
    reads = []
    supplied_messages = {m['id'] for m in out['recent_messages']['items']}
    def source(locator, reason):
        if locator.startswith('message/') and locator.removeprefix('message/') in supplied_messages:
            return
        path = catalog.get(locator)
        if path and not any(r['path'] == path for r in reads):
            reads.append({'path': path, 'reason': reason})
    for _, locator, value in website_rows[:4]:
        if not any(row.get('path') == value.get('path') and not row.get('needs_read') for row in selected_updates):
            source(locator, '网站上的老师批注或学生选择原文')
    for m in reversed(uncovered[-6:]):
        if m['id'] in supplied_messages:
            continue
        source('message/' + m['id'], '未覆盖的新消息')
    for i, record in reversed(list(enumerate(card.get('quality', {}).get('records', [])))):
        if record.get('kind') == 'support' and record.get('step') == card.get('current_step'):
            source('quality.records/' + str(i), '当前阶段最近的教学支持原文')
            break
    for entry in reversed(active_notes(notes)):
        if entry['kind'] == 'decision' and entry.get('step') == card.get('current_step'):
            for ref in entry.get('sources', []):
                source('message/' + ref['message_id'], '当前阶段最近取舍的原文依据')
            break
    # Reserve a bounded navigation budget before adding optional older decisions.
    out['read_first'] = {'items': [], 'omitted': len(reads)}
    for row in reads:
        if len(encode(out)) + len(encode(row)) < 9400 and len(encode(out['read_first']['items'] + [row])) <= 1700:
            out['read_first']['items'].append(row)
            out['read_first']['omitted'] -= 1
    # Flexible reserve: full relevant decisions first, then uncovered recent text.
    included = {e['id'] for e in out['decision']['items']}
    for e in active_notes(notes):
        if e['kind'] == 'decision' and e['id'] not in included:
            row = dict(id=e['id'], text=e['text'], path=catalog.get('note/' + e['id']))
            if len(encode(out)) + len(encode(row)) < 9500:
                out['decision']['items'].append(row)
                out['decision']['omitted'] -= 1
    # Every omission has the root index; no clipping of a semantic statement.
    if len(encode(out)) > LIMIT:
        raise ValueError('启动上下文超过10000字符，拒绝发送。')
    return out


def receipt(result):
    if not isinstance(result, dict) or 'current_step' not in result or 'version' not in result:
        return result
    kept = {k: result[k] for k in ('id', 'result_id', 'version', 'current_step', 'status', 'return_url', 'receipt') if k in result}
    readiness = result.get('research', {}).get('review_readiness')
    if readiness:
        kept['handoff'] = {'prepared': readiness['prepared'], 'step': readiness['step'],
                           'blocking': readiness.get('execution_check', {}).get('detail', ''),
                           'missing': [dict(label=i['label'],detail=i.get('detail','')) for i in readiness['items'] if i['status'] in ('missing','incomplete','recheck')]}
    kept['next_read'] = 'proposal_read_project返回限长启动包；完整成果按本地索引逐项读取。'
    if len(encode(kept)) > 6000:
        kept['receipt'] = {k: result.get('receipt', {}).get(k) for k in ('saved', 'stage_complete', 'complete')}
    return kept
