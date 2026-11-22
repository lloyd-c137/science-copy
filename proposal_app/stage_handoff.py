"""One tutor write saves an explicit draft bundle; only the website confirms it."""
from copy import deepcopy
try:
    from . import research_service as service, research_store as store, workflow, quality_records
except ImportError:
    import research_service as service, research_store as store, workflow, quality_records


def save(c,card,body,user,messages):
    n=card['current_step']
    if body.get('step')!=n: raise store.Conflict('只能整理当前阶段的交接。')
    allowed={'step','data','objects','links','proposals','activate_link_ids','version','requirement_version','request_id'}
    if set(body)-allowed: raise ValueError('交接只保存草稿，不接受确认或完成参数。')
    if user.get('actor_type') == 'ai': quality_records.guard_agent_changes(card,'progress',body)
    if body.get('objects') or body.get('links'):
        service._save_objects(c,card,body,user,messages)
    service.enrich(c,card)
    def append(proposal):
        for old in card['quality']['records']:
            if old['id'] in proposal['supersedes_proposals']:
                old.update(status='superseded',superseded_by=proposal['id'])
        card['quality']['records'].append(proposal)
    for record in body.get('proposals',[]):
        proposal=service.object_proposal(card,{'record':record},user,student_messages=messages)
        append(proposal)
    ids=body.get('activate_link_ids',[])
    if not isinstance(ids,list) or len(ids)!=len(set(ids)): raise ValueError('请明确列出本次待本人确认的关联ID。')
    links={l['id']:l for l in card['research']['links']}
    grouped={}
    for lid in ids:
        if lid not in links or links[lid]['status']!='draft': raise ValueError('待确认关联不存在或已经处理。')
        grouped.setdefault(links[lid]['to_ref']['id'],[]).append(lid)
    for oid,lids in grouped.items():
        prior=[p for p in card['quality']['records'] if p.get('target_object_id')==oid and p.get('status')=='pending']
        if len(prior)>1: raise ValueError('同一成果有多个候选，请明确替代关系。')
        obj=store.get(c,card['id'],oid)
        record=deepcopy(prior[0]) if prior else dict(target_object_id=oid,expected_revision=obj['revision'],text='核对已讨论的成果与关联',reason='；'.join(links[l]['reason'] for l in lids),content_patch={'set':{},'remove':[]},proposed_status='confirmed')
        changes=record.setdefault('relation_changes',{})
        changes['activate_draft_ids']=list(dict.fromkeys(changes.get('activate_draft_ids',[])+lids))
        record['supersedes_proposals']=[p['id'] for p in prior]
        proposal=service.object_proposal(card,{'record':record},user,student_messages=messages)
        append(proposal)
    data=body.get('data',{})
    if not isinstance(data,dict): raise ValueError('data须为阶段资料对象。')
    workflow.save_progress(card,dict(workflow_version=workflow.VERSION,step=n,data=data or card['steps'][n-1]['data'] or {'summary':''},complete=False,confirmed=False),user)
    if n == 1 and 'direction' in data:
        selected = workflow.direction_object_ids(data)
        unselected = {obj['id'] for obj in card['research']['objects']
                      if obj['kind'] in workflow.A_DIRECTION_KINDS and obj['id'] not in selected}
        for proposal in card['quality']['records']:
            if proposal.get('kind') == 'proposal' and proposal.get('status') == 'pending' and proposal.get('target_object_id') in unselected:
                proposal.update(status='superseded', superseded_reason='未列入本次已选方向，保留在探索记录。')
    # Incomplete semantic fields remain visible in the receipt, never fabricated.
    return card
