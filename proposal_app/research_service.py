"""Research mutations coordinated inside the caller's SQLite transaction."""
from copy import deepcopy
try:
    from . import research_store as s, research_schema as schema, deliverables, workflow
except ImportError:
    import research_store as s, research_schema as schema, deliverables, workflow
Conflict=s.Conflict
init_schema=s.init_schema

def identity(user): return {k:user[k] for k in ('id','name','role','actor_type') if k in user} if isinstance(user,dict) else user

def publication_status(card, version):
    def matches(ref):
        return ref and ref.get('id')==version['id'] and ref.get('revision')==version['revision']
    reviews=card.get('prior_reviews',[])+([card['review']] if card.get('review') else [])
    review=next((r for r in reversed(reviews) if matches(r.get('deliverable_ref'))),None)
    if review: return {'approve':'approved','supplement':'supplement','redirect':'redirect'}.get(review['decision'],'submitted')
    if any(matches(r) for r in card.get('submissions',[])) or matches(card.get('submitted_deliverable')): return 'submitted'
    return version.get('status','prepared')

def enrich(c,card):
    state=deepcopy(card.get('research_state',{}))
    for key,table in [('objects','research_objects'),('revisions','object_revisions'),('links','research_links'),('events','research_events'),('deliverables','deliverable_versions'),('reference_snapshots','research_reference_snapshots')]: state[key]=s.rows(c,table,card['id'])
    import hashlib
    pools={'source':card.get('materials',[]),'file':card.get('files',[]),'claim':card.get('quality',{}).get('records',[])}
    for snapshot in state['reference_snapshots']:
        latest=next((r for r in pools.get(snapshot['ref_type'],[]) if r.get('id')==snapshot['ref_id'] or (snapshot['ref_type']=='source' and r.get('url')==snapshot['ref_id'])),None)
        snapshot['has_newer_record']=bool(latest and hashlib.sha256(s.dump(latest).encode()).hexdigest()!=snapshot['sha256'])
    state['checks']=[o for o in state['objects'] if o['kind']=='check']
    for sequence,version in enumerate(state['deliverables'],1):
        version['sequence']=sequence
        version['publication_status']=publication_status(card,version)
    state['needs_review']=[o['id'] for o in state['objects'] if o.get('needs_review')]
    questions=[o for o in state['objects'] if o['kind']=='rq' and o['status']=='confirmed']
    selected=next((o for o in questions if o['id']==state.get('focus_object_id')),None)
    selected=selected or (questions[0] if len(questions)==1 else None)
    card['title']=selected['content']['question'] if selected else '正在探索的方向'
    card['tutor_mode']=state.get('tutor_mode',card.get('tutor_mode','observation'))
    state['contract']={'workflow_version':'tanyue-v1','object_update':{'id':'object id','expected_revision':1,'content_patch':{'set':{},'remove':[]}},'proposal':{'kind':'proposal','record':{'text':'建议','reason':'理由','target_object_id':'object id','expected_revision':1,'content_patch':{'set':{},'remove':[]},'proposed_status':'confirmed','relation_changes':{'activate_draft_ids':[],'retire_link_ids':[]}}},'progress':{'workflow_version':'tanyue-v1','step':1,'complete':False,'confirmed':False,'data':{'summary':'待本人核对的本轮小结'}},'stages':{'A':'curiosity/question + selection_reason','B':'problem + groups_into','C':'search/rq/hypothesis + frames/explains + source_comparisons (reference,location,student_message_ref,supports,cannot_claim,question_impact,reading_scope), two independent sources','D':'method/check + operationalized_by + learning_value/practical_value/research_value/budget/critical_validation','E':'save Proposal first; defense.content.deliverable_ref must match selected {id,revision}, with actual answer_ref' ,'F':'website final submit fixed deliverable_ref'},'deliverable':{'chapters':dict.fromkeys(deliverables.CHAPTERS,''),'object_refs':[]},'recheck':{'object_id':'object id','expected_revision':1,'reason':'本人复核理由','link_ids':[]}}
    state['contract']['object_types']={kind:{'required_on_confirmation':fields} for kind,fields in schema.REQUIRED.items()}
    state['contract']['proposal']['record']['supersedes_proposals']=['可选：明确替代同一对象尚未决定的旧建议ID，保留旧记录']
    state['contract']['object_save']={'objects':[{'kind':'question','expected_revision':0,'content':{}}], 'links':[{'id':'client-generated unique link id (optional)', 'from_ref':{'type':'file','id':'registered material id'}, 'to_ref':{'type':'object','id':'target object id','revision':1}, 'relation':'limits', 'reason':'what this evidence changes or cannot support', 'evidence_refs':[]}]}
    state['contract']['search_save']={'content':{'query':'实际检索式','channel':'实际渠道','searched_at':'实际日期','selection_reason':'选排依据','term_change_reason':'改词原因；未改则说明','understanding_change':'理解变化或未发生变化','reading_scope':'full|abstract|excerpt|not_read','result_count':None}}
    state['contract']['check_save']={'content':{'scope_refs':[{'type':'object','id':kind+' id','revision':1} for kind in ('rq','hypothesis','method')],'rq_alignment':'方法如何回答 RQ，引用已知依据','alternative_discrimination':'如何区分备择解释；不适用须说明理由','conclusion_limits':'当前设计允许与不允许得出的结论','reasoned_findings':['有具体依据的判断'],'unresolved':[],'reviewer_response':'本人核对回应'}}
    state['contract']['content_schema']={
        'default_field_type':'string',
        'array_fields':['scope_refs','mechanical_findings','reasoned_findings','unresolved','evidence_refs','revision_actions'],
        'object_fields':{'deliverable_ref':{'id':'Proposal id','revision':1},'supersedes':{'type':'object','id':'old check id','revision':1}},
        'derived_fields':{'student_quote':'server derives from student_quote_ref','answer_text':'server derives from answer_ref','mechanical_findings':'server computed; scientific judgment belongs in reasoned_findings'},
        'reference':{'type':'object|file|source|claim','id':'current project record id','revision':'required for object; omit for source/file/claim'},
        'enums':{'question_type':['background','measurement','mechanism','open'],'reading_scope':['full','abstract','excerpt','not_read'],'context':['practice','formal']},
        'optional_search_fields':['exclusion_reason','term_change_reason','result_count (nonnegative integer or null)'],
        'hypothesis_confirmation':'explanation, alternatives and scope required; mechanism and prediction, or not_applicable_reason',
        'check_confirmation':'scope_refs required; drafts and confirmation may omit scientific judgments',
        'check_stage_d':'scope_refs must include a current confirmed, reviewed hypothesis -> rq plus rq/hypothesis -> method chain with current confirmed links; all object refs current and confirmed; reasoned_findings, reviewer_response, rq_alignment, alternative_discrimination, conclusion_limits required; unresolved or mechanical findings block completion; structural checks do not establish scientific validity or actual experiments',
        'check_judgment_fields':list(schema.CHECK_JUDGMENTS),
        'new_object':{'kind':'one object_types key','expected_revision':0,'content':{}},
        'relations':sorted(schema.RELATIONS),
        'relation_directions':{'belongs_to':'question -> topic','motivates':'curiosity -> topic/question','groups_into':'question -> problem','frames':'problem -> rq','explains':'hypothesis -> rq','operationalized_by':'rq/hypothesis -> method','supports/challenges/limits':'object/source/file/claim -> problem/hypothesis/rq/method; evidence origin and reading scope remain explicit','compared_with':'same kind objects','replaces':'new -> old'}}
    card['research']=state
    readiness_card=card
    if '_student_messages' not in card and 'student_message_ids' in card:readiness_card=dict(card,_student_messages=dict.fromkeys(card['student_message_ids']))
    state['review_readiness']=workflow.review_readiness(readiness_card)
    if card.get('status') == 'active' and not card.get('_review_preview'):
        try:
            from . import stage_review
        except ImportError:
            import stage_review
        messages = dict(readiness_card.get('_student_messages') or {})
        # Only already validated stored quotations may supplement the message ID
        # index on read-only GETs; POST confirmation re-reads the archive itself.
        for o in state['objects']:
            for reference, text in [('student_quote_ref','student_quote'),('answer_ref','answer_text')]:
                if o['content'].get(reference) and o['content'].get(text):
                    messages[o['content'][reference]] = o['content'][text]
        result = stage_review.preview(c, readiness_card, messages)
        state['review_readiness']['prepared'] = result['prepared']
        state['review_readiness']['execution_check'] = result
        if result['prepared']:
            for item in state['review_readiness']['items']:
                if item['status'] != 'ready': item['status'] = 'confirm'
        else:
            state['review_readiness']['items'].append(dict(kind='execution',label='确认事务检查',status='incomplete',detail=result['detail'],object_ids=[]))
    return card

