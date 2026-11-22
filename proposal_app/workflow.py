"""A–F completion rules for the new research workflow."""
from copy import deepcopy
from datetime import date
try:
    from . import research_schema as schema, research_store as store, quality_records
except ImportError:
    import research_schema as schema, research_store as store, quality_records
VERSION='tanyue-v1'
BUDGET=dict(weeks=26,weekly_minutes=270,student_hours=117,teacher_hours=13,research_hours=104)
TASKS=[
 ('兴趣探索与问题积累','从实际经历积累问题，选择继续探索的方向。','观察、主题与问法',[('summary','本轮探索收获'),('selection_reason','暂选与未选理由')]),
 ('形成核心 Problem','解释哪些问题由同一困惑连接，并作本人选择。','问题归组与核心困惑',[('summary','归组与选择理由')]),
 ('搜索诊断与假设发展','比较已读原文，推敲解释、预测与研究问题。','来源比较、RQ 与解释路径',[('summary','检索与解释的变化')]),
 ('研究框架与关键验证','核对方法、价值、资源与关键验证。','方法、预算与一致性核对',[('summary','当前判断'),('learning_value','学习价值与依据'),('practical_value','实际价值与依据'),('research_value','研究价值与依据'),('budget','活动预算与时间估算'),('critical_validation','关键条件验证及依据')]),
 ('Proposal 与答辩准备','核对固定版本的开题计划并回应实际追问。','Proposal 与实际答辩',[('summary','本人核对与答辩修订')]),
 ('老师审阅与开题决定','本人提交固定版本，由老师发布正式意见。','正式提交与审阅决定',[('summary','最终核对说明')])]
NEXT=['记录一个具体场景及真实问法。','解释问题之间的联系并选择核心困惑。','比较两篇独立来源的已读原文。','检验核心测法与承诺结论是否一致。','核对开题稿并回答追问。','在网站核对固定版本后提交老师。']
REQUIRED_OBJECTS={1:['curiosity','question'],2:['problem'],3:['search','rq','hypothesis'],4:['method','check'],5:['defense'],6:[]}
OBJECT_LABELS={'curiosity':'原始观察','question':'探索问题','problem':'核心困惑','search':'检索与阅读','rq':'研究问题','hypothesis':'解释与假设','method':'研究方法','check':'一致性核对','defense':'答辩记录'}

A_DIRECTION_KINDS = {'curiosity', 'question', 'topic'}


def direction_object_ids(data):
    direction = data.get('direction')
    if not isinstance(direction, dict):
        return None
    return {direction['observation_id'], direction['main_question_id'], *direction['subquestion_ids']}


def selected_direction_ids(card, n):
    return direction_object_ids(card['steps'][0]['data']) if n == 1 and card.get('steps') else None


def validate_direction(card, data):
    if 'direction' not in data:
        return
    direction = data['direction']
    if not isinstance(direction, dict) or set(direction) != {'observation_id', 'main_question_id', 'subquestion_ids'}:
        raise ValueError('请明确指定最初观察、主问题和已选子问题。')
    subquestions = direction['subquestion_ids']
    if not isinstance(subquestions, list):
        raise ValueError('已选子问题须为列表，可以留空。')
    ids = [direction['observation_id'], direction['main_question_id'], *subquestions]
    if any(not schema.text(oid) for oid in ids) or len(ids) != len(set(ids)):
        raise ValueError('最初观察、主问题和已选子问题需引用不同的有效记录。')
    objects = {o['id']: o for o in card.get('research', {}).get('objects', [])
               if o['status'] not in ('abandoned', 'superseded')}
    for oid, kind in zip(ids, ['curiosity'] + ['question'] * (len(ids) - 1)):
        if objects.get(oid, {}).get('kind') != kind:
            raise ValueError('选中的观察或问题在当前课题中不存在或已停用。')


def stage_objects(card, n):
    selected = selected_direction_ids(card, n)
    research = card.get('research', {})
    objects = [o for o in research.get('objects', [])
            if selected is None or o['kind'] not in A_DIRECTION_KINDS or o['id'] in selected]
    if n in (5, 6) and card.get('steps'):
        data = card['steps'][n - 1]['data']
        fixed = card['steps'][4]['data'].get('deliverable_ref') if n == 6 else None
        fixed = fixed or data.get('deliverable_ref') or research.get('selected_deliverable')
        return [o for o in objects if o['kind'] != 'defense' or
                (fixed and o['content'].get('deliverable_ref') == fixed)]
    return objects


