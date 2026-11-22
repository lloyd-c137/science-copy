"""Evidence and student decisions persisted inside the versioned project card."""
import ast
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlsplit
import uuid
from datetime import datetime


class StaleProposal(ValueError):
    pass


def text(data, key, maximum=8000):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('请填写有效的' + key + '。')
    return value.strip()


def calculate(expression):
    """Evaluate numeric arithmetic only, without eval, names or executable code."""
    if not isinstance(expression, str) or len(expression) > 300:
        raise ValueError('算式过长。')
    try:
        tree = ast.parse(expression, mode='eval')
        if len(list(ast.walk(tree))) > 60:
            raise ValueError('请拆分过长的算式。')
        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return Decimal(ast.get_source_segment(expression, node))
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = visit(node.operand)
                return -value if isinstance(node.op, ast.USub) else value
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                left, right = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Add): return left + right
                if isinstance(node.op, ast.Sub): return left - right
                if isinstance(node.op, ast.Mult): return left * right
                return left / right
            raise ValueError('只支持数字、括号与加减乘除。')
        with localcontext() as context:
            context.prec = 28
            value = visit(tree.body)
            if not value.is_finite() or abs(value) > Decimal('1e100'):
                raise ValueError('计算结果超出可核对范围。')
            return str(value)
    except (SyntaxError, ArithmeticError, InvalidOperation) as error:
        raise ValueError('算式无效或不能计算。') from error


def add(card, body, author, student_messages=None):
    kind = body.get('kind')
    payload = body.get('record')
    if kind not in ('claim', 'proposal', 'support', 'session') or not isinstance(payload, dict):
        raise ValueError('请选择有效的记录类型。')
    step = payload.get('step', card['current_step'])
    if type(step) is not int or not 1 <= step <= 6:
        raise ValueError('请选择有效阶段。')
    row = dict(id='Q'+uuid.uuid4().hex[:14], kind=kind, step=step,
               created=datetime.now().astimezone().isoformat(timespec='seconds'), author=author)
    if kind == 'claim':
        row.update({key: text(payload, key) for key in ('text', 'origin', 'limitation', 'check')})
        if row['origin'] not in ('measured', 'literature', 'student', 'ai_example', 'inference'):
            raise ValueError('请选择实际的证据来源类型。')
        row['reference'] = payload.get('reference', '')
        row['location'] = payload.get('location', '')
        if not isinstance(row['reference'], str) or not isinstance(row['location'], str):
            raise ValueError('出处和位置需要文字。')
        if row['origin'] in ('measured', 'literature'):
            reference = text(payload, 'reference', 2000)
            text(payload, 'location', 2000)
            file_ids = {f['id'] for f in card.get('files', [])}
            if row['origin'] == 'measured' and any(f['id'] == reference and f.get('material_origin') == 'ai_generated' for f in card.get('files', [])):
                raise ValueError('AI 生成材料不能作为实测原始证据，请上传实际记录或标为 AI 示例。')
            link = urlsplit(reference)
            if reference not in file_ids and not (row['origin'] == 'literature' and link.scheme in ('https', 'http') and link.hostname):
                raise ValueError('实测须关联本项目材料；文献须提供原文链接或本项目材料编号。')
        if row['origin'] == 'student':
            reference = text(payload, 'reference')
            if reference not in (student_messages or {}):
                raise ValueError('学生自述须引用本项目学生原话编号。')
            row['student_quote'] = student_messages[reference]
        row['verification'] = 'recorded_not_independently_verified'
        if 'calculation' in payload:
            calc = payload['calculation']
            if not isinstance(calc, dict): raise ValueError('请提供算式、预期结果和单位。')
            expression, expected, unit = (text(calc, key, 300) for key in ('expression', 'expected', 'unit'))
            result = calculate(expression)
            try:
                expected_number = Decimal(expected)
                if not expected_number.is_finite(): raise ValueError('预期结果须为有限数字。')
            except InvalidOperation as error:
                raise ValueError('预期结果须为数字。') from error
            row['calculation'] = dict(expression=expression, expected=expected, unit=unit,
                                      result=result, passed=Decimal(result) == expected_number)
        if payload.get('supersedes'):
            prior = next((r for r in card.get('quality', {}).get('records', []) if r['id'] == payload['supersedes'] and r['kind'] == 'claim'), None)
            if not prior or prior['step'] != step:
                raise ValueError('更正须关联本项目同阶段的原主张。')
            if prior.get('calculation') and not row.get('calculation'):
                raise ValueError('更正计算记录须保留可复算的算式。')
            row['supersedes'] = prior['id']
    elif kind == 'proposal':
        row.update(text=text(payload, 'text'), reason=text(payload, 'reason'), status='pending')
        changes = payload.get('changes')
        allowed = {f['key'] for f in card['steps'][step-1]['fields']} - {'file_ids', 'papers'}
        if not isinstance(changes, dict) or not changes or set(changes)-allowed:
            raise ValueError('建议必须关联阶段中的文字字段。')
        row['changes'] = {key: text(changes, key) for key in changes}
        for key, options in (('path', ('研究型','应用型','待定')), ('tier', ('基础档','丘奖目标档','待定'))):
            if step == 3 and key in row['changes'] and row['changes'][key] not in options:
                raise ValueError('请使用有效的项目路径或目标档位。')
        row['baseline'] = {key: card['steps'][step-1]['data'].get(key, '') for key in changes}
        row['requirement_version'] = card['activity']['version']
    elif kind == 'support':
        row.update({key: text(payload, key) for key in ('concept', 'observation', 'strategy', 'outcome', 'evidence_id')})
        if row['evidence_id'] not in (student_messages or {}):
            raise ValueError('学习支持须引用本项目学生原话编号。')
        row['student_quote'] = student_messages[row['evidence_id']]
    else:
        row.update({key: text(payload, key) for key in ('settled', 'unresolved', 'next_action', 'owner')})
    records = card.setdefault('quality', {}).setdefault('records', [])
    records.append(row)
    return row