def capture_reading_sources(c,card):
    materials={m['id'] for m in card.get('materials',[])}
    for comparison in card['steps'][2]['data'].get('source_comparisons',[]):
        rid=comparison['reference']
        comparison['source_snapshot_ref']=s.snapshot(c,card,{'type':'source' if rid in materials else 'file','id':rid})


def ref(c,card,r):
    if not isinstance(r,dict): raise ValueError('引用必须包含 type、id 与 revision。')
    if r.get('project_id',card['id'])!=card['id']: raise ValueError('不能跨项目引用。')
    if r.get('type')=='object':
        if type(r.get('revision')) is not int: raise ValueError('对象引用须有 revision。')
        o=s.get(c,card['id'],r.get('id'),r['revision'])
        return dict(type='object',id=o['id'],revision=o['revision'])
    return s.snapshot(c,card,r)

def validate_link(c,card,left,right,relation):
    target=s.get(c,card['id'],right['id']) if right.get('type')=='object' else None
    source=s.get(c,card['id'],left['id']) if left.get('type')=='object' else None
    allowed={'belongs_to':({'question'},{'topic'}),'motivates':({'curiosity'},{'topic','question'}),'groups_into':({'question'},{'problem'}),'frames':({'problem'},{'rq'}),'explains':({'hypothesis'},{'rq'}),'operationalized_by':({'rq','hypothesis'},{'method'})}
    if not target: raise ValueError('关系目标须为研究对象。')
    if relation in allowed:
        a,b=allowed[relation]
        if not source or source['kind'] not in a or target['kind'] not in b: raise ValueError('关系方向或对象类型不符合 '+relation+' 契约。')
    if relation in ('compared_with','replaces') and (not source or source['kind']!=target['kind']): raise ValueError('比较与替代关系须连接同类研究对象。')
    if relation in ('supports','challenges','limits') and target['kind'] not in ('problem','hypothesis','rq','method'): raise ValueError('依据关系应指向 Problem、假设、RQ 或方法。')
    if source and source['id']==target['id']: raise ValueError('不能建立对象自身关系。')


