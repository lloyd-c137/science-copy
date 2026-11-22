"""Build the Windows x64 or macOS Research Coach ZIP for a teaching site."""

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

if __package__:
    from . import pilot_install, plugin_site
else:
    import pilot_install
    import plugin_site


APP = Path(__file__).resolve().parent
SOURCES = ('pilot_client', 'pilot_history', 'pilot_install', 'pilot_folder', 'pilot_defaults', 'review_mcp', 'coach_mcp', 'project_files', 'pdf_text',
           'tutor_runtime', 'workspace_store', 'context_archive', 'readable_archive', 'research_export', 'quality_records')


def runtime(destination, source):
    destination.mkdir()
    tag = f'python{sys.version_info.major}{sys.version_info.minor}'
    for name in ('python.exe', 'pythonw.exe', 'python3.dll', tag + '.dll', 'LICENSE.txt', 'vcruntime140.dll', 'vcruntime140_1.dll'):
        shutil.copyfile(source / name, destination / name)
    dlls = source / 'DLLs'
    for path in dlls.iterdir():
        if path.suffix == '.pyd' or path.name in ('libcrypto-3.dll', 'libssl-3.dll', 'libffi-8.dll', 'sqlite3.dll', 'zlib1.dll'):
            shutil.copyfile(path, destination / path.name)
    skip = {'test', 'tests', 'venv', 'site-packages', 'ensurepip', 'tkinter', 'turtle.py', 'idlelib', '__pycache__'}
    with ZipFile(destination / (tag + '.zip'), 'w', ZIP_DEFLATED) as archive:
        lib = source / 'Lib'
        for path in lib.rglob('*.py'):
            relative = path.relative_to(lib)
            if skip.isdisjoint(relative.parts):
                archive.write(path, str(relative))
    (destination / (tag + '._pth')).write_text(f'{tag}.zip\n.\n..\\bridge\n', 'ascii')
    framework = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319'
    subprocess.run([str(framework / 'csc.exe'), '/nologo', '/target:winexe', '/platform:x64',
                    '/reference:' + str(framework / 'Microsoft.VisualBasic.dll'),
                    '/reference:' + str(framework / 'System.Web.Extensions.dll'),
                    '/out:' + str(destination / 'folder-picker.exe'), str(APP / 'pilot_folder_windows.cs')],
                   check=True)


def build(destination, origin, target='windows'):
    if target not in ('windows', 'macos'):
        raise ValueError('未知安装包系统。')
    windows = target == 'windows'
    if windows and (sys.platform != 'win32' or platform.machine().upper() not in ('AMD64', 'X86_64') or sys.version_info[:2] != (3, 12)):
        raise ValueError('请用 Windows x64 上的 CPython 3.12 构建试教安装包。')
    origin = plugin_site.canonical_origin(origin)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.build-', dir=destination.parent) as temporary:
        folder = Path(temporary) / ('开题手记-Windows' if windows else '开题手记-macOS')
        folder.mkdir()
        if windows:
            runtime(folder / 'runtime', Path(sys.base_prefix))
        bridge = folder / 'bridge'
        bridge.mkdir()
        for module in SOURCES:
            shutil.copyfile(APP / (module + '.py'), bridge / (module + '.py'))
        marketplace = folder / 'marketplace'
        plugin = marketplace / 'plugins' / pilot_install.PLUGIN
        skill = plugin / 'skills/research-proposal-coach'
        shutil.copytree(APP.parent / 'skills/research-proposal-coach', skill,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(APP.parent / 'skills/research-proposal-review', plugin / 'skills/research-proposal-review',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        pilot_install.write_json(marketplace / '.agents/plugins/marketplace.json', {
            'name': pilot_install.MARKET, 'interface': {'displayName': '开题手记'}, 'plugins': [{
                'name': pilot_install.PLUGIN, 'source': {'source': 'local', 'path': './plugins/' + pilot_install.PLUGIN},
                'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}}]})
        pilot_install.write_json(plugin / '.codex-plugin/plugin.json', {
            'name': pilot_install.PLUGIN, 'version': pilot_install.VERSION, 'description': '科研开题导师、老师审阅与教学网站连接',
            'skills': './skills/', 'mcpServers': './.mcp.json',
            'interface': {'displayName': 'Research Coach', 'shortDescription': '科研开题导师与课题讨论同步',
                          'developerName': '开题手记项目组', 'category': 'Productivity'}})
        pilot_install.write_json(folder / 'website.json', {'origin': origin, 'platform': target})
        suffix = '.cmd' if windows else '.command'
        for action, label in (('install', '安装开题手记'),):
            script = folder / (label + suffix)
            if windows:
                script.write_bytes(f'@echo off\r\n"%~dp0runtime\\python.exe" -B "%~dp0bridge\\pilot_install.py" {action}\r\npause\r\n'.encode('ascii'))
            else:
                script.write_text('''#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
for python in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$(command -v python3 || true)"; do
    if [[ -x "$python" && "$python" != /usr/bin/python3 ]] && "$python" -c 'import sys, sqlite3, ssl; sys.exit(sys.version_info < (3, 12))'; then
        exec "$python" -B bridge/pilot_install.py ''' + action + ''' "$@"
    fi
done
printf '%s\n' '请先安装 Python 3.12 或更新版本，再重新运行。'
exit 1
''', encoding='utf-8', newline='\n')
        requirement = ('安装 Windows 版 Codex 并登录。' if windows else
                       '将 macOS 版 Codex 放到「应用程序」并登录。安装 Python 3.12 或更新版本。')
        (folder / '使用说明.txt').write_text(
            f'1. {requirement}\n'
            f'2. 解压 ZIP，运行「安装开题手记{suffix}」，核对教学网站地址。\n'
            '3. 回到已登录的开题手记，在连接向导点「我已有三位连接码」并输入。安装完成后重新打开 Codex。\n'
            '4. 从网页打开学生讨论或老师审阅，点击「选择文件夹」。\n'
            f'5. 连接失效时再运行「安装开题手记{suffix}」，用新三位码连接。\n'
            f'教学网站：{origin}\n', 'utf-8-sig')
        staged_zip = Path(temporary) / 'package.zip'
        with ZipFile(staged_zip, 'w', ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob('*')):
                if path.is_file():
                    name = path.relative_to(folder.parent)
                    if path.suffix == '.command':
                        info = ZipInfo.from_file(path, name.as_posix())
                        info.create_system = 3
                        info.external_attr = 0o100755 << 16
                        archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED)
                    else:
                        archive.write(path, name)
        staged_zip.replace(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', choices=('windows', 'macos'), default='windows')
    args = parser.parse_args()
    build(args.output, args.origin, args.target)
