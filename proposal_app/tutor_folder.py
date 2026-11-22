"""Opt-in, folder-scoped shared hooks. No user-wide hooks are installed."""
import json
from pathlib import Path

MANIFEST = '.tanyue-coach/folder.json'

def shared_root(folder):
    folder = Path(folder).resolve()
    for candidate in (folder, *folder.parents):
        manifest = candidate / MANIFEST
        if manifest.is_file():
            try:
                value = json.loads(manifest.read_text('utf-8'))
                configured = json.loads((candidate/'.codex/hooks.json').read_text('utf-8'))
                if value.get('format') != 1 or Path(value['root']).resolve() != candidate:
                    return None
                if not (candidate/'.git').exists():
                    return None
                # A marked folder alone is insufficient: both actual hook definitions
                # and their launcher must exist before suppressing project-local hooks.
                command = value['command']
                if not (candidate/'.tanyue-coach/runtime/folder_hook.py').is_file():
                    return None
                for event in ('SessionStart', 'UserPromptSubmit'):
                    if not any(h.get('command') == command for g in configured.get('hooks',{}).get(event,[])
                               for h in g.get('hooks',[])):
                        return None
                return candidate
            except (OSError, ValueError, KeyError, TypeError):
                return None
        if (candidate/'.git').exists():
            return None  # An independent child repository is another native root.
    return None

def project_folder(cwd, root):
    """Resolve only the active project's ancestors, never search sibling projects."""
    root = Path(root).resolve()
    cwd = Path(cwd).resolve()
    if not cwd.is_relative_to(root) or cwd == root:
        return None
    for candidate in (cwd, *cwd.parents):
        if candidate == root:
            break
        if (candidate/'.coach/identity.json').is_file():
            return candidate
    return None