def _save_objects(c,card,b,user,messages):
    entries=b.get('objects',[]); links=b.get('links',[])
    if not isinstance(entries,list) or not isinstance(links,list) or not (entries or links): raise ValueError('请提供 objects 或 links。')
    seen=set()
    for entry in entries:
        if not isinstance(entry,dict): raise ValueError('对象格式无效。')
        oid=entry.get('id') or s.uid('O')
        if not isinstance(oid,str) or not oid.strip() or len(oid)>100 or oid in seen: raise ValueError('对象 ID 必须唯一有效。')
        seen.add(oid)
        expected=entry.get('expected_revision')
        if type(expected) is not int or expected<0: raise ValueError('请提供 expected_revision。')
        if entry.get('project_id',card['id'])!=card['id'] or 'created_by' in entry: raise ValueError('不能冒填项目或创建身份。')
        if expected:
            old=s.get(c,card['id'],oid)
            if old['revision']!=expected: raise Conflict('对象版本已变化。')
            if old['status'] not in ('draft','pending_confirmation'): raise ValueError('已确认或结束的对象须经本人决定修改。')
            if 'content' in entry: raise ValueError('更新对象请使用 content_patch，避免覆盖未列字段。')
            content=schema.patch(old['content'],entry.get('content_patch')); kind=old['kind']; row=deepcopy(old)
            if entry.get('kind',kind)!=kind: raise ValueError('不能改变对象类型。')
        else:
            kind=entry.get('kind'); content=deepcopy(entry.get('content')); row=dict(id=oid,project_id=card['id'],kind=kind,schema_version=1,created_by=identity(user),created_at=s.now())
        schema.validate(kind,content)
        if entry.get('status','draft') not in ('draft','pending_confirmation'): raise ValueError('直接保存只能形成草稿，确认须由本人决定。')
        for field in (['student_quote_ref'] if kind=='curiosity' else ['answer_ref'] if kind=='defense' else []):
            if content.get(field):
                if content[field] not in (messages or {}): raise ValueError('原话或答辩须引用本项目真实学生消息。')
                content['student_quote' if kind=='curiosity' else 'answer_text']=(messages or {})[content[field]]
        if kind=='defense':
            content['evidence_refs']=[ref(c,card,r) for r in content.get('evidence_refs',[])]
            defense_deliverable(card,content)
        if not isinstance(entry.get('origin_refs',row.get('origin_refs',[])),list): raise ValueError('origin_refs 须为引用列表。')
        row.update(content=content,revision=expected+1,status=entry.get('status','draft'),updated_at=s.now(),origin_refs=[ref(c,card,r) for r in entry.get('origin_refs',row.get('origin_refs',[]))],needs_review=False)
        if kind=='check':
            schema.validate_check_replacement(content,oid,s.rows(c,'research_objects',card['id']))
            if content.get('supersedes'):
                content['supersedes']=ref(c,card,content['supersedes'])
                prior=s.get(c,card['id'],content['supersedes']['id'])
                if prior['kind']!='check' or prior['id']==oid: raise ValueError('supersedes 须引用另一项 CheckRun。')
            content['scope_refs']=[ref(c,card,r) for r in content.get('scope_refs',[])]
            content['mechanical_findings']=mechanical(c,card,content['scope_refs'])
            row['reviewer']=identity(user)
        s.save_object(c,row,expected); s.event(c,card['id'],'object_saved',identity(user),object_id=oid,revision=row['revision'])
    for entry in links:
        if not isinstance(entry,dict) or entry.get('relation') not in schema.RELATIONS: raise ValueError('关联类型无效。')
        if entry.get('status','draft')!='draft' or entry.get('project_id',card['id'])!=card['id']: raise ValueError('关联直接保存只能是本项目草稿。')
        lid=entry.get('id') or s.uid('L')
        if not isinstance(lid,str) or not lid.strip() or len(lid)>100: raise ValueError('关联 ID 无效。')
        if not isinstance(entry.get('evidence_refs',[]),list): raise ValueError('evidence_refs 须为引用列表。')
        if any(l['id']==lid for l in s.rows(c,'research_links',card['id'])): raise Conflict('关联已存在。')
        left=ref(c,card,entry.get('from_ref')); right=ref(c,card,entry.get('to_ref'))
        if right['type']!='object' or not schema.text(entry.get('reason')): raise ValueError('关联目标须为研究对象，并说明理由。')
        validate_link(c,card,left,right,entry['relation'])
        row=dict(id=lid,project_id=card['id'],from_ref=left,to_ref=right,relation=entry['relation'],reason=entry['reason'],evidence_refs=[ref(c,card,r) for r in entry.get('evidence_refs',[])],status='draft',created_by=identity(user),created_at=s.now())
        s.save_link(c,row)

