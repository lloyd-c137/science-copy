"""Synthetic research fixtures; service evidence, never real classroom results."""
import json
import uuid
from pathlib import Path
from proposal_app import research_service as research, research_store as store, deliverables
from proposal_app.project_archive import atomic_json

CONTENTS={
 'problem':dict(puzzle='同样路程为何迟到次数不同？',grouping_reason='快慢与稳定性围绕准时问题',candidate_explanations='灯控与出发时刻'),
 'rq':dict(population_or_object='两条上学路线',conditions='同一工作日时段',question='两条路线用时波动有何差别？',scope='仅观察时段',promised_conclusion='样本中的用时差异'),
 'method':dict(research_type='observational',materials='实际出发到达记录',procedure='交替记录两条路线',analysis='比较分布与迟到次数',variables_or_concepts='路线与用时',feasibility='校历允许两周记录',limits='不能推断路线本身的因果效果',ethics='仅记录本人通勤，无额外参与者')}

def seed_review(c,card,user):
    """Narrow review-test precondition: real immutable objects and proposal row."""
    research.enrich(c,card)
    for kind,content in CONTENTS.items():
        research.mutate(c,card,'research-objects',{'objects':[dict(id=kind,kind=kind,expected_revision=0,content=content)]},user)
        p=research.object_proposal(card,{'record':dict(target_object_id=kind,expected_revision=1,text='合成审阅夹具确认',reason='用于隔离测试审阅权限',content_patch={'set':{},'remove':[]},proposed_status='confirmed')},user)
        card.setdefault('quality',{}).setdefault('records',[]).append(p)
        research.decide(c,card,dict(record_id=p['id'],decision='accepted',reason='合成夹具本人选择',confirmed=True),user)
    d=deliverables.create(c,card,dict(chapters={k:'合成审阅夹具章节：'+k for k in deliverables.CHAPTERS},object_refs=[dict(type='object',id=k,revision=2) for k in CONTENTS]),user)
    card.update(status='review',current_step=6,submitted_deliverable=dict(id=d['id'],revision=d['revision'],activity_version=card['activity']['version']))
    for st in card['steps']:st['status']='complete' if st['number']<6 else 'review'
    research.enrich(c,card)
    return card

