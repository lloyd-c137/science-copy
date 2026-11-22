"""Teacher review MCP: evidence reads and draft writes, never publication."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

if __package__:
    from .coach_mcp import Client, ToolError, encode
else:
    from coach_mcp import Client, ToolError, encode

FIELDS = {key:{"type":"string"} for key in (
    "value","feasibility","annual_acceptance","deliverable","standard","owner","due","evidence","gaps")}
FIELDS.update(deliverable_version={"type":"object","description":"读取到的submitted_deliverable固定版本引用"},object_refs={"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"revision":{"type":"integer"}},"required":["id","revision"]}},decision={"type":"string","enum":["approve","supplement","redirect"]},
              step={"type":"integer","minimum":1,"maximum":5})
TOOLS = [
    {"name":"review_read_project","description":"读取本项目最新开题卡、老师要求、材料、学生可见对话和学习观察，以及已有审阅草稿。先读再判断。",
     "annotations":{"readOnlyHint":True},"inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"review_read_material","description":"读取本项目文本、Markdown或CSV材料正文。PDF等未解析文件明确标记为未读，不据文件名声称已核实全文。",
     "annotations":{"readOnlyHint":True},"inputSchema":{"type":"object","properties":{"file_id":{"type":"string"}},"required":["file_id"],"additionalProperties":False}},
    {"name":"review_save_draft","description":"自动填写网站审阅草稿供老师核对，不发布、不改变学生状态。字段由本次判断填写，版本来自最新读取。",
     "inputSchema":{"type":"object","properties":{
         "project_version":{"type":"integer","minimum":1},"requirement_version":{"type":"integer","minimum":1},
         "draft_revision":{"type":"string","minLength":0,"description":"沿用首次读取的 review_draft.draft.revision；没有草稿时直接传空字符串。"},
         "draft":{"type":"object","properties":FIELDS,"additionalProperties":False,
                  "required":["decision","value","feasibility","deliverable","evidence","gaps"]}},
         "required":["project_version","requirement_version","draft_revision","draft"],"additionalProperties":False}},
]

def context(client, project):
    base='/api/projects/'+quote(project,safe='')
    card=client.request(base)
    discussions=client.request(base+'/discussions')
    draft=client.request(base+'/review-draft')
    return {"project":card,"student_discussions":discussions,"review_draft":draft,
            "return_url":client.origin+'/?project='+project,
            "evidence_rule":"缺失的对话或文献全文表示尚无法核查，不据开题稿推断学生实际参与，也不因记录缺失自动否定研究。"}

def run_tool(name,args,client=None,project=None,folder=None):
    project=project or os.environ.get('PROPOSAL_PROJECT_ID','')
    if not project: raise ToolError('缺少审阅项目绑定，请从网站重新打开辅助审阅。')
    if not isinstance(args,dict):raise ToolError('参数应为对象。')
    client=client or Client.load()
    if name=='review_read_project':
        if args:raise ToolError('读取工具不需要参数。')
        return context(client,project)
    if name=='review_read_material':
        if set(args)!={'file_id'} or not isinstance(args['file_id'],str):raise ToolError('请提供材料编号。')
        card=client.request('/api/projects/'+quote(project,safe=''))
        entry=next((item for item in card['files'] if item['id']==args['file_id']),None)
        if entry is None:raise ToolError('当前项目没有这份材料。')
        if Path(entry['name']).suffix.lower() not in ('.txt','.md','.csv','.json'):
            return {'name':entry['name'],'read':False,'note':'此文件格式尚未解析，请老师打开原文件核查；不能声称已阅读或核实其内容。','url':client.origin+entry['url']}
        raw=client.request(entry['url'],binary=True)
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:raise ToolError('材料不是UTF-8文本，请老师打开原文件核查。')
        return {'name':entry['name'],'read':True,'text':text[:60000],'truncated':len(text)>60000}
    if name=='review_save_draft':
        if set(args)!={'draft','project_version','requirement_version','draft_revision'} or not isinstance(args['draft'],dict):
            raise ToolError('请提交草稿和读取时的项目、要求版本。')
        if set(args['draft'])-set(FIELDS):raise ToolError('草稿包含未知字段。')
        result=client.request('/api/projects/'+quote(project,safe='')+'/review-draft',
                              dict(args['draft'],project_version=args['project_version'],requirement_version=args['requirement_version'],draft_revision=args['draft_revision']))
        # Also retain a readable teacher-owned draft, never in the student's archive.
        folder=Path(folder) if folder else Path(os.environ['PROPOSAL_CLIENT_DIR']).parent.parent
        folder.mkdir(parents=True,exist_ok=True)
        labels={'decision':'建议结论','value':'研究价值','feasibility':'年度可行性','annual_acceptance':'年度验收依据',
                'deliverable':'下一步交付物','standard':'完成标准','owner':'责任人','due':'日期','evidence':'判断依据','gaps':'待核实事项','step':'补证阶段','deliverable_version':'提交版本','object_refs':'对象依据'}
        text='# 审阅草稿 · 待老师确认\n\n'+'\n\n'.join('## '+labels[k]+'\n\n'+str(v) for k,v in args['draft'].items())
        try:(folder/'审阅草稿.md').write_text(text,'utf-8')
        except OSError:pass  # The website is authoritative; a local export failure must not undo its saved draft.
        return result
    raise ToolError('未知审阅工具。')

def dispatch(message):
    if 'id' not in message:return None
    method=message.get('method');params=message.get('params',{})
    if method=='initialize':
        result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},
                'serverInfo':{'name':'proposal_review','version':'1.0'},
                'instructions':'先读完整项目，作出证据明确的判断并自动保存草稿；最终由老师在网站确认发布。'}
    elif method=='tools/list':result={'tools':TOOLS}
    elif method=='ping':result={}
    elif method=='tools/call':
        try:result={'content':[{'type':'text','text':encode(run_tool(params.get('name'),params.get('arguments',{})))}]}
        except (ToolError,OSError,ValueError,KeyError) as exc:
            result={'isError':True,'content':[{'type':'text','text':str(exc)}]}
    else:return {'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Method not found'}}
    return {'jsonrpc':'2.0','id':message['id'],'result':result}

if __name__=='__main__':
    for line in sys.stdin.buffer:
        try:reply=dispatch(json.loads(line))
        except ValueError:continue
        if reply is not None:
            sys.stdout.buffer.write((encode(reply)+'\n').encode('utf-8'));sys.stdout.buffer.flush()