def mechanical(c,card,refs):
    issues=[]
    for r in refs:
        if r.get('type')=='object':
            o=s.get(c,card['id'],r['id'])
            if o['revision']!=r['revision']: issues.append({'object_id':o['id'],'finding':'stale_revision'})
            if o.get('needs_review'): issues.append({'object_id':o['id'],'finding':'needs_review'})
            if o['status']!='confirmed': issues.append({'object_id':o['id'],'finding':'not_confirmed'})
    issues.extend(schema.chain_findings(s.rows(c,'research_objects',card['id']),s.rows(c,'research_links',card['id']),refs))
    return issues

def defense_deliverable(card,content):
    reference=content.get('deliverable_ref')
    if reference is None: return
    if not isinstance(reference,dict) or type(reference.get('revision')) is not int or not any(d['id']==reference.get('id') and d['revision']==reference['revision'] for d in card.get('research',{}).get('deliverables',[])): raise ValueError('答辩须绑定本项目已保存的固定 Proposal 版本。')
    content['deliverable_ref']={'id':reference['id'],'revision':reference['revision']}


def _provenance(kind,content,messages):
    fields={'curiosity':('student_quote_ref','student_quote'),'defense':('answer_ref','answer_text')}
    if kind not in fields: return
    reference,derived=fields[kind]
    if not content.get(reference): return
    if content[reference] not in (messages or {}): raise ValueError('须引用本项目真实学生原话。')
    content[derived]=(messages or {})[content[reference]]


