"""Build a portable magazine from the edited Markdown; no third-party dependencies."""
from pathlib import Path
import base64
import html
import json
import re

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
SOURCE = DOCS / '开题手记-设计思路与师生使用指南.md'

def inline(text):
    text = html.escape(text)
    text = re.sub(r'\[([^\]\n]+)\]\((([\w-]+/)*[\w-]+\.md)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text

def markdown(text):
    lines = text.strip().splitlines()
    output = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s == '---':
            i += 1
            continue
        if s.startswith('```'):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i]); i += 1
            output.append('<details class="text-route"><summary>查看完整操作路径</summary><pre>' + html.escape('\n'.join(block)) + '</pre></details>')
            i += 1
            continue
        if s.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = lines[i].strip()
                if not re.match(r'^\|[\s:|\-]+$', row):
                    rows.append([inline(c.strip()) for c in row.strip('|').split('|')])
                i += 1
            output.append('<div class="table-scroll" tabindex="0" role="region" aria-label="内容对照表，可横向滚动"><table><thead><tr>' + ''.join('<th scope="col">'+c+'</th>' for c in rows[0]) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+c+'</td>' for c in row)+'</tr>' for row in rows[1:])+'</tbody></table></div>')
            continue
        image = re.match(r'!\[(.*?)\]\((.*?)\)', s)
        if image:
            alt, file = image.groups()
            uri = 'data:image/png;base64,' + base64.b64encode((DOCS / file).read_bytes()).decode()
            output.append(f'<figure class="screen"><button class="zoom" aria-label="放大{html.escape(alt)}"><img src="{uri}" alt="{html.escape(alt)}" loading="lazy"><span>↗ 点击放大界面</span></button></figure>')
        elif s.startswith('### '):
            output.append('<h3>'+inline(s[4:])+'</h3>')
        elif s.startswith('- '):
            items = []
            while i < len(lines) and lines[i].strip().startswith('- '):
                items.append('<li>'+inline(lines[i].strip()[2:])+'</li>'); i += 1
            output.append('<ul>'+''.join(items)+'</ul>')
            continue
        else:
            output.append('<p>'+inline(s)+'</p>')
        i += 1
    return '\n'.join(output)

titles = ['想解决什么问题','为什么这样设计','一个项目怎样走完','系统是怎么配合的','学生怎么用','老师怎么用','用 CO₂ 案例过一遍完整流程']
shorts = ['需求','设计','流程','架构','学生指南','老师指南','案例']
english = ['THE QUESTION','DESIGN PRINCIPLES','THE RESEARCH JOURNEY','TWO WORLDS, ONE PROJECT','FOR STUDENTS','FOR TEACHERS','FROM IDEA TO ACTION']
notes = ['从一个生活观察开始，找到真正能研究的问题。','把讨论留下来，让每个选择都有理由。','六个阶段，三种审阅走向。点击节点，看证据怎样积累。','本地助手负责探索与动手，网站负责组织与协作。','先看任务，再去讨论。核对成果，接着往下做。','看进度、查证据，把意见写成可执行的下一步。','把学生、AI、老师的工作，放回同一段研究经历。']
source = SOURCE.read_text(encoding='utf-8-sig')
parts = re.split(r'^## [一二三四五六七]、[^\n]+\n', source, flags=re.M)
assert len(parts) == 8, 'Expected seven document sections'
intro = re.sub(r'^#{1,2}[^\n]*\n', '', parts[0], flags=re.M).strip()
nav = ''.join(f'<a href="#section-{n}" aria-label="{n:02d} {titles[n-1]}"><span>{n:02d}</span>{shorts[n-1]}</a>' for n in range(1,8))
sections = []
for n, body in enumerate(parts[1:], 1):
    diagram = (HERE/'flow.html').read_text(encoding='utf-8') if n == 3 else (HERE/'architecture.html').read_text(encoding='utf-8') if n == 4 else ''
    sections.append(f'<section class="chapter" id="section-{n}" aria-labelledby="heading-{n}"><header class="chapter-head"><span class="chapter-number">{n:02d}</span><div><p class="eyebrow">{english[n-1]}</p><h2 id="heading-{n}">{titles[n-1]}</h2></div></header>{diagram}<div class="reading-grid"><aside class="margin-note"><span>FIELD NOTE / {n:02d}</span><p>{notes[n-1]}</p><div class="note-line"></div></aside><div class="prose">{markdown(body)}</div></div></section>')

