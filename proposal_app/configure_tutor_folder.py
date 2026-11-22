"""Manual configuration utility; does not install software or auto-trust hooks."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

RUNTIME = ('folder_hook.py','tutor_folder.py','tutor_runtime.py','workspace_store.py',
           'coach_mcp.py','context_archive.py','readable_archive.py')

def configure(folder, source=None):
    root = Path(folder).expanduser().resolve()
    if not root.is_dir() or root == Path(root.anchor) or root == Path.home().resolve():
        raise ValueError('请选择专门存放科研项目的总文件夹，不要选择磁盘根目录或个人主目录。')
    source = Path(source or Path(__file__).parent)
    marker = root/'.tanyue-coach/folder.json'
    hooks_file = root/'.codex/hooks.json'
    if hooks_file.exists() and not marker.exists():
        raise ValueError('此文件夹已有其他钩子配置，请先由维护者合并，程序不会覆盖。')
    nested = [p for p in root.rglob('.git') if p != root/'.git']
    if nested:
        raise ValueError('以下子项目有独立仓库，会截断共享钩子；请先由维护者处理：'+str(nested[0].parent))
    if marker.exists():
        old = json.loads(marker.read_text('utf-8'))
        if Path(old['root']).resolve() != root:
            raise ValueError('科研总文件夹已移动，需要重新配置并在 Codex 中重新确认信任。')
        if hooks_file.exists():
            current=json.loads(hooks_file.read_text('utf-8')).get('hooks',{})
            if set(current) != {'SessionStart','UserPromptSubmit'} or any(
                    len(groups)!=1 or len(groups[0].get('hooks',[]))!=1 or
                    groups[0]['hooks'][0].get('command')!=old.get('command')
                    for groups in current.values()):
                raise ValueError('钩子文件已包含其他修改，请由维护者合并，程序不会覆盖。')
    # Validate every dependency before changing the selected folder.
    payload = {name:(source/name).read_bytes() for name in RUNTIME}
    binary = sys.executable
    parts = [binary, '-X', 'utf8', str(root/'.tanyue-coach/runtime/folder_hook.py')]
    command = subprocess.list2cmdline(parts) if sys.platform=='win32' else shlex.join(parts)
    hooks = {'hooks':{event:[{'hooks':[{'type':'command','command':command,'timeout':25,
                                      'additionalContextLimit':20000}]}]
                      for event in ('SessionStart','UserPromptSubmit')}}
    runtime = root/'.tanyue-coach/runtime'; runtime.mkdir(parents=True,exist_ok=True)
    for name,data in payload.items():
        path=runtime/name
        if not path.exists() or path.read_bytes()!=data:
            path.write_bytes(data)
    # Minimal valid, empty Git repository: native Codex uses it to discover the
    # common root. No commits, remotes, uploads, or changes to child documents.
    git = root/'.git'
    if not git.exists():
        for child in ('objects/info','objects/pack','refs/heads','refs/tags','info'):
            (git/child).mkdir(parents=True,exist_ok=True)
        (git/'HEAD').write_text('ref: refs/heads/main\n','utf-8')
        (git/'config').write_text('[core]\n\trepositoryformatversion = 0\n\tbare = false\n','utf-8')
        (git/'info/exclude').write_text('*\n','utf-8')
    hooks_file.parent.mkdir(exist_ok=True)
    hooks_file.write_text(json.dumps(hooks,ensure_ascii=False,indent=2)+'\n','utf-8')
    marker.write_text(json.dumps({'format':1,'root':str(root),'command':command,
        'files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}},ensure_ascii=False,indent=2),'utf-8')
    return root

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',nargs='?')
    args=parser.parse_args()
    folder=args.folder
    if not folder:
        if sys.platform == 'darwin':
            result=subprocess.run(['/usr/bin/osascript','-e',
                'POSIX path of (choose folder with prompt "选择科研总文件夹（例如：探月科研课程/开题）")'],
                capture_output=True,text=True,encoding='utf-8')
            if result.returncode:
                if '(-128)' in result.stderr:return
                raise ValueError('无法打开文件夹选择框：'+result.stderr.strip())
            folder=result.stdout.strip()
        else:
            import tkinter as tk
            from tkinter import filedialog
            window=tk.Tk();window.withdraw()
            folder=filedialog.askdirectory(title='选择科研总文件夹（例如：探月科研课程/开题）')
            window.destroy()
        if not folder:return
    root=configure(folder)
    print('文件已配置：'+str(root))
    print('下一步：在 Codex 打开这个总文件夹，进入 设置 → 钩子，信任该路径下的两个科研钩子。')
    print('然后从网站打开具体科研项目。不要在子项目内重新配置；不要移动已配置总文件夹。')
    print('本程序没有自动记录信任。')

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('配置未完成：'+str(error),file=sys.stderr)
        raise SystemExit(1)