def object_proposal(card,body,user,student_messages=None):
    p=deepcopy(body.get('record',body)); oid=p.get('target_object_id')
    obj=next((o for o in card.get('research',{}).get('objects',[]) if o['id']==oid),None)
    if not obj: raise ValueError('提案目标必须是本项目研究对象。')
    if type(p.get('expected_revision')) is not int: raise ValueError('expected_revision 须为整数。')
    if p.get('expected_revision')!=obj['revision']: raise Conflict('提案对象版本已变化。')
    if not schema.text(p.get('text')) or not schema.text(p.get('reason')): raise ValueError('请填写建议与理由。')
    status=p.get('proposed_status','confirmed')
    if status not in schema.STATES: raise ValueError('proposed_status 无效。')
    candidate=schema.patch(obj['content'],p.get('content_patch',{'set':{},'remove':[]}))
    _provenance(obj['kind'],candidate,student_messages)
    if obj['kind']=='defense': defense_deliverable(card,candidate)
    if obj['kind']=='check': schema.validate_check_replacement(candidate,oid,card['research']['objects'])
    schema.validate(obj['kind'],candidate,status=='confirmed')
    changes=p.get('relation_changes',{'activate_draft_ids':[],'retire_link_ids':[]})
    if not isinstance(changes,dict) or set(changes)-{'activate_draft_ids','retire_link_ids'} or any(not isinstance(v,list) for v in changes.values()): raise ValueError('relation_changes 无效。')
    if any(not isinstance(lid,str) for ids in changes.values() for lid in ids): raise ValueError('关系变更须使用关联 ID 列表。')
    links={l['id']:l for l in card['research']['links']}; baselines={}
    for key,status_expected in [('activate_draft_ids','draft'),('retire_link_ids','confirmed')]:
        for lid in changes.get(key,[]):
            link=links.get(lid)
            if not link or link['status']!=status_expected or oid not in [link['from_ref']['id'],link['to_ref']['id']]: raise ValueError('关联必须属于目标对象且状态匹配。')
            for endpoint in (link['from_ref'],link['to_ref']):
                schema.confirmation_reference(card['research']['objects'],card['research'].get('revisions',[]),endpoint)
            baselines[lid]=deepcopy(link)
    supersedes=p.get('supersedes_proposals',[])
    if not isinstance(supersedes,list) or any(not isinstance(rid,str) for rid in supersedes): raise ValueError('supersedes_proposals 须为旧建议编号列表。')
    prior={r['id']:r for r in card.get('quality',{}).get('records',[])}
    if any(rid not in prior or prior[rid].get('kind')!='proposal' or prior[rid].get('target_object_id')!=oid or prior[rid].get('status')!='pending' for rid in supersedes): raise ValueError('只能替代同一对象尚未决定的建议。')
    return dict(id=s.uid('Q'),kind='proposal',step=schema.STAGES[obj['kind']],created=s.now(),author=identity(user),text=p['text'],reason=p['reason'],status='pending',target_object_id=oid,expected_revision=obj['revision'],content_patch=deepcopy(p.get('content_patch',{'set':{},'remove':[]})),candidate_content=candidate,proposed_status=status,relation_changes=changes,relation_baselines=baselines,requirement_version=card['activity']['version'],supersedes_proposals=supersedes)