def _object_readiness(card, step=None):
    """Preparation and personal confirmation are separate; never confirm on read."""
    n=step or card['current_step']; items=[]
    selected = selected_direction_ids(card, n)
    candidates = stage_objects(card, n)
    for kind in REQUIRED_OBJECTS[n]:
        objects=[o for o in candidates if o['kind']==kind and o['status'] not in ('abandoned','superseded')]
        ready=[o for o in objects if o['status']=='confirmed' and not o.get('needs_review')]
        complete=[]
        for obj in objects:
            try: schema.validate(kind,obj['content'],confirmed=True)
            except ValueError: continue
            complete.append(obj)
        if selected is not None:
            status = ('missing' if not objects else 'incomplete' if len(complete) != len(objects)
                      else 'recheck' if any(o.get('needs_review') for o in complete)
                      else 'ready' if len(ready) == len(objects) else 'confirm')
        else:
            status='ready' if ready else 'confirm' if any(not o.get('needs_review') for o in complete) else 'recheck' if complete else 'incomplete' if objects else 'missing'
        items.append(dict(kind=kind,label=OBJECT_LABELS[kind],status=status,object_ids=[o['id'] for o in (ready or complete or objects)]))
    prepared=all(i['status'] not in ('missing','incomplete') for i in items)
    return dict(step=n,prepared=prepared,confirmed=all(i['status']=='ready' for i in items),items=items,
                tutor_instruction='先从已有讨论整理漏存或不完整的记录，保存成功后重读本检查；prepared=false时不得让学生回网站核对，不让学生重复已回答内容。prepared=true仅表示必需记录已整理，不代表阶段完成；再检查活动契约、依据与关联，学生本人确认后才能提交。')

def set_navigation_stage(card, step):
    """Activity focus belongs to the current navigation visit, not its successor."""
    if card.get('current_step') != step:
        for container in (card, card.get('research_state', {}), card.get('research', {})):
            container.pop('tutor_mode', None)
            container.pop('focus_object_id', None)
    card['current_step'] = step


def _objects(card,kind):
    return [o for o in card.get('research',{}).get('objects',[]) if o['kind']==kind and o['status']=='confirmed' and not o.get('needs_review')]
def _has_link(card,relation,targets):
    objects={o['id']:o for o in card.get('research',{}).get('objects',[])}
    for link in card.get('research',{}).get('links',[]):
        if link['relation']!=relation or link['status']!='confirmed' or link.get('needs_review') or link['to_ref']['id'] not in targets: continue
        if all(r['type']!='object' or (r['id'] in objects and objects[r['id']]['revision']==r['revision'] and objects[r['id']]['status']=='confirmed' and not objects[r['id']].get('needs_review')) for r in [link['from_ref'],link['to_ref']]): return True
    return False

def selected_deliverable(card,data):
    reference=data.get('deliverable_ref',card.get('research',{}).get('selected_deliverable'))
    if not isinstance(reference,dict): raise ValueError('请选择固定 Proposal 版本。')
    d=next((d for d in card.get('research',{}).get('deliverables',[]) if d['id']==reference.get('id') and d['revision']==reference.get('revision')),None)
    if not d: raise ValueError('Proposal 版本不存在。')
    if d['activity_version']!=card['activity']['version']: raise store.Conflict('活动要求已更新，请重新生成 Proposal。')
    if reference in card.get('research',{}).get('deliverable_reviews',[]): raise ValueError('该 Proposal 已受上游变更影响，请复核后生成新版本。')
    objects={o['id']:o for o in card['research']['objects']}
    for r in d['object_refs']:
        obj=objects.get(r['id'])
        if not obj or obj['revision']!=r['revision'] or obj.get('needs_review') or obj['status']!='confirmed': raise ValueError('Proposal 引用已变化或待复核，请生成新版本。')
    return d

