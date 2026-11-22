"""Versioned research object vocabulary and structural validation."""
from copy import deepcopy
KINDS = {'curiosity','topic','question','problem','rq','hypothesis','method','search','check','defense'}
STATES = {'draft','pending_confirmation','confirmed','superseded','abandoned'}
RELATIONS = {'motivates','belongs_to','groups_into','frames','explains','operationalized_by','supports','challenges','limits','compared_with','replaces'}
STAGES = {'curiosity':1,'topic':1,'question':1,'problem':2,'search':3,'hypothesis':3,'rq':3,'method':4,'check':4,'defense':5}
REQUIRED = {'curiosity':['observation','why_care','student_quote_ref'], 'topic':['title','exploration_reason'], 'question':['wording','question_type','importance'], 'problem':['puzzle','grouping_reason','candidate_explanations'], 'rq':['population_or_object','conditions','question','scope','promised_conclusion'], 'hypothesis':['explanation','alternatives','scope'], 'method':['research_type','materials','procedure','analysis','variables_or_concepts','feasibility','limits','ethics'], 'search':['query','channel','searched_at','selection_reason','understanding_change','reading_scope'], 'check':['scope_refs'], 'defense':['question','answer_ref','answer_text','evidence_refs','context','deliverable_ref']}
CHECK_JUDGMENTS = ('rq_alignment','alternative_discrimination','conclusion_limits')

def text(v): return isinstance(v,str) and bool(v.strip())

def confirmation_reference(objects, revisions, reference):
    """Only rebase a single content-identical draft -> personal confirmation."""
    if reference.get('type')!='object': return deepcopy(reference)
    current=next((o for o in objects if o['id']==reference.get('id')),None)
    if current and current['revision']==reference.get('revision'): return deepcopy(reference)
    previous=next((o for o in revisions if o.get('id',o.get('object_id'))==reference.get('id') and o['revision']==reference.get('revision')),None)
    if (current and previous and current['revision']==previous['revision']+1
        and previous['status'] in ('draft','pending_confirmation') and current['status']=='confirmed'
        and current.get('decision_ref') and not current.get('needs_review')
        and current['content']==previous['content'] and current.get('origin_refs',[])==previous.get('origin_refs',[])):
        return dict(reference,revision=current['revision'])
    raise ValueError('关联对象版本已变化，请导师更新关联建议后再核对。')

def validate_check_replacement(content, oid, objects):
    reference=content.get('supersedes')
    if not reference: return
    prior=next((o for o in objects if o['id']==reference.get('id')),None) if isinstance(reference,dict) else None
    if not prior or prior['kind']!='check' or prior['id']==oid or prior['status']!='confirmed':
        raise ValueError('只能替代另一项已确认检查；旧检查为草稿时请更新草稿，或创建不带supersedes的独立检查。')
    if prior['revision']!=reference.get('revision'): raise ValueError('待替代检查版本已变化。')
    if not {r['id'] for r in prior['content'].get('scope_refs',[])}.issubset({r['id'] for r in content.get('scope_refs',[])}):
        raise ValueError('新核对须覆盖旧检查的研究对象。')

def patch(content, p):
    if not isinstance(p,dict) or set(p)-{'set','remove'} or not isinstance(p.get('set',{}),dict) or not isinstance(p.get('remove',[]),list): raise ValueError('content_patch 须使用 set 与 remove。')
    if any(not isinstance(k,str) for k in p.get('remove',[])) or set(p.get('set',{})) & set(p.get('remove',[])): raise ValueError('同一字段不能同时设置与删除。')
    out=deepcopy(content); out.update(deepcopy(p.get('set',{})))
    for key in p.get('remove',[]): out.pop(key,None)
    return out

def validate(kind, content, confirmed=False):
    if kind not in KINDS or not isinstance(content,dict): raise ValueError('研究对象类型或 content 无效。')
    if confirmed:
        missing=[k for k in REQUIRED[kind] if not content.get(k) or (isinstance(content.get(k),str) and not content[k].strip())]
        if missing: raise ValueError('对象尚缺：'+', '.join(missing))
    if kind=='question' and content.get('question_type','open') not in ('background','measurement','mechanism','open'): raise ValueError('question_type 无效。')
    if kind=='search':
        n=content.get('result_count')
        if n is not None and (type(n) is not int or n<0): raise ValueError('result_count 必须是非负整数或 null。')
        if content.get('reading_scope','not_read') not in ('full','abstract','excerpt','not_read'): raise ValueError('reading_scope 无效。')
    if kind=='defense' and content.get('context','practice') not in ('practice','formal'): raise ValueError('答辩 context 无效。')

    arrays={'scope_refs','mechanical_findings','reasoned_findings','unresolved','evidence_refs','revision_actions'}
    for key,value in content.items():
        if kind=='check' and key in CHECK_JUDGMENTS and not isinstance(value,str): raise ValueError(key+' 须为文字。')
        if key in arrays and not isinstance(value,list): raise ValueError(key+' 须为列表。')
        if key in REQUIRED[kind] and key not in arrays and key!='deliverable_ref' and not isinstance(value,str): raise ValueError(key+' 须为文字。')
    if kind=='check' and confirmed and not content.get('scope_refs'): raise ValueError('核对须引用具体对象版本。')
    if kind=='curiosity' and confirmed and not text(content.get('student_quote')): raise ValueError('观察须有实际学生原话。')
    if kind=='hypothesis' and confirmed and not (text(content.get('prediction')) and text(content.get('mechanism'))) and not text(content.get('not_applicable_reason')): raise ValueError('解释须包含机制与预测，或说明理论/质性适配理由。')


def chain_findings(objects, links, refs):
    """Structural coverage only; never certifies scientific validity or actual evidence."""
    current={o['id']:o for o in objects}
    scoped={r['id'] for r in refs if r.get('type')=='object' and r.get('id') in current
            and current[r['id']]['revision']==r.get('revision')
            and current[r['id']]['status']=='confirmed' and not current[r['id']].get('needs_review')}
    missing=[kind for kind in ('rq','hypothesis','method') if not any(current[oid]['kind']==kind for oid in scoped)]
    if missing:return [{'finding':'missing_chain_scope','kinds':missing}]
    edges=[]
    for link in links:
        if link['status']!='confirmed' or link.get('needs_review'):continue
        ends=[link['from_ref'],link['to_ref']]
        if all(r.get('type')=='object' and r.get('id') in scoped and current[r['id']]['revision']==r.get('revision') for r in ends):
            edges.append((link['relation'],ends[0]['id'],ends[1]['id']))
    for relation,h,r in edges:
        if relation!='explains' or current[h]['kind']!='hypothesis' or current[r]['kind']!='rq':continue
        if any(rel=='operationalized_by' and origin in (h,r) and current[target]['kind']=='method' for rel,origin,target in edges):return []
    return [{'finding':'missing_confirmed_reasoning_chain'}]