def _affected(c,card,oid,include_self=True,keep_navigation=False,preserve=()):
    visited={oid}; queue=[oid]; links=s.rows(c,'research_links',card['id']); affected=set()
    while queue:
        current=queue.pop(0)
        for link in links:
            if link['status']!='confirmed' or link['from_ref'].get('type')!='object' or link['from_ref']['id']!=current or link['relation']=='replaces': continue
            link['needs_review']=True; s.save_link(c,link)
            if link['relation']=='compared_with': continue
            target=link['to_ref']['id']; affected.add(target)
            if target not in visited: visited.add(target); queue.append(target)
        for o in s.rows(c,'research_objects',card['id']):
            if o['status'] in ('superseded','abandoned') or o['id']==current or o['id'] in preserve: continue
            refs=o.get('origin_refs',[])+o['content'].get('scope_refs',[])+o['content'].get('evidence_refs',[])
            if any(r.get('type')=='object' and r.get('id')==current for r in refs):
                affected.add(o['id'])
                if o['id'] not in visited: visited.add(o['id']);queue.append(o['id'])
    for target in affected:
        o=s.get(c,card['id'],target); o['needs_review']=True; s.pointer(c,o)
    state=card.setdefault('research_state',{}); pending=state.setdefault('deliverable_reviews',[])
    for d in s.rows(c,'deliverable_versions',card['id']):
        if any(r['id'] in visited|affected for r in d['object_refs']):
            key={'id':d['id'],'revision':d['revision']}
            if key not in pending: pending.append(key)
    stages={schema.STAGES[s.get(c,card['id'],x)['kind']] for x in affected|({oid} if include_self else set())}
    if pending or affected or include_self: stages.add(6)
    if pending: stages.add(5)
    for n in stages:
        st=card['steps'][n-1]; st['cycle']=st.get('cycle',1)+1
        if st['status'] in ('complete','review'): st['status']='pending'
    if card.get('status') in ('review','approved'): card['status']='active'
    if card.get('status')=='active' and not keep_navigation:
        for st in card['steps']:
            if st['status']=='active': st['status']='pending'
        earliest=next((st['number'] for st in card['steps'] if st['status']!='complete'),card['current_step'])
        workflow.set_navigation_stage(card,earliest);card['steps'][earliest-1]['status']='active'
    card.pop('milestone',None)
    return sorted(affected)

