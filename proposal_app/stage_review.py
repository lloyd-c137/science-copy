"""One website gesture saves personal edits and confirms a stage atomically."""
from copy import deepcopy
import sqlite3
try:
    from . import research_schema as schema, research_store as store, workflow, quality_records
except ImportError:
    import research_schema as schema, research_store as store, workflow, quality_records

EDITABLE = {
    'curiosity': ['observation', 'why_care'], 'topic': ['title', 'exploration_reason'],
    'question': ['wording', 'importance'], 'problem': ['puzzle', 'grouping_reason', 'candidate_explanations'],
    'rq': ['question', 'population_or_object', 'conditions', 'scope', 'promised_conclusion'],
    'hypothesis': ['explanation', 'prediction', 'alternatives', 'scope'],
    'method': ['procedure', 'variables_or_concepts', 'analysis', 'feasibility', 'limits'], 'defense': ['revision_actions'],
}
STAGE_FIELDS = {1: ['selection_reason', 'technical_plan', 'first_validation'],
                4: ['budget', 'critical_validation', 'learning_value', 'practical_value', 'research_value']}

def targets(card):
    n = card['current_step']
    pending = [r for r in card.get('quality', {}).get('records', []) if r.get('kind') == 'proposal' and r.get('status') == 'pending']
    ids = {r.get('target_object_id') for r in pending}
    kinds = set(workflow.REQUIRED_OBJECTS[n]) | ({'topic'} if n == 1 else set())
    return [o for o in workflow.stage_objects(card, n) if o['status'] not in ('abandoned', 'superseded') and (o['kind'] in kinds or o['id'] in ids)], pending

def apply(c, card, body, user, messages):
    guarded = card.get('_review_preview')
    card['_review_preview'] = True
    try:
        return _apply(c, card, body, user, messages)
    finally:
        if not guarded: card.pop('_review_preview', None)


def preview(c, card, messages=None):
    """Execute the same transaction in memory, without taking a database write lock."""
    work = deepcopy(card)
    work['_review_preview'] = True
    memory = sqlite3.connect(':memory:')
    store.init_schema(memory)
    try:
        for table in ('research_objects','object_revisions','research_links','research_events','research_reference_snapshots','deliverable_versions'):
            rows=c.execute('SELECT * FROM '+table+' WHERE project_id=? ORDER BY rowid',(card['id'],)).fetchall()
            if rows: memory.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
        apply(memory, work, dict(step=card['current_step'], confirmed=True, complete=True),
              dict(id=card['student_id'], role='student', name='本人核对'), messages or {})
        return dict(prepared=True, detail='')
    except (ValueError, store.Conflict) as error:
        return dict(prepared=False, detail=str(error))
    finally:
        memory.close()


