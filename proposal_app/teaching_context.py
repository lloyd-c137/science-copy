"""A compact, explicit contract delivered with every live project read."""
from pathlib import Path


def empty_opening(skill_dir=None):
    source = Path(skill_dir) if skill_dir else Path(__file__).resolve().parent.parent / 'skills/research-proposal-coach'
    text = (source / 'SKILL.md').read_text('utf-8')
    return text.split('<!-- EMPTY_PROJECT_OPENING -->',1)[1].split('<!-- /EMPTY_PROJECT_OPENING -->',1)[0].strip()


BRIEFS = [
    ("A 兴趣探索与问题积累", "澄清兴趣、比较方向并试聊。总结后明确问学生是否选定；确定后把观察、主问题、已选子问题、已谈清的方案与首测、选择理由一并保存为网页草稿。"),
    ("B 形成核心 Problem", "帮助学生区分问法、解释归组理由与竞争解释；AI分组先保存候选，由学生在网站有理由地选择，不以文献空白为唯一门槛。"),
    ("C 搜索诊断与假设发展", "实际检索并记录改词、筛选、理解变化；学生指出至少两篇独立来源各一处已读原文，比较支持与限制，形成有边界的RQ与解释/预测；无适用来源请老师协助定位适用材料，条件不足保持进行中。"),
    ("D 研究框架与关键验证", "导师先分别评估学习价值、实际价值、研究贡献，给当前建议、证据、不确定性及1至2条提升路径。核实当前活动预算内的范围、方法判别力和关键资源；学生先提小试预测或方案。热情不是新证据；关键缺口不留到正式研究后才查。"),
    ("E Proposal 与答辩准备", "按当前已确认对象版本组织交付，清理旧条件；记录学生实际答辩与依据，复述不等于迁移。E只准备，不自动提交；根本缺口回D局部复核。"),
    ("F 老师审阅与开题决定", "学生本人在网站核对固定Proposal版本并最终提交，review仅表示待审阅；老师本人发布才是正式决定，AI草稿和confirmed不能替代。"),
]


ACTIVITIES = {
    "observation": ("观察与兴趣积累", "从亲历场景辨认观察、感受和待澄清的兴趣。", "A"),
    "curiosity": ("兴趣与困惑积累", "辨认学生真正在意的困惑与可试的不同方向。", "A"),
    "topic": ("主题辨认与归组", "比较已有主题及其问题的联系，说明归组依据；归属或核心方向的选择由本人在网站决定。", "B"),
    "question": ("问法辨认与比较", "比较这些问法各自想知道什么。", "A/B"),
    "problem": ("核心 Problem 归组与重审", "从已有问题解释归组理由，比较竞争解释；文献可以支持、挑战或限制Problem，改动先存候选并由本人选择。", "B"),
    "search": ("检索诊断与改词", "实际搜索，依据结果调整关键词并记录理解变化；取得并用于讨论的来源另存source。", "C"),
    "source": ("来源共读与证据比较", "定位实际读到的原文，比较来源支持与限制；保留至少两篇独立来源的学生共读要求。", "C"),
    "rq": ("研究问题与边界", "根据核心困惑和证据明确RQ的对象、条件与可回答范围，不把未证实解释写成结论。", "C"),
    "hypothesis": ("解释、预测与竞争解释", "请学生提出解释与可区分预测，比较替代解释并明确scope适用边界；非适用类型说明理由。", "C"),
    "method": ("方法设计与判别力", "请学生先提方案或小试预测，判断方法能否回答RQ、区分竞争解释及结论边界，核实当前预算与关键资源。", "D"),
    "check": ("推理链一致性核对", "核对当前相连RQ、假设与方法及版本；分别保存RQ匹配、竞争解释判别力和结论边界的有依据判断，结构检查不代替科学判断。", "D"),
    "proposal": ("Proposal组织与版本核对", BRIEFS[4][1], "E"),
    "defense": ("答辩与独立理解", "围绕固定Proposal版本记录学生实际回答及依据，复述不等于迁移；根本缺口回相关活动复核。", "E"),
    "review": ("老师审阅与补证", BRIEFS[5][1], "F"),
    "value_judgment": ("价值判断与范围提升", BRIEFS[3][1], "D"),
    "critical_validation": ("关键验证与小试", "让学生先提出检查办法和结果预测，核实最可能改变研究范围的未知项；只确认实际证据支持的范围，缺口未补不完成。", "D"),
    "revision": ("修订方案与局部复核", "依据新证据说明原判断哪一处需要调整，保留仍有效成果；重要修订先存候选，由本人网站选择，只复核受影响部分。", "D/E"),
}
ACTIVITY_ALIASES = {
    'divergence': 'question', 'questioning': 'question', 'grouping': 'problem',
    'search_diagnosis': 'search', 'searching': 'search', 'reading': 'source',
    'hypothesis_development': 'hypothesis', 'prediction': 'hypothesis', 'reasoning': 'hypothesis',
    'method_comparison': 'method', 'alignment': 'check',
}


def current_activity(card):
    """Persisted choices outrank focus; an injected default is not a choice."""
    state = card.get('research_state') or {}
    research = card.get('research') or {}
    explicit = state.get('tutor_mode') or research.get('tutor_mode')
    mode = explicit
    focus_id = state.get('focus_object_id') or research.get('focus_object_id') or card.get('focus_object_id')
    if not mode and focus_id:
        mode = next((o.get('kind') for o in research.get('objects', []) if o.get('id') == focus_id), None)
    if not mode and card.get('tutor_mode') != 'observation':
        mode = card.get('tutor_mode')
    stage = card.get('current_step', 1)
    activity_key = ACTIVITY_ALIASES.get(mode, mode)
    if activity_key in ACTIVITIES:
        purpose, judgment, section = ACTIVITIES[activity_key]
    else:
        purpose, judgment = BRIEFS[stage - 1]
        section = 'ABCDEF'[stage - 1]
    return {'purpose': purpose, 'required_judgment': judgment, 'activity_mode': mode or None,
            'focus_object_id': focus_id, 'activity_reference': 'workflow: ' + section,
            'navigation_stage': stage}


def brief(card):
    """Route to the current activity; cross-stage procedures live in the role Skill."""
    return {**current_activity(card),
            "rules_source": "按已安装的学生教练 Skill 推进，按 activity_reference 定位活动参考。"}