class ResearchHTTP:
    """Drive all research writes through authenticated HTTP with synthetic messages."""
    def __init__(self,case):
        self.t=case;self.card=case.api(case.path,case.student)
        archive=case.srv.project_archive
        archive.sessions=Path(case.temp.name)/'fixture-sessions';archive.sessions.mkdir(exist_ok=True)
        tid=str(uuid.uuid4())
        self.messages={'observation':'合成学生原话：近路遇到红灯时也会迟到。','read-a':'合成学生原话：甲文图1仅比较工作日样本。','read-b':'合成学生原话：乙文第2节比较分布，不能推出因果。','answer':'合成学生原话：我只能比较这两周的样本，天气可能影响结果。'}
        rows=[{'type':'response_item','payload':{'type':'message','id':mid,'role':'user','content':[{'type':'input_text','text':text}]}} for mid,text in self.messages.items()]
        (archive.sessions/('rollout-'+tid+'.jsonl')).write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows),encoding='utf-8')
        atomic_json(archive.folder(self.card)/'stages/1-1/conversation.json',dict(thread_id=tid,step=1,title='合成验收'))
    def write(self,action,payload,expect=200,web=False):
        body=dict(version=self.card['version'],requirement_version=self.card['activity']['version'],request_id=uuid.uuid4().hex,**payload)
        result=self.t.api(self.t.path+'/'+action,('cookie:'+self.t.student) if web else self.t.student,body,expect)
        if expect==200:self.card=result
        return result
    def obj(self,oid,kind,content,links=()):
        self.write('research-objects',{'objects':[dict(id=oid,kind=kind,expected_revision=0,content=content)],'links':list(links)})
        return self.confirm(oid,[l['id'] for l in links])
    def confirm(self,oid,links=(),patch=None):
        o=next(o for o in self.card['research']['objects'] if o['id']==oid)
        self.write('quality',{'kind':'proposal','record':dict(target_object_id=oid,expected_revision=o['revision'],text='核对当前选择',reason='合成测试中的明确取舍',content_patch=patch or {'set':{},'remove':[]},proposed_status='confirmed',relation_changes={'activate_draft_ids':list(links),'retire_link_ids':[]})})
        p=self.card['quality']['records'][-1]
        return self.write('quality-decision',dict(record_id=p['id'],decision='accepted',reason='合成测试：本人核对依据后选择',confirmed=True),web=True)
    def ref(self,oid):
        o=next(o for o in self.card['research']['objects'] if o['id']==oid)
        return dict(type='object',id=oid,revision=o['revision'])
    def link(self,source,target,relation):
        return dict(id='L-'+source+'-'+target,from_ref=self.ref(source),to_ref=dict(type='object',id=target,revision=1),relation=relation,reason='合成验收中具体依赖')
    def progress(self,n,data=None,expect=200):
        return self.write('progress',dict(workflow_version='tanyue-v1',step=n,data=data or {'summary':'合成测试：核对本阶段'},confirmed=True,complete=True),expect,web=True)
    def stage_a(self):
        self.obj('curiosity','curiosity',dict(observation='近路也会迟到',why_care='想准时到校',student_quote_ref='observation'))
        self.obj('question','question',dict(wording='近路更稳定吗？',question_type='measurement',importance='关系到准时'))
        return self.progress(1,dict(summary='留下观察和问题',selection_reason='先比较稳定性，暂不研究天气机制'))
    def stage_b(self):
        self.obj('problem','problem',CONTENTS['problem'],[self.link('question','problem','groups_into')])
        return self.progress(2)
    def stage_c(self):
        for suffix in ('a','b'):
            self.t.api(self.t.path+'/sources',self.t.student,dict(title='合成论文'+suffix,url='https://example.org/study-'+suffix,help='提供比较方法',limit='仅样本观察',request_id='source-'+suffix))
        self.card=self.t.api(self.t.path,self.t.student)
        self.obj('search','search',dict(query='路线 用时 波动',channel='合成搜索夹具',searched_at='2026-11-17',result_count=None,selection_reason='两种独立研究方法',understanding_change='区分均值与稳定性',reading_scope='excerpt'))
        self.obj('hypothesis','hypothesis',dict(explanation='信号灯可能增加波动',mechanism='等待时长变化',prediction='等待较长时总时长增加',alternatives='出发时刻差异',scope='仅本人的两条工作日通勤路线'))
        self.obj('rq','rq',CONTENTS['rq'],[self.link('problem','rq','frames'),self.link('hypothesis','rq','explains')])
        self.readings=[dict(reference=m['id'],location='图1或第2节',student_message_ref='read-'+m['url'][-1],supports='支持比较样本分布',cannot_claim='不能推出因果',question_impact='保留观察性比较',reading_scope='excerpt') for m in self.card['materials']]
        self.progress(3,dict(summary='缺少独立原文比较',source_comparisons=self.readings[:1]),422)
        return self.progress(3,dict(summary='两种独立来源共读',source_comparisons=self.readings))
    def stage_d(self):
        self.obj('method','method',CONTENTS['method'],[self.link('rq','method','operationalized_by')])
        self.obj('check','check',dict(scope_refs=[self.ref('rq'),self.ref('hypothesis'),self.ref('method')],rq_alignment='比较样本用时分布能回答差异问题',alternative_discrimination='观察设计不能排除出发时刻影响，不声称识别因果',conclusion_limits='仅本人两周样本，正式观察尚未开展',reasoned_findings=[{'finding':'合成核对：观察计划只承诺样本比较','evidence_refs':[self.ref('method')]}],unresolved=[],reviewer_response='已限定范围，不主张因果'))
        return self.progress(4,dict(summary='核对可行范围',learning_value='学习比较分布',practical_value='本人通勤选择',research_value='提供本场景样本',budget='26周117小时内安排，两周记录',critical_validation='合成夹具的时间记录可定位，不声称完成实际小试'))
    def stage_e(self):
        self.deliverable()
        self.defense()
        return self.progress(5)
    def defense(self):
        return self.obj('defense-'+str(len(self.card['research']['deliverables'])),'defense',dict(question='能否证明路线导致迟到？',answer_ref='answer',answer_text='服务将从原话派生',evidence_refs=[self.ref('method')],context='practice',deliverable_ref=self.card['research']['selected_deliverable']))
    def deliverable(self):
        return self.write('research-deliverable',dict(chapters={k:'合成开题计划章节 '+k+'，正式研究未开展。' for k in deliverables.CHAPTERS},object_refs=[self.ref(k) for k in ('problem','rq','method')]))
    def ready(self):
        self.stage_a();self.stage_b();self.stage_c();self.stage_d();self.stage_e();self.progress(6)
        return self.card