hero = '''<header class="cover" id="top">
<div class="cover-meta"><span>RESEARCH × AI × EDUCATION</span><span>开题辅导 · 设计与使用特刊</span></div>
<div class="cover-grid"><div class="cover-copy"><p class="eyebrow"><i></i> 从一个好问题开始</p><h1>让好奇心，<br>成为<span>研究。</span></h1><p class="cover-deck">开题手记<br><span>设计思路与师生使用指南</span></p><a class="start" href="#section-1">开始阅读 <span>↘</span></a></div>
<figure class="cover-art" aria-label="教室、开窗与 CO₂ 观测的示意插画，不代表实际测量结果">
<div class="art-top"><span>FIELD STUDY 001</span><span class="art-tag">CO₂</span></div>
<svg viewBox="0 0 540 400" role="img" aria-label="从教室观察到研究问题的空间示意图"><defs><pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#a6b3bc" opacity=".5"/></pattern></defs><rect width="540" height="400" fill="url(#dots)"/>
<g fill="none" stroke="#203b50" stroke-width="1.5"><path d="M95 260 290 355 465 255 270 160Z" fill="#e6ebea"/><path d="M95 260V100L270 10V160" fill="#f7f6ef"/><path d="M270 10 465 106V255L270 160" fill="#d8e2e6"/><path d="M120 120 175 91V169L120 198Z" fill="#b9d1fa"/><path d="M184 86 241 56V135L184 164Z" fill="#f9f9f3"/><path d="M184 86 218 110V188L184 164Z" fill="#8db1ed"/><path d="M321 93 414 139V178L321 132Z" fill="#fbfaf4"/>
<g fill="#c2d0d6"><path d="M160 231 205 252 238 233 194 211Z"/><path d="M245 272 289 293 322 274 278 252Z"/><path d="M263 211 307 232 340 213 296 191Z"/></g><path d="M160 231V257M205 252V277M238 233V259M245 272V298M289 293V320M322 274V300M263 211V235M307 232V255M340 213V235"/>
<path d="M374 229 397 240V274L374 263Z" fill="#ff6c35"/><path d="m379 238 12 6v12l-12-6Z" fill="#fff2d8"/>
<path d="M92 154C143 122 165 189 230 168S327 142 371 191" stroke="#2468f4" stroke-width="3" stroke-dasharray="8 6" class="airflow"/><circle cx="230" cy="168" r="5" fill="#2468f4" stroke="none"/><path d="M381 250H489M165 91V37H90" stroke="#f56635"/></g><g font-family="sans-serif" font-size="12" fill="#203b50"><text x="414" y="239">记录仪</text><text x="26" y="41">开窗条件</text><text x="28" y="340" font-size="11" letter-spacing="2">OBSERVE → ASK → TEST</text></g></svg>
<figcaption><span>“下午教室有点闷。”</span><p>一个观察，可以走多远？</p><small>教学案例示意 / 非实测数据</small></figcaption></figure></div>
<div class="cover-bottom"><span>01—07 / 从问题到开题</span><p>学生提出问题 · AI 协助探索 · 老师作出判断</p><span>向下探索 ↓</span></div></header>'''

template = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>开题手记｜从好奇心到研究 · 设计与使用特刊</title><style>__CSS__</style></head><body><a class="skip" href="#section-1">跳到正文</a><div class="progress" aria-hidden="true"><div></div></div><nav class="masthead" aria-label="章节导航"><a class="brand" href="#top"><b>研<span>·</span></b> 开题手记 <small>FIELDNOTES</small></a><button class="menu-toggle" aria-expanded="false" aria-controls="chapters">目录 ＋</button><div class="nav-links" id="chapters">__NAV__</div><button class="motion-toggle" aria-pressed="false" title="暂停或启用图解动效">动效 开</button></nav><main>__HERO__<div class="intro"><span class="eyebrow">EDITOR’S NOTE / 卷首语</span><p>__INTRO__</p></div>__SECTIONS__<footer><a class="footer-brand" href="#top">开题手记 ↗</a><p>从一个模糊的兴趣，到一件能动手做的事。</p><div><span>RESEARCH BEGINS WITH A QUESTION.</span><button id="print">打印 / 保存 PDF</button><a href="#top">回到封面 ↑</a></div></footer></main><dialog id="image-dialog" aria-label="应用界面大图"><button id="close-image" autofocus>关闭 ×</button><img alt=""></dialog><script>__JS__</script></body></html>'''
result = template.replace('__CSS__',(HERE/'magazine.css').read_text(encoding='utf-8') + (HERE/'refinement.css').read_text(encoding='utf-8')).replace('__JS__',(HERE/'magazine.js').read_text(encoding='utf-8')).replace('__NAV__',nav).replace('__HERO__',hero).replace('__INTRO__',inline(intro)).replace('__SECTIONS__','\n'.join(sections))
target = DOCS/'开题手记.html'
target.write_text(result, encoding='utf-8')
print(json.dumps({'output':str(target),'bytes':target.stat().st_size,'sections':len(sections)},ensure_ascii=False))