def _apply(c, card, body, user, messages):
    # Called inside research_service.mutate's savepoint, including stage completion.
    try:
        from . import research_service as service
    except ImportError:
        import research_service as service
    n = card['current_step']
    if body.get('step') != n or body.get('confirmed') is not True:
        raise store.Conflict('阶段已变化，请重新打开成果。')
    objects, pending = targets(card)
    edits = body.get('edits', [])
    if not isinstance(edits, list): raise ValueError('修改格式无效。')
    by_id = {o['id']: o for o in objects}
    edited = {}
    for entry in edits:
        if not isinstance(entry, dict): raise ValueError('修改格式无效。')
        oid = entry.get('id'); obj = by_id.get(oid)
        if not obj or oid in edited or entry.get('expected_revision') != obj['revision']:
            raise store.Conflict('成果已更新，请重新打开后修改。')
        patch = entry.get('set')
        if not isinstance(patch, dict) or set(patch) - set(EDITABLE.get(obj['kind'], [])):
            raise ValueError('只能修改本页的关键内容。')
        edited[oid] = patch
    stage_data = body.get('data', {})
    if not isinstance(stage_data, dict) or set(stage_data) - set(STAGE_FIELDS.get(n, [])):
        raise ValueError('阶段修改字段无效。')
    if any(not schema.text(v) for v in stage_data.values()): raise ValueError('请填写修改的内容。')
    item_only = body.get('scope') == 'item'
    if item_only:
        if body.get('complete') is True or (len(edited) != 1 if edited else not stage_data) or (edited and stage_data):
            raise ValueError('单项保存只能修改当前一项，不能提交整个阶段。')
        objects = [o for o in objects if o['id'] in edited]
        pending = [p for p in pending if p.get('target_object_id') in edited]
    for proposal in pending:
        if proposal.get('target_object_id'):
            obj = by_id.get(proposal['target_object_id'])
            if not obj or obj['revision'] != proposal['expected_revision'] or proposal['requirement_version'] != card['activity']['version']:
                raise store.Conflict('建议已更新，请导师重新整理。')
            for lid, baseline in proposal.get('relation_baselines', {}).items():
                if next((l for l in card['research']['links'] if l['id'] == lid), None) != baseline:
                    raise store.Conflict('关联已更新，请重新打开成果。')
    # The order permits content-identical confirmations to carry their references forward.
    order = ['curiosity', 'topic', 'question', 'problem', 'search', 'hypothesis', 'rq', 'method', 'check', 'defense']
    # Replacements precede their old checks; old checks become superseded in this
    # same transaction and must never be separately re-confirmed.
    def operation_order(o):
        p = next((p for p in pending if p.get('target_object_id') == o['id']), None)
        content = schema.patch(o['content'], p['content_patch']) if p else o['content']
        return order.index(o['kind']), 0 if content.get('supersedes') else 1
    for initial in sorted(objects, key=operation_order):
        oid = initial['id']; obj = store.get(c, card['id'], oid)
        if obj['status'] in ('superseded', 'abandoned'): continue
        if edited and obj.get('needs_review') and not initial.get('needs_review') and oid not in edited:
            # A substantive edit invalidates dependent judgments. Save the edit now;
            # the tutor must update those judgments, not ask for the same edit again.
            continue
        proposals = [r for r in pending if r.get('target_object_id') == oid]
        if len(proposals) > 1: raise ValueError('同一成果有多个候选，请导师先整理为明确的选择。')
        prior = proposals[0] if proposals else None
        content = schema.patch(obj['content'], prior['content_patch']) if prior else deepcopy(obj['content'])
        content.update(edited.get(oid, {}))
        if body.get('complete') is not True and oid not in edited and not prior:
            if obj.get('needs_review'): continue
            try: schema.validate(obj['kind'], content, confirmed=True)
            except ValueError: continue
        if obj['status'] == 'confirmed' and not prior and content == obj['content']:
            if obj.get('needs_review'): raise ValueError('已有内容受上游修改影响，请导师先核实。')
            continue
        if obj['kind'] == 'check':
            if initial.get('needs_review'): raise ValueError('研究方案已变化，请导师更新关键验证。')
            content['scope_refs'] = [schema.confirmation_reference(card['research']['objects'], card['research']['revisions'], r) for r in content.get('scope_refs', [])]
        reason = (prior or {}).get('reason') or card['steps'][n-1]['data'].get('summary') or '本人核对并保存阶段成果'
        p = service.object_proposal(card, {'record': dict(
            target_object_id=oid, expected_revision=obj['revision'], text='保存本人核对结果', reason=reason,
            content_patch={'set': content, 'remove': [k for k in obj['content'] if k not in content]},
            proposed_status=(prior or {}).get('proposed_status', 'confirmed'),
            relation_changes=(prior or {}).get('relation_changes', {}),
            supersedes_proposals=[prior['id']] if prior else [])}, user, student_messages=messages)
        if prior:
            row = next(r for r in card['quality']['records'] if r['id'] == prior['id'])
            row.update(status='superseded', superseded_by=p['id'])
        card['quality']['records'].append(p)
        service.decide(c, card, dict(record_id=p['id'], decision='accepted', reason=reason, confirmed=True, _stage_review=True), user, student_messages=messages)
        # Saving this edit also accepts its still-current incoming references; downstream
        # scientific checks remain invalidated and cannot be silently renewed.
        changed = store.get(c, card['id'], oid)
        if changed.get('needs_review') and changed['kind'] != 'check':
            links = [l['id'] for l in card['research']['links'] if l['status'] == 'confirmed' and l['to_ref']['id'] == oid and l.get('needs_review')]
            service.mutate(c, card, 'research-recheck', dict(object_id=oid, expected_revision=changed['revision'], reason=reason, link_ids=links), user, student_messages=messages)
    for proposal in pending:
        if not proposal.get('target_object_id'):
            quality_records.decide(card, dict(record_id=proposal['id'], decision='accepted', reason=proposal.get('reason') or '本人核对阶段成果', confirmed=True))
    data = deepcopy(card['steps'][n-1]['data']); data.update(stage_data)
    data = workflow.derived_stage_data(card, n, data)
    data['object_refs'] = [dict(type='object', id=o['id'], revision=o['revision']) for o in workflow.stage_objects(card, n) if o['kind'] in workflow.REQUIRED_OBJECTS[n] and o['status'] == 'confirmed']
    if n in (5, 6) and not item_only:
        selected = workflow.selected_deliverable(card, data)
        data['deliverable_ref'] = dict(id=selected['id'], revision=selected['revision'])
    card['_student_messages'] = messages or {}
    affected = any(o.get('needs_review') and o['status'] not in ('superseded','abandoned') and o['kind'] in workflow.REQUIRED_OBJECTS[n] for o in workflow.stage_objects(card,n))
    if body.get('complete') is True and not (edited and affected):
        workflow.save_progress(card, dict(workflow_version=workflow.VERSION, step=n, complete=True, confirmed=True, data=data), user)
        if n == 3: service.capture_reading_sources(c, card)
    else:
        card['steps'][n-1]['data'] = data
        if edited and affected: card['next_action']='修改已保存，请和导师更新受影响的研究依据。'
    card.pop('_student_messages', None)