def decide(c,card,body,user,student_messages=None):
    if user.get('role')!='student' or user.get('id')!=card.get('student_id'): raise PermissionError('仅项目学生本人可以决定。')
    work=deepcopy(card); sname='research_decide'
    if not c.in_transaction: c.execute('BEGIN')
    c.execute('SAVEPOINT '+sname)
    try:
        row=next((r for r in work.get('quality',{}).get('records',[]) if r['id']==body.get('record_id') and r.get('target_object_id')),None)
        if not row or row['status'] not in ('pending','deferred'): raise ValueError('建议不存在或已处理。')
        decision=body.get('decision')
        if decision not in ('accepted','rejected','deferred') or not schema.text(body.get('reason')): raise ValueError('请填写本人决定及理由。')
        if decision=='accepted':
            if body.get('confirmed') is not True: raise ValueError('请核对后确认接受。')
            old=s.get(c,card['id'],row['target_object_id'])
            if old['revision']!=row['expected_revision'] or row['requirement_version']!=work['activity']['version']: raise Conflict('对象或活动要求已变化，请重提建议。')
            links={l['id']:l for l in s.rows(c,'research_links',card['id'])}
            for lid,baseline in row['relation_baselines'].items():
                if links.get(lid)!=baseline: raise Conflict('关联已变化，请重提建议。')
            obj=deepcopy(old); obj.update(content=schema.patch(old['content'],row['content_patch']),revision=old['revision']+1,status=row['proposed_status'],updated_at=s.now(),needs_review=False,decision_ref=row['id'])
            _provenance(obj['kind'],obj['content'],student_messages)
            if obj['kind']=='defense':
                obj['content']['evidence_refs']=[ref(c,work,r) for r in obj['content'].get('evidence_refs',[])]
                defense_deliverable(work,obj['content'])
            if obj['kind']=='check':
                obj['content']['scope_refs']=[ref(c,work,r) for r in obj['content'].get('scope_refs',[])]
                obj['content']['mechanical_findings']=mechanical(c,work,obj['content']['scope_refs'])
            schema.validate(obj['kind'],obj['content'],obj['status']=='confirmed')
            unchanged=(old['status']==obj['status']=='confirmed' and old['content']==obj['content']
                       and not old.get('needs_review') and obj['kind']!='check')
            if unchanged: obj=deepcopy(old)
            if obj['kind']=='check' and obj['status']=='confirmed' and obj['content'].get('supersedes'):
                prior_ref=ref(c,work,obj['content']['supersedes']); prior=s.get(c,work['id'],prior_ref['id'])
                if prior['kind']!='check' or prior['id']==obj['id']: raise ValueError('只能替代另一项 CheckRun。')
                if prior['revision']!=prior_ref['revision'] or prior['status']!='confirmed': raise Conflict('待替代检查版本已变化。')
                if not {r['id'] for r in prior['content'].get('scope_refs',[])}.issubset({r['id'] for r in obj['content'].get('scope_refs',[])}): raise ValueError('新核对须覆盖旧检查的研究对象。')
                archived=deepcopy(prior);archived.update(revision=prior['revision']+1,status='superseded',needs_review=False,superseded_by=obj['id'],updated_at=s.now(),decision_ref=row['id'])
                s.save_object(c,archived,prior['revision'])
                s.event(c,work['id'],'check_superseded',identity(user),object_id=prior['id'],replacement_id=obj['id'],proposal_id=row['id'])
            pure_confirmation = (body.get('_stage_review') is True and old['status'] in ('draft','pending_confirmation')
                                 and obj['status']=='confirmed' and old['content']==obj['content'] and not old.get('needs_review'))
            if not unchanged:
                s.save_object(c,obj,old['revision'])
                if not pure_confirmation: _affected(c,work,obj['id'])
                # Content changes invalidate incoming references; evidence-only decisions do not.
                for link in links.values():
                    if pure_confirmation and link['status']=='confirmed' and link['from_ref'].get('type')=='object' and link['from_ref']['id']==obj['id'] and link['from_ref'].get('revision')==old['revision']:
                        link['from_ref']['revision']=obj['revision'];s.save_link(c,link)
                    if link['status']=='confirmed' and link['to_ref']['id']==obj['id']:
                        if pure_confirmation: link['to_ref']['revision']=obj['revision']
                        else: link['needs_review']=True
                        s.save_link(c,link)
            # Relationship effects are evaluated at their target, after applying
            # them. A same-content source is not a changed research result.
            for key,status in [('retire_link_ids','superseded'),('activate_draft_ids','confirmed')]:
                for lid in row['relation_changes'].get(key,[]):
                    link=links[lid]
                    if status=='confirmed':
                        for field in ('from_ref','to_ref'):
                            r=link[field]
                            if r['type']=='object':
                                current=s.get(c,card['id'],r['id'])
                                if r['id']==obj['id']: r['revision']=obj['revision']
                                elif current['revision']!=r['revision']:
                                    try: link[field]=schema.confirmation_reference(s.rows(c,'research_objects',card['id']),s.rows(c,'object_revisions',card['id']),r)
                                    except ValueError as error: raise Conflict(str(error)) from error
                        link['needs_review']=False
                    link['status']=status; link['decision_ref']=row['id']; s.save_link(c,link)
                    target=link['to_ref']['id']
                    if link['relation'] not in ('replaces','compared_with'):
                        if status == 'superseded':
                            downstream=s.get(c,work['id'],target);downstream['needs_review']=True;s.pointer(c,downstream)
                        # The draft check was prepared for this exact method and comparison.
                        # Confirming their already proposed link does not change its evidence.
                        preserve = ()
                        if pure_confirmation and status=='confirmed' and link['relation']=='operationalized_by' and target==obj['id']:
                            source=link['from_ref']
                            expected={(source['id'],source['revision']),(old['id'],old['revision'])}
                            preserve={check['id'] for check in s.rows(c,'research_objects',work['id'])
                                      if check['kind']=='check' and check['status']=='draft' and not check.get('needs_review')
                                      and expected.issubset({(ref['id'],ref['revision']) for ref in check['content'].get('scope_refs',[]) if ref['type']=='object'})}
                        _affected(c,work,target,include_self=status=='superseded',keep_navigation=True,preserve=preserve)
            if any(l['status']=='confirmed' and l['to_ref']['id']==obj['id'] and l.get('needs_review') and l['relation'] not in ('replaces','compared_with') for l in s.rows(c,'research_links',work['id'])):
                obj['needs_review']=True;s.pointer(c,obj)
        row.setdefault('decisions',[]).append(dict(id=s.uid('QD'),decision=decision,reason=body['reason'],at=s.now(),author=identity(user)))
        row.update(status=decision,decision_reason=body['reason'],decided_at=row['decisions'][-1]['at'])
        s.event(c,card['id'],decision,identity(user),quality_decision_id=row['decisions'][-1]['id'],proposal_id=row['id'],object_id=row['target_object_id'])
        enrich(c,work); c.execute('RELEASE '+sname)
    except Exception:
        c.execute('ROLLBACK TO '+sname); c.execute('RELEASE '+sname); raise
    card.clear();card.update(work);return row