def _reading(card,data,verify_messages=True):
    readings=data.get('source_comparisons',[])
    if not isinstance(readings,list): raise ValueError('source_comparisons 须为列表。')
    materials={r['id']:r for r in card.get('materials',[]) if not r.get('lead')}
    files={r['id']:r for r in card.get('files',[])}
    identities=set(); titles=set(); studies=set()
    for row in readings:
        if not isinstance(row,dict) or any(not schema.text(row.get(k)) for k in ('reference','location','student_message_ref','supports','cannot_claim','question_impact')): raise ValueError('来源比较须包含出处、已读位置、本人原话、支持范围、局限与改题影响。')
        original=materials.get(row['reference']) or files.get(row['reference'])
        if not original or original.get('material_origin')=='ai_generated': raise ValueError('来源比较须引用本项目真实登记来源。')
        if row.get('reading_scope') not in ('full','abstract','excerpt'): raise ValueError('请标明实际阅读范围。')
        messages=card.get('_student_messages',{})
        if verify_messages and row['student_message_ref'] not in messages: raise ValueError('来源比较须引用本项目实际学生原话。')
        identity=original.get('url',original.get('sha256',original['id'])).split('#')[0].lower()
        title=''.join(str(original.get('title',original.get('name',''))).casefold().split())
        study=''.join(str(row.get('study',original.get('study',''))).casefold().split())
        if identity in identities or (title and title in titles) or (study and study in studies): raise ValueError('同一研究的链接、附件或重复条目不能作为两篇独立来源。')
        identities.add(identity)
        if title: titles.add(title)
        if study: studies.add(study)
    if len(identities)<2: raise ValueError('需比较至少两篇独立来源的已读原文。')


def _check_science(card):
    valid_checks=[]
    current={o['id']:o for o in card['research']['objects']}
    for check in _objects(card,'check'):
        content=check['content']; refs=content.get('scope_refs',[])
        if content.get('mechanical_findings') or content.get('unresolved'): continue
        if not content.get('reasoned_findings') or not schema.text(content.get('reviewer_response')): continue
        if any(not schema.text(content.get(key)) for key in schema.CHECK_JUDGMENTS): continue
        if schema.chain_findings(list(current.values()),card['research'].get('links',[]),refs): continue
        if not any(current.get(r.get('id'),{}).get('kind')=='method' for r in refs): continue
        if any(r.get('type')=='object' and (r['id'] not in current or current[r['id']]['revision']!=r['revision'] or current[r['id']].get('needs_review') or current[r['id']]['status']!='confirmed') for r in refs): continue
        valid_checks.append(check)
    if not valid_checks: raise ValueError('一致性核对尚未覆盖当前研究问题、解释与方法，或缺少方法匹配、竞争解释、结论边界及本人回应；请导师先整理并核实。')


def derived_stage_data(card,n,data):
    """Reference existing E/F evidence; never invent a new student judgment."""
    data=deepcopy(data)
    if n not in (5,6): return data
    reference=data.get('deliverable_ref') or card.get('research',{}).get('selected_deliverable')
    if n==6: reference=card['steps'][4]['data'].get('deliverable_ref') or reference
    if not reference: return data
    defenses=[o for o in card.get('research',{}).get('objects',[]) if o['kind']=='defense' and o['status'] not in ('superseded','abandoned') and o['content'].get('deliverable_ref')==reference and o['content'].get('answer_ref')]
    if defenses:
        data.setdefault('deliverable_ref',deepcopy(reference))
        data['defense_refs']=[dict(type='object',id=o['id'],revision=o['revision']) for o in defenses]
        if not schema.text(data.get('summary')) or data.get('summary_origin')=='program_reference':
            data['summary']='核对固定开题计划及对应答辩。' if n==5 else '提交 E 阶段已核对的固定开题计划及对应答辩。'
            data['summary_refs']=[deepcopy(reference),dict(id=defenses[-1]['id'],revision=defenses[-1]['revision'])]
            data['summary_origin']='program_reference'
    return data


