"""Render the research view without editing student-authored files."""
import io
import json
import zipfile
from pathlib import Path

CHAPTERS = {
    'Introduction': ('curiosity', 'topic', 'question', 'problem'),
    'Literature Review': ('search',),
    'Research Question / Hypothesis': ('rq', 'hypothesis'),
    'Methods': ('method',),
    'Discussion / Limitations': ('check', 'defense'),
}
PROPOSAL_LABELS={'background':'研究背景与核心困惑','literature':'文献比较与搜索诊断','question':'研究问题、解释与预测','method':'研究方法','validation':'关键验证与可行性','limits':'局限与备择解释','references':'参考资料'}


def text(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def documents(card):
    research = card.get('research', {})
    if not research:
        return {}
    objects = research.get('objects', [])
    lines = ['# 研究对象与版本', '']
    for obj in objects:
        lines += [f"## {obj['kind']} · {obj['id']} v{obj['revision']}",
                  f"状态：{obj['status']}" + ('；需要复核' if obj.get('needs_review') else ''),
                  '```json', text(obj.get('content', {})), '```', '']
    lines += ['## 关系及来源', '```json', text(research.get('links', [])), '```']
    mapping = ['# 后续报告章节映射', '以下是开题过程与研究计划，不是正式研究结果。', '']
    for chapter, kinds in CHAPTERS.items():
        refs = [f"{o['id']} v{o['revision']}（{o['status']}）" for o in objects if o['kind'] in kinds]
        mapping += ['## ' + chapter, '\n'.join('- ' + ref for ref in refs) or '尚未形成。', '']
    mapping += ['## Results', '仅可引用明确标记为开题小试的实际材料；正式研究结果尚待开展。',
                '## References', text(card.get('materials', []))]
    output = {'研究过程/研究对象与版本.md': '\n'.join(lines),
              '研究过程/报告章节映射.md': '\n'.join(mapping),
              '研究过程/对象事件.md': '# 研究过程事件\n\n```json\n' + text(research.get('events', [])) + '\n```',
              '研究过程/研究档案.json': text(research)}
    for index, item in enumerate(research.get('deliverables', []), 1):
        # Do not use user strings as export path components.
        lines=['# 开题计划',f"版本：{item['id']} · 第 {item['revision']} 版",'']
        for key,label in PROPOSAL_LABELS.items():
            lines+=['## '+label,str(item.get('chapters',{}).get(key,'')),'']
        lines+=['## 本版依据','活动要求版本：'+str(item.get('activity_version',''))]
        lines += [f"- {r['id']} · 第 {r['revision']} 版" for r in item.get('object_refs',[])]
        output[f'Proposal/提交版本-{index:03}.md'] = '\n\n'.join(lines)
    return output


def bundle(card, root=None, attachments=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in documents(card).items():
            archive.writestr(name, content.encode('utf-8'))
        archive.writestr('资料索引.json', text({'files': card.get('files', []), 'materials': card.get('materials', [])}))
        if root:
            root=Path(root).resolve()
            try:
                manifest=json.loads((root/'.coach/readable-manifest.json').read_text('utf-8')).get('files',{})
            except (OSError,ValueError): manifest={}
            for relative in sorted(set(manifest.values())):
                candidate=root/relative
                try:
                    archive_path=candidate.resolve().relative_to(root).as_posix()
                    if candidate.is_file() and not candidate.is_symlink():
                        archive.writestr('本地成果/'+archive_path,candidate.read_bytes())
                except (OSError,ValueError): continue
        for index, item in enumerate(attachments,1):
            name=str(item['name']).replace('\\','/').rsplit('/',1)[-1]
            archive.writestr(f'附件/{index:03}-{name}',item['content'])
    return stream.getvalue()
