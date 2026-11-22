"""Immutable, evidence-bound proposal versions."""
from copy import deepcopy
try:
    from . import research_store as store
except ImportError:
    import research_store as store
CHAPTERS=('background','literature','question','method','validation','limits','references')
def create(c,card,body,user):
    if not isinstance(body.get('evidence_refs',[]),list): raise ValueError('evidence_refs 须为引用列表。')
    chapters=body.get('chapters')
    if not isinstance(chapters,dict) or any(not isinstance(chapters.get(k),str) or not chapters[k].strip() for k in CHAPTERS): raise ValueError('请完整保存 Proposal 七个章节。')
    refs=body.get('object_refs')
    if not isinstance(refs,list) or not refs: raise ValueError('Proposal 须引用固定对象版本。')
    for ref in refs:
        if not isinstance(ref,dict) or ref.get('type')!='object' or type(ref.get('revision')) is not int or ref.get('project_id',card['id'])!=card['id']: raise ValueError('Proposal 引用须为本项目固定对象版本。')
        obj=store.get(c,card['id'],ref.get('id'),ref.get('revision'))
        current=store.get(c,card['id'],ref.get('id'))
        if obj['revision']!=current['revision'] or current.get('needs_review') or obj['status']!='confirmed': raise ValueError('Proposal 引用必须是已确认、已复核的当前对象。')
    kinds={store.get(c,card['id'],r['id'])['kind'] for r in refs}
    if not {'problem','rq','method'}.issubset(kinds): raise ValueError('Proposal 至少引用 Problem、RQ 和 Method。')
    oid=body.get('id') or store.uid('PV')
    if not isinstance(oid,str) or not oid.strip() or len(oid)>100: raise ValueError('Proposal ID 无效。')
    if type(body.get('expected_revision',0)) is not int: raise ValueError('expected_revision 须为整数。')
    old=[d for d in store.rows(c,'deliverable_versions',card['id']) if d['id']==oid]
    revision=max([d['revision'] for d in old],default=0)+1
    if body.get('expected_revision',0)!=revision-1: raise store.Conflict('Proposal 版本已变化。')
    decisions=[r['id'] for r in card.get('quality',{}).get('records',[]) if r.get('kind')=='proposal' and r.get('status')=='accepted' and r.get('target_object_id') in {x['id'] for x in refs}]
    evidence_ids={r['snapshot_id'] for link in store.rows(c,'research_links',card['id']) if link.get('status')=='confirmed' and link['to_ref']['id'] in {x['id'] for x in refs} for r in [link['from_ref'],*link.get('evidence_refs',[])] if 'snapshot_id' in r}
    # Capture the actual comparison sources and object provenance used by this plan.
    for r in body.get('evidence_refs',[]):
        evidence_ids.add(store.snapshot(c,card,r)['snapshot_id'])
    for object_ref in refs:
        obj=store.get(c,card['id'],object_ref['id'],object_ref['revision'])
        for r in obj.get('origin_refs',[])+obj['content'].get('evidence_refs',[]):
            if r.get('type')!='object': evidence_ids.add(store.snapshot(c,card,r)['snapshot_id'])
    material_ids={m['id'] for m in card.get('materials',[])}
    for comparison in card.get('steps',[{}, {}, {}])[2].get('data',{}).get('source_comparisons',[]):
        rid=comparison['reference']
        evidence_ids.add(store.snapshot(c,card,comparison.get('source_snapshot_ref') or {'type':'source' if rid in material_ids else 'file','id':rid})['snapshot_id'])
    snapshots=[s for s in store.rows(c,'research_reference_snapshots',card['id']) if s['id'] in evidence_ids]
    row=dict(id=oid,project_id=card['id'],revision=revision,status='prepared',chapters=deepcopy(chapters),object_refs=deepcopy(refs),evidence_snapshots=snapshots,quality_decision_refs=decisions,activity_version=card['activity']['version'],created_by=user,created_at=store.now())
    c.execute('INSERT INTO deliverable_versions VALUES(?,?,?,?)',(card['id'],oid,revision,store.dump(row)))
    store.event(c,card['id'],'deliverable_created',user,deliverable_ref={'id':oid,'revision':revision})
    card.setdefault('research_state',{})['selected_deliverable']={'id':oid,'revision':revision}
    prior_defenses={o['id'] for o in store.rows(c,'research_objects',card['id']) if o['kind']=='defense'}
    for proposal in card.get('quality',{}).get('records',[]):
        if proposal.get('kind')=='proposal' and proposal.get('status')=='pending' and proposal.get('target_object_id') in prior_defenses:
            proposal.update(status='superseded',superseded_reason='新版开题计划需对应本稿的答辩。')
    if card.get('steps'):
        for st in card['steps'][4:]:
            data=st['data']
            for key in ('deliverable_ref','defense_refs','summary_refs','revision_notes'):
                data.pop(key,None)
            if data.get('summary_origin')=='program_reference':
                data.pop('summary',None)
                data.pop('summary_origin',None)
    if card.get('steps') and card['steps'][4]['status']=='complete':
        for st in card['steps'][4:]: st['status']='pending';st['cycle']=st.get('cycle',1)+1
        card['steps'][4]['status']='active';card['current_step']=5;card['status']='active'
        card.pop('milestone',None);card['next_action']='请针对新 Proposal 版本核对答辩后再提交。'
    return row