def _completion_checks(card,n,data,verify_messages=False):
    data = derived_stage_data(card,n,data)
    issues=[]
    def check(label,fn):
        try: fn()
        except (ValueError,store.Conflict) as error: issues.append(dict(kind='stage_check',label=label,status='incomplete',object_ids=[],detail=str(error)))
    def require(condition,message):
        if not condition: raise ValueError(message)
    for key,label in TASKS[n-1][3]:
        check(label,lambda key=key,label=label:require(schema.text(data.get(key)),label+'尚未整理，请导师从已有讨论保存草稿。'))
    if n==1: check('选定的研究方向',lambda:validate_direction(card,data))
    check('算式复核',lambda:require(not quality_records.unresolved_calculations(card,n),'仍有未解决的算式复算不一致，请先更正依据。'))
    relations={2:[('groups_into','problem','问题归组关系')],3:[('frames','rq','核心困惑与研究问题的关联'),('explains','rq','解释与研究问题的关联')],4:[('operationalized_by','method','研究问题与方法的关联')]}
    for relation,kind,label in relations.get(n,[]):
        check(label,lambda relation=relation,kind=kind,label=label:require(_has_link(card,relation,{o['id'] for o in _objects(card,kind)}),label+'尚未确认或版本已变化，请导师整理关联建议。'))
    if n==3: check('两篇独立来源共读',lambda:_reading(card,data,verify_messages))
    if n==4: check('科学判断与当前引用',lambda:_check_science(card))
    if n in (5,6):
        def fixed():
            selected=selected_deliverable(card,data)
            ref={'id':selected['id'],'revision':selected['revision']}
            require(any(o['content'].get('deliverable_ref')==ref and schema.text(o['content'].get('answer_text')) for o in _objects(card,'defense')),'选定开题计划尚无已确认的对应答辩，不能沿用其他版本的回答。')
            if n==6: require(card['steps'][4]['data'].get('deliverable_ref')==ref,'最终提交稿须与 E 阶段核对的固定版本一致，请先完成新版核对。')
        check('固定开题计划与对应答辩',fixed)
        check('上游成果复核',lambda:require(not any(o.get('needs_review') and o['status']=='confirmed' for o in card.get('research',{}).get('objects',[])),'研究方案存在受影响的成果，请先复核。'))
    if n==6: check('前序阶段',lambda:require(all(s['status']=='complete' for s in card['steps'][:5]),'前序阶段尚未完成或因补证重开，请先完成对应核对。'))
    return issues