def decide(card, body):
    records = card.get('quality', {}).get('records', [])
    row = next((r for r in records if r['id'] == body.get('record_id') and r['kind'] == 'proposal'), None)
    if not row or row['status'] not in ('pending', 'deferred'):
        raise ValueError('这项建议已处理或不存在。')
    decision = body.get('decision')
    if decision not in ('accepted', 'rejected', 'deferred'):
        raise ValueError('请选择接受、拒绝或暂缓。')
    reason = text(body, 'reason')
    if decision == 'accepted':
        if body.get('confirmed') is not True:
            raise ValueError('请核对变更后确认接受。')
        data = card['steps'][row['step']-1]['data']
        if row['requirement_version'] != card['activity']['version'] or any(data.get(k, '') != v for k, v in row['baseline'].items()):
            raise StaleProposal('建议依据的成果或老师要求已有变化，请重新讨论建议。')
        data.update(row['changes'])
        if row['step'] == 1 and 'title' in row['changes']:
            card['title'] = row['changes']['title']
            if card.get('review'):
                card.setdefault('prior_reviews', []).append(card['review'])
                card['review'] = None
        if row['step'] <= card['current_step']:
            for step in card['steps'][row['step']-1:]:
                step['status'] = 'pending'
                step['cycle'] = step.get('cycle', 1)+1
            card['current_step'] = row['step']
            card['steps'][row['step']-1]['status'] = 'active'
            card.pop('milestone', None)
            card['next_action'] = '根据你接受的建议，核对受影响的成果；原材料和记录已保留。'
    row.setdefault('decisions', []).append(dict(decision=decision, reason=reason,
        at=datetime.now().astimezone().isoformat(timespec='seconds')))
    row.update(status=decision, decision_reason=reason, decided_at=row['decisions'][-1]['at'])
    return row


def guard_agent_changes(card, action, body):
    """Protect established research choices from model-only confirmation flags."""
    if action == 'revise':
        raise ValueError('请用 proposal_quality_record 保存改题建议，由学生在网站决定。')
    if action != 'progress' or not isinstance(body.get('data'), dict): return
    step = body.get('step')
    if type(step) is not int or not 1 <= step <= 6: return
    previous = card['steps'][step-1]['data']
    keys = {1: {'title', 'evidence'}, 4: {'scope', 'roles', 'criterion'}}.get(step, set())
    proposed = set()
    for row in card.get('quality', {}).get('records', []):
        if row['kind'] == 'proposal' and row['step'] == step:
            proposed.update(row.get('changes',{}))
    if any(key in body['data'] and (key in proposed or previous.get(key) not in (None, '')) and body['data'][key] != previous.get(key, '') for key in keys | proposed):
        raise ValueError('研究问题或范围已有选择，请先保存修改建议，由学生在网站决定。')


def markdown(card):
    records = card.get('quality', {}).get('records', [])
    if not records: return ''
    lines = ['# 依据与选择', '记录中的核对说明是提交者的核对记录；只有算术结果由程序复算，输入及单位仍需核对。']
    import json
    for row in records:
        lines += ['', '## '+row['id']+' · '+row['kind'], json.dumps(row, ensure_ascii=False, indent=2)]
    return '\n'.join(lines)


def unresolved_calculations(card, step):
    records = card.get('quality', {}).get('records', [])
    replaced = {r.get('supersedes') for r in records}
    return [r['id'] for r in records if r['kind'] == 'claim' and r['id'] not in replaced
            and (step == 6 or r['step'] == step) and r.get('calculation', {}).get('passed') is False]