def mutate(c,card,action,body,user,coach=False,student_messages=None):
    if user.get('role')!='student' or user.get('id')!=card.get('student_id'): raise PermissionError('只有本项目学生可以保存研究工作。')
    user=dict(user,actor_type='ai' if coach else 'student',name='AI 导师' if coach else user.get('name','学生'))
    work=deepcopy(card)
    if not c.in_transaction: c.execute('BEGIN')
    c.execute('SAVEPOINT research_mutate')
    try:
        if action == 'research-handoff':
            try:
                from . import stage_handoff
            except ImportError:
                import stage_handoff
            stage_handoff.save(c,work,body,user,student_messages)
        elif action == 'research-review':
            if coach: raise PermissionError('阶段核对须由学生在网站完成。')
            try:
                from . import stage_review
            except ImportError:
                import stage_review
            stage_review.apply(c,work,body,user,student_messages)
        elif action in ('research-objects','research-search','research-check'):
            b=deepcopy(body)
            if action!='research-objects':
                kind='search' if action=='research-search' else 'check'
                if not any(key in b for key in ('objects','content','record')): raise ValueError('请将记录字段放入 payload.content；或使用 objects 数组，不能省略记录内容。')
                b={'objects':b.get('objects',[dict(kind=kind,expected_revision=0,content=b.get('content',b.get('record',{})))])}
                if any(o.get('kind')!=kind for o in b['objects']): raise ValueError('记录类型与接口不一致。')
            _save_objects(c,work,b,user,student_messages)
        elif action=='research-focus':
            if body.get('focus_object_id'): s.get(c,work['id'],body['focus_object_id'])
            if not schema.text(body.get('tutor_mode')): raise ValueError('请说明本轮认知活动。')
            work.setdefault('research_state',{}).update(focus_object_id=body.get('focus_object_id'),tutor_mode=body['tutor_mode'])
        elif action=='research-deliverable': deliverables.create(c,work,body,identity(user))
        elif action=='research-recheck':
            if coach: raise PermissionError('复核须由学生在网页确认。')
            if not schema.text(body.get('reason')): raise ValueError('请说明保留或修改依据的理由。')
            obj=s.get(c,work['id'],body.get('object_id'))
            if body.get('expected_revision')!=obj['revision']: raise Conflict('对象版本已变化。')
            if obj['kind']=='check': raise ValueError('CheckRun 须创建新的核对记录，不覆盖历史检查。')
            ids=body.get('link_ids',[])
            if not isinstance(ids,list): raise ValueError('link_ids 须为列表。')
            for r in obj.get('origin_refs',[])+obj['content'].get('evidence_refs',[]):
                if r.get('type')=='object':
                    upstream=s.get(c,work['id'],r['id'])
                    if upstream['revision']!=r['revision'] or upstream.get('needs_review') or upstream['status']!='confirmed': raise ValueError('对象内引用已失效，请提出引用当前版本的修改建议。')
            for link in s.rows(c,'research_links',work['id']):
                if link['status']=='confirmed' and link['to_ref']['id']==obj['id'] and link.get('needs_review'):
                    if link['id'] not in ids: raise ValueError('请逐项核对所有受影响关联。')
                    newer=deepcopy(link); newer.update(id=s.uid('L'),needs_review=False,reason=body['reason'],supersedes=link['id'],created_by=identity(user),created_at=s.now())
                    for field in ('from_ref','to_ref'):
                        if newer[field]['type']=='object':
                            upstream=s.get(c,work['id'],newer[field]['id'])
                            if upstream['status']!='confirmed' or (upstream['id']!=obj['id'] and upstream.get('needs_review')): raise ValueError('请先确认并复核上游对象，再核对下游关系。')
                            newer[field]['revision']=upstream['revision']
                    link['status']='superseded';s.save_link(c,link);s.save_link(c,newer)
            obj['needs_review']=False;s.pointer(c,obj);s.event(c,work['id'],'rechecked',identity(user),object_id=obj['id'],reason=body['reason'])
        else: raise ValueError('未知研究操作。')
        enrich(c,work); c.execute('RELEASE research_mutate')
    except Exception:
        c.execute('ROLLBACK TO research_mutate');c.execute('RELEASE research_mutate');raise
    card.clear();card.update(work);return '已保存研究记录'