def review_readiness(card, step=None):
    result=_object_readiness(card,step);n=result['step']
    data=(card.get('steps') or [{}]*6)[n-1].get('data',{})
    issues=_completion_checks(card,n,data,verify_messages='_student_messages' in card)
    for proposal in card.get('quality',{}).get('records',[]):
        if proposal.get('kind')!='proposal' or proposal.get('status')!='pending':continue
        target=next((o for o in card.get('research',{}).get('objects',[]) if o['id']==proposal.get('target_object_id')),None)
        stale=proposal.get('requirement_version')!=card.get('activity',{}).get('version') or (proposal.get('target_object_id') and (not target or target['revision']!=proposal.get('expected_revision')))
        if any(next((l for l in card.get('research',{}).get('links',[]) if l['id']==lid),None)!=baseline for lid,baseline in proposal.get('relation_baselines',{}).items()):stale=True
        try:
            for baseline in proposal.get('relation_baselines',{}).values():
                for endpoint in (baseline['from_ref'],baseline['to_ref']):
                    schema.confirmation_reference(card['research']['objects'],card['research'].get('revisions',[]),endpoint)
            if target and target['kind']=='check':schema.validate_check_replacement(schema.patch(target['content'],proposal.get('content_patch',{})),target['id'],card['research']['objects'])
        except ValueError:stale=True
        issues.append(dict(kind='pending_choice',proposal_id=proposal['id'],label='本人选择',status='incomplete' if stale else 'confirm',object_ids=[],detail='候选建议的对象、关联或活动版本已变化，请导师更新建议。' if stale else '请核对已整理的建议并留下本人选择。'))
    # Preview both explicit proposals and the website's direct draft confirmation.
    # This is read-only and never substitutes for a personal decision.
    candidates=list(card.get('quality',{}).get('records',[]))
    proposed={p.get('target_object_id') for p in candidates if p.get('kind')=='proposal' and p.get('status') in ('pending','deferred')}
    for draft in stage_objects(card,n):
        if (draft['kind'] in REQUIRED_OBJECTS[n] and draft['status'] in ('draft','pending_confirmation')
            and not draft.get('needs_review') and draft['id'] not in proposed):
            candidates.append(dict(kind='proposal',status='pending',target_object_id=draft['id'],
                expected_revision=draft['revision'],requirement_version=card.get('activity',{}).get('version'),
                content_patch={'set':{},'remove':[]},proposed_status='confirmed',direct_draft=True))
    for proposal in candidates:
        if proposal.get('kind')!='proposal' or proposal.get('status')!='pending': continue
        target=next((o for o in card.get('research',{}).get('objects',[]) if o['id']==proposal.get('target_object_id')),None)
        if not target or target['revision']!=proposal.get('expected_revision') or proposal.get('requirement_version')!=card.get('activity',{}).get('version'): continue
        preview=deepcopy(card)
        obj=next(o for o in preview['research']['objects'] if o['id']==target['id'])
        obj['content']=schema.patch(obj['content'],proposal.get('content_patch',{}))
        try: schema.validate(obj['kind'],obj['content'],confirmed=True)
        except ValueError: continue
        if obj['kind']=='check':
            try: schema.validate_check_replacement(obj['content'],obj['id'],preview['research']['objects'])
            except ValueError: continue
        unchanged=(target['status']==proposal.get('proposed_status','confirmed')=='confirmed'
                   and target['content']==obj['content'] and not target.get('needs_review') and obj['kind']!='check')
        obj.update(status=proposal.get('proposed_status','confirmed'),revision=obj['revision']+(0 if unchanged else 1),needs_review=False)
        for link in preview['research'].get('links',[]):
            if link['id'] not in proposal.get('relation_changes',{}).get('activate_draft_ids',[]): continue
            if link!=proposal.get('relation_baselines',{}).get(link['id']): continue
            link.update(status='confirmed',needs_review=False)
            for field in ('from_ref','to_ref'):
                if link[field].get('id')==obj['id']:link[field]['revision']=obj['revision']
                else:
                    try:link[field]=schema.confirmation_reference(card['research']['objects'],card['research'].get('revisions',[]),link[field])
                    except ValueError:link['needs_review']=True
        remaining={i['label'] for i in _completion_checks(preview,n,data,verify_messages='_student_messages' in card)}
        for issue in issues:
            if issue['kind']!='pending_choice' and issue['label'] not in remaining:
                issue.update(status='confirm',object_ids=[obj['id']],detail='内容已整理，请本人核对草稿；确认后会重新检查实际版本。' if proposal.get('direct_draft') else '已整理为待选建议，请本人核对；决定后会重新检查实际版本。')
    # A single website confirmation can accept several dependent drafts together.
    # Preview that final state without changing stored objects or their versions.
    combined=deepcopy(card)
    for proposal in candidates:
        if proposal.get('kind')!='proposal' or proposal.get('status')!='pending': continue
        obj=next((o for o in combined['research']['objects'] if o['id']==proposal.get('target_object_id')),None)
        if not obj or obj.get('needs_review') or obj['revision']!=proposal.get('expected_revision') or proposal.get('requirement_version')!=card.get('activity',{}).get('version'): continue
        content=schema.patch(obj['content'],proposal.get('content_patch',{}))
        try: schema.validate(obj['kind'],content,confirmed=True)
        except ValueError: continue
        obj.update(content=content,status=proposal.get('proposed_status','confirmed'))
        for link in combined['research'].get('links',[]):
            if link['id'] in proposal.get('relation_changes',{}).get('activate_draft_ids',[]) and link==proposal.get('relation_baselines',{}).get(link['id']):
                link.update(status='confirmed',needs_review=False)
    for obj in combined.get('research',{}).get('objects',[]):
        if obj['kind']=='check' and obj['status']=='confirmed' and not obj.get('needs_review'):
            refs=obj['content'].get('scope_refs',[])
            try:
                refs=[schema.confirmation_reference(combined['research']['objects'],combined['research'].get('revisions',[]),r) for r in refs]
                obj['content']['scope_refs']=refs
            except ValueError: continue
            current={o['id']:o for o in combined['research']['objects']}
            if all(r.get('type')!='object' or (r['id'] in current and current[r['id']]['revision']==r['revision'] and current[r['id']]['status']=='confirmed' and not current[r['id']].get('needs_review')) for r in refs):
                obj['content']['mechanical_findings']=schema.chain_findings(combined['research']['objects'],combined['research'].get('links',[]),refs)
    remaining={i['label'] for i in _completion_checks(combined,n,data,verify_messages='_student_messages' in card)}
    for issue in issues:
        if issue['kind']!='pending_choice' and issue['label'] not in remaining:
            issue.update(status='confirm',detail='内容已整理，确认后会核查实际版本。')
    result['items'].extend(issues)
    result['prepared']=result['prepared'] and not any(i['status'] not in ('confirm','ready') for i in issues)
    result['confirmed']=result['confirmed'] and not issues
    result['tutor_instruction']='阶段交接前逐项检查items：已有讨论能补齐的记录、小结、关联、共读、判断与版本先整理保存；不得把漏存交给学生。prepared=false时不能宣称阶段已准备好。确需先由本人决定的中间建议，明确只核对该建议，不是提交阶段；决定后导师重读并更新关联与引用，再检查。'
    return result

