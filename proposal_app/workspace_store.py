"""Student-selected project folders, separate from the service's private state."""
import ctypes
import json
import os
from pathlib import Path
import re
import threading
import subprocess
import sys
import uuid


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_name(text):
    text=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(text)).strip(' .')[:48]
    return text or '学生'


class WorkspaceStore:
    def __init__(self, registry):
        self.registry=Path(registry)
        self.lock=threading.RLock()
        try:
            self.data=json.loads(self.registry.read_text('utf-8'))
        except FileNotFoundError:
            self.data={'projects':{},'preferences':{}}

    def recommendation(self, user):
        previous=self.data['preferences'].get(user)
        if previous:
            return previous
        base=Path.home()/'Documents'
        if os.name=='nt' and Path('D:/').is_dir() and ctypes.windll.kernel32.GetDriveTypeW('D:\\')==3:
            # Do not probe-drive by creating files before the student chooses it.
            if os.access('D:/',os.W_OK):
                base=Path('D:/')
        return str(base/'探月科研课程'/'开题')

    def get(self, user, project):
        with self.lock:
            entry=self.data['projects'].get(project)
            return dict(entry) if entry and entry['user']==user else None

    def visible(self, user, project):
        entry=self.get(user,project)
        return Path(entry['path']) if entry else None

    def internal(self, user, project):
        root=self.visible(user,project)
        return root/'.coach' if root else self.registry.parent/(self.registry.stem+'.pending')/user/project

    def describe(self, card):
        entry=self.get(card['student_id'],card['id'])
        return {'configured':bool(entry),'path':entry['path'] if entry else '',
                'recommended':self.recommendation(card['student_id']),
                'folder_name':Path(entry['path']).name if entry else safe_name(card['student_name'])+'-开题项目'}

    def select(self, card, parent):
        if not isinstance(parent,str) or not parent.strip():
            raise ValueError('请选择存放项目的文件夹。')
        base=Path(parent.strip()).expanduser()
        if not base.is_absolute() or str(base).startswith(('\\\\','//')):
            raise ValueError('请填写本机的完整文件夹路径，例如 D:\\探月科研课程\\开题。')
        if os.name=='nt' and (':' in str(base)[2:] or any(c in str(base) for c in '<>"|?*')):
            raise ValueError('文件夹路径包含不能使用的字符。')
        base=base.resolve()
        with self.lock:
            existing=self.get(card['student_id'],card['id'])
            if existing:
                if Path(existing['base'])!=base:
                    raise ValueError('这个项目已经有存储位置；新项目可以重新选择。')
                return self.describe(card)
            target=base/self.describe(card)['folder_name']
            # Existing directories are reusable only after our own interrupted setup,
            # with the exact project identity. Unknown student folders stay untouched.
            base.mkdir(parents=True,exist_ok=True)
            identity={'project':card['id'],'user':card['student_id']}
            folder_name=target.name
            number=1
            while target.exists():
                try:
                    saved=json.loads((target/'.coach'/'identity.json').read_text('utf-8'))
                except (OSError,ValueError):
                    saved=None
                if saved==identity:
                    break
                number+=1
                target=base/(folder_name+'-'+str(number))
            if not target.exists():
                staging=base/('.'+target.name+'-'+uuid.uuid4().hex+'.setup')
                staging.mkdir()
                try:
                    for name in ('.coach','我的笔记','文献','阶段成果','学习记录','研究过程'):
                        (staging/name).mkdir()
                    atomic_json(staging/'.coach'/'identity.json',identity)
                    staging.rename(target)
                except Exception:
                    # Remove only the known files/empty directories created by this call.
                    (staging/'.coach'/'identity.json').unlink(missing_ok=True)
                    for name in ('我的笔记','文献','阶段成果','学习记录','研究过程','.coach'):
                        directory=staging/name
                        if directory.is_dir():
                            try: directory.rmdir()
                            except OSError: pass
                    try: staging.rmdir()
                    except OSError: pass
                    raise
            entry={'user':card['student_id'],'base':str(base),'path':str(target)}
            updated=json.loads(json.dumps(self.data))
            updated['projects'][card['id']]=entry
            updated['preferences'][card['student_id']]=str(base)
            atomic_json(self.registry,updated)
            self.data=updated
            return self.describe(card)

    def open(self, card):
        path=self.visible(card['student_id'],card['id'])
        if path is None or not path.is_dir():
            raise ValueError('项目文件夹还未设置，或已被移动。')
        if os.name!='nt':
            raise ValueError('请在文件管理器中打开显示的项目路径。')
        os.startfile(str(path))

    def pick(self, user):
        initial=Path(self.recommendation(user))
        while not initial.exists() and initial!=initial.parent:
            initial=initial.parent
        script=('import tkinter as tk; from tkinter import filedialog; import json,sys; '
                'root=tk.Tk(); root.withdraw(); root.attributes("-topmost",True); '
                'value=filedialog.askdirectory(parent=root,title="选择研究项目存放位置",initialdir=sys.argv[1]); '
                'root.destroy(); print(json.dumps(value))')
        result=subprocess.run([sys.executable,'-c',script,str(initial)],capture_output=True,text=True,
                              encoding='utf-8',timeout=600,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:
            raise ValueError('暂时无法打开文件夹选择器，也可以直接填写路径。')
        return json.loads(result.stdout)
