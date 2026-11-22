"""Build the two configuration ZIPs and their shared offline HTML guide."""
from pathlib import Path
import zipfile

from proposal_app.configure_tutor_folder import RUNTIME

APP=Path(__file__).resolve().parent
OUT=APP.parent/'deliverables'
WINDOWS='''@echo off\r
cd /d "%~dp0"\r
where py >nul 2>nul\r
if errorlevel 1 (\r
  python configure_tutor_folder.py\r
) else (\r
  py -3 configure_tutor_folder.py\r
)\r
pause\r
'''
MAC='''#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python_bin=""
for candidate in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  candidate_path=$(command -v "$candidate" 2>/dev/null) || continue
  if "$candidate_path" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    python_bin="$candidate_path"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  printf '%s\n' '未找到 Python 3.11 或以上版本。请老师先准备能运行本地科研工作台的环境。'
  read -r '?按回车关闭窗口。'
  exit 1
fi
"$python_bin" configure_tutor_folder.py
result=$?
read -r '?按回车关闭窗口。'
exit "$result"
'''

def build():
    OUT.mkdir(exist_ok=True)
    for platform, launcher, content in [('windows','Windows-配置.cmd',WINDOWS),('macos','macOS-配置.command',MAC)]:
        readme=f'''探月科研文件夹配置 · {platform}

先解压全部文件，再双击 {launcher}，选择科研总文件夹。
看到“文件已配置”后，在 Codex 打开该总文件夹，进入 设置 → 钩子，信任对应路径下的两个钩子。
然后从网站打开具体科研项目；以后同一总文件夹中的普通新项目无需重复配置。

前提：电脑已能运行配套版本的本地科研工作台，已有 Python 3.11+；Codex 已安装并登录。
不包含 Python、Codex 或网站服务，不是独立安装包。
配置仅写所选总文件夹，不写全局钩子、不自动记录信任、不上传研究资料。
不要移动已配置的总文件夹；子项目若有独立 Git 仓库，程序会停止，请维护者处理。
若系统不允许打开启动文件，或程序报错，保留提示交给维护者处理。
Windows 已在当前环境验证；macOS 已检查代码分支与包内文件，仍需 Mac 真机验收。
图文步骤见同一套教程中的“科研文件夹配置指南.html”，在顶部选择你的系统。
'''
        with zipfile.ZipFile(OUT/f'tanyue-folder-hooks-{platform}.zip','w',zipfile.ZIP_DEFLATED) as z:
            for name in (*RUNTIME,'configure_tutor_folder.py'):
                z.write(APP/name,name)
            entry=zipfile.ZipInfo(launcher)
            entry.create_system=3
            entry.external_attr=(0o100755 if platform=='macos' else 0o100644)<<16
            entry.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(entry,content.encode('utf-8'))
            z.writestr('使用说明.txt',readme.encode('utf-8-sig'))
    with zipfile.ZipFile(OUT/'科研配置图文教程.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['科研文件夹配置指南.html','tanyue-folder-hooks-windows.zip','tanyue-folder-hooks-macos.zip']:
            z.write(OUT/name,name)

if __name__=='__main__':build()