def validate_completion(card,n,data):
    data = derived_stage_data(card,n,data)
    if any(not schema.text(data.get(key)) for key,_ in TASKS[n-1][3]): raise ValueError('请补全本阶段小结与选择依据。')
    if quality_records.unresolved_calculations(card,n): raise ValueError('仍有未解决的算式复算不一致，请先更正依据。')
    readiness=_object_readiness(card,n)
    missing=[i for i in readiness['items'] if i['status']!='ready']
    if missing:
        labels={'missing':'尚未整理','incomplete':'内容待补齐','confirm':'待本人确认','recheck':'待本人复核'}
        raise ValueError('阶段成果尚未就绪：'+'；'.join(i['label']+'（'+labels[i['status']]+'）' for i in missing)+'。请先完成核对页列出的事项。')
    if any(r.get('kind')=='proposal' and r.get('status')=='pending' for r in card.get('quality',{}).get('records',[])):
        raise ValueError('仍有待本人选择的建议，请先核对并留下选择与理由。')
    issues=_completion_checks(card,n,data,verify_messages=True)
    if issues: raise ValueError('；'.join(item['detail'] for item in issues))


def save_progress(card,b,user):
    if b.get('_coach') and (b.get('complete') or b.get('confirmed')):
        raise PermissionError('阶段确认和完成须由学生在网页执行。')
    if user.get('role')!='student' or user.get('id')!=card.get('student_id'): raise PermissionError('仅项目学生可以保存阶段进展。')
    if b.get('workflow_version')!=VERSION: raise store.Conflict('请读取当前工作流版本后提交。')
    n=b.get('step'); complete=b.get('complete') is True
    if type(n) is not int or not 1<=n<=6: raise ValueError('阶段编号无效。')
    if card['status']!='active' or (n!=card['current_step'] and not (not complete and n>card['current_step'])): raise store.Conflict('只能完成当前导航阶段；后续阶段可以保存草稿。')
    if complete and b.get('confirmed') is not True: raise ValueError('请核对本轮进展。')
    updates=b.get('data')
    if not isinstance(updates,dict) or not updates: raise ValueError('请填写阶段进展。')
    work=deepcopy(card); step=work['steps'][n-1]; data=deepcopy(step['data'])
    previous_direction = data.get('direction') if n == 1 else None
    data.update(deepcopy(updates))
    data=derived_stage_data(work,n,data)
    if n==1:
        validate_direction(work,data)
        changed_main = previous_direction and previous_direction['main_question_id'] != data['direction']['main_question_id']
        for key in ('technical_plan','first_validation'):
            if changed_main and key not in updates: data.pop(key,None)
            if key in data and not schema.text(data[key]): raise ValueError('请填写已讨论的技术方案或第一步验证。')
    if complete:
        validate_completion(work,n,data)
        if n in (5,6):
            selected=selected_deliverable(work,data);data['deliverable_ref']={'id':selected['id'],'revision':selected['revision']}
        if n==6 and b.get('_coach') is True: raise PermissionError('最终提交须由本人在网页核对。')
        if n==6 and any(s['status']!='complete' for s in work['steps'][:5]): raise ValueError('请先完成 A—E 并核对受影响阶段。')
    step.update(data=data,confirmed=b.get('confirmed') is True,requirement_version=work['activity']['version'])
    if complete:
        step['status']='complete'
        if n==6:
            d=selected_deliverable(work,data)
            work['submitted_deliverable']=dict(id=d['id'],revision=d['revision'],activity_version=d['activity_version'],submitted_by=user['id'],submitted_at=store.now())
            work.setdefault('submissions',[]).append(deepcopy(work['submitted_deliverable']))
            work['status']='review';step['status']='review';work['next_action']='等待老师审阅固定 Proposal 版本。'
        else:
            remaining=next((s['number'] for s in work['steps'] if s['status']!='complete'),6)
            set_navigation_stage(work,remaining);work['steps'][remaining-1]['status']='active';work['next_action']=NEXT[remaining-1]
        work['milestone']=dict(step=n,title=step['title'],summary=data['summary'],version=work.get('version',0)+1,kind='submitted' if n==6 else 'stage_complete',next_action=work['next_action'],return_url='/?project='+work['id'])
    elif n>work['current_step']: step['draft_saved']=True
    elif schema.text(b.get('next_action')): work['next_action']=b['next_action']
    card.clear();card.update(work)
    return ('提交开题计划' if n==6 else '完成'+step['title']) if complete else '保存阶段进展'

