"""Read a fresh, validated launch configuration for each background preparation."""
import json
import hashlib
import os
import tempfile
from threading import RLock
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name('runtime-config.json')
EFFORTS = {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}
CONFIG_LOCK = RLock()


def public_config(path=None):
    path = Path(path) if path else CONFIG_PATH
    with CONFIG_LOCK:
        roles = {role: load_launch_config(role, path) for role in ('student', 'teacher')}
        revision = hashlib.sha256(path.read_bytes()).hexdigest()
        return dict(roles={role: {key: value[key] for key in ('model', 'reasoning_effort')}
                           for role, value in roles.items()}, revision=revision)


def save_defaults(body, path=None):
    """Publish both role defaults atomically; reject stale browser forms."""
    path = Path(path) if path else CONFIG_PATH
    with CONFIG_LOCK:
        current = public_config(path)
        if body.get('revision') != current['revision']:
            raise ValueError('配置已被更新，请刷新后再保存。')
        model, effort = body.get('model'), body.get('reasoning_effort')
        if not isinstance(model, str) or not model or len(model) > 120 or any(c.isspace() for c in model):
            raise ValueError('请填写无空白的模型标识。')
        if not isinstance(effort, str) or effort not in EFFORTS:
            raise ValueError('请选择有效的推理强度。')
        data = {role: load_launch_config(role, path) for role in ('student', 'teacher')}
        for settings in data.values():
            settings.update(model=model, reasoning_effort=effort)
        descriptor, name = tempfile.mkstemp(prefix='.runtime-', suffix='.json', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return public_config(path)


def load_launch_config(role, path=None):
    path = Path(path) if path is not None else CONFIG_PATH
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or set(data) != {'student', 'teacher'}:
            raise ValueError('顶层必须包含且仅包含 student、teacher')
        for name, settings in data.items():
            required={'model', 'reasoning_effort', 'prepare_timeout_seconds'}
            optional={'e_draft_timeout_retries'} if name=='student' else set()
            if not isinstance(settings, dict) or not required<=set(settings) or set(settings)-required-optional:
                raise ValueError(f'{name} 必须包含 model、reasoning_effort、prepare_timeout_seconds，且不能有未知字段')
            retries=settings.get('e_draft_timeout_retries',0)
            if type(retries) is not int or retries not in (0,1):
                raise ValueError('e_draft_timeout_retries 必须为 0 或 1')
            model = settings['model']
            if not isinstance(model, str) or not model.strip() or model != model.strip() or any(c.isspace() for c in model):
                raise ValueError(f'{name}.model 必须是无空白的模型标识')
            effort = settings['reasoning_effort']
            if not isinstance(effort, str) or effort not in EFFORTS:
                raise ValueError(f'{name}.reasoning_effort 无效，可选：{", ".join(sorted(EFFORTS))}')
            timeout = settings['prepare_timeout_seconds']
            if type(timeout) is not int or not 30 <= timeout <= 3600:
                raise ValueError(f'{name}.prepare_timeout_seconds 必须是 30～3600 的整数')
        if role not in data:
            raise ValueError(f'未知角色：{role}')
        return dict(data[role])
    except (OSError, ValueError) as error:
        raise RuntimeError(f'启动配置错误（{path.name}）：{error}') from error
