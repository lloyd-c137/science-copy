"""Generate a project-only capability profile; never edit the user's global config."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib


def profile(root, home=None):
    root = Path(root).resolve()
    home = Path(home or Path.home())
    skill = root / '.agents/skills/research-proposal-coach/SKILL.md'
    lines = ['# Managed research-project runtime; global settings remain untouched.',
             '[features]', 'apps = false',
             '[skills]', 'include_instructions = false', 'bundled.enabled = false']
    paths = set()
    for base in (home / '.agents/skills', home / '.codex/skills', root / '.agents/skills'):
        if base.is_dir():
            paths.update(base.rglob('SKILL.md'))
    for path in sorted(paths, key=str):
        lines += ['[[skills.config]]', 'path = ' + json.dumps(str(path.resolve()), ensure_ascii=False),
                  'enabled = ' + ('true' if path.resolve() == skill.resolve() else 'false')]
    lines += ['[plugins._default]', 'enabled = false']
    global_config = home / '.codex/config.toml'
    config = tomllib.loads(global_config.read_text('utf-8')) if global_config.exists() else {}
    # Explicit plugin enables override defaults, so suppress those in this project too.
    for name in sorted(config.get('plugins', {})):
        if name != '_default':
            lines += ['[plugins.' + json.dumps(name) + ']', 'enabled = false']
    for name in sorted(config.get('mcp_servers', {})):
        if name != 'proposal_coach':
            lines += ['[mcp_servers.' + json.dumps(name) + ']', 'enabled = false']
    command = subprocess.list2cmdline([sys.executable, '-X', 'utf8', str(Path(__file__).with_name('tutor_runtime.py'))])
    try:
        from .tutor_folder import shared_root
    except ImportError:
        from tutor_folder import shared_root
    for event in (() if shared_root(root) else ('UserPromptSubmit', 'SessionStart')):
        lines += [f'[[hooks.{event}]]', f'[[hooks.{event}.hooks]]', 'type = "command"',
                  'command = ' + json.dumps(command), 'timeout = 25', 'additionalContextLimit = 20000']
    return '\n'.join(lines) + '\n'