def review(card,b,user):
    if user.get('role')!='teacher': raise PermissionError('仅老师可以发布正式审阅。')
    if card['status']!='review' or not card.get('submitted_deliverable'): raise store.Conflict('请等待学生提交固定版本。')
    submission=card['submitted_deliverable']
    if b.get('deliverable_version',submission)!=submission: raise store.Conflict('提交版本已变化，请重新读取后审阅。')
    if submission['activity_version']!=card['activity']['version']: raise store.Conflict('活动要求已改变，请学生重新核对提交。')
    reviewed_refs=b.get('object_refs',[])
    if not isinstance(reviewed_refs,list): raise ValueError('审阅对象引用须为列表。')
    d=next((d for d in card.get('research',{}).get('deliverables',[]) if d['id']==submission['id'] and d['revision']==submission['revision']),None)
    if not d or any(not isinstance(r,dict) or not any(r.get('id')==v['id'] and r.get('revision')==v['revision'] for v in d['object_refs']) for r in reviewed_refs): raise ValueError('审阅引用必须属于固定提交版本。')
    decision=b.get('decision'); required={'approve':['value','feasibility','deliverable','annual_acceptance','owner','due','standard'],'supplement':['value','feasibility','deliverable','owner','due'],'redirect':['value','feasibility','deliverable']}
    if decision not in required or any(not schema.text(b.get(k)) for k in required.get(decision,[])): raise ValueError('请补全正式决定、依据及后续任务。')
    if decision in ('approve','supplement'):
        try: date.fromisoformat(b['due'])
        except ValueError: raise ValueError('请填写有效日期。')
    work=deepcopy(card); row={k:b[k] for k in required[decision]}; row.update(decision=decision,name=user.get('name'),created=store.now(),deliverable_ref=deepcopy(submission),object_refs=deepcopy(reviewed_refs or d['object_refs']))
    for key in ('standard','evidence','gaps','annual_acceptance'):
        if schema.text(b.get(key)): row[key]=b[key]
    if work.get('review'): work.setdefault('prior_reviews',[]).append(work['review'])
    work['review']=row
    if decision=='approve': work['status']='approved';work['steps'][5]['status']='complete'
    else:
        n=1 if decision=='redirect' else b.get('step',4)
        if type(n) is not int or not 1<=n<=5: raise ValueError('补证阶段无效。')
        for target in {n,5,6}:
            st=work['steps'][target-1];st['status']='pending';st['cycle']=st.get('cycle',1)+1
        work['status']='active';set_navigation_stage(work,n);work['steps'][n-1]['status']='active';row['step']=n
        work.pop('milestone',None)
    work['next_action']=b['deliverable'];card.clear();card.update(work)
    return {'approve':'老师同意开题','supplement':'老师要求补证','redirect':'老师建议调整方向'}[decision]
