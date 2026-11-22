"""Open a native folder dialog and return its result to the initiating browser."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from threading import Event, Thread
from time import monotonic


SCHEME = 'research-coach-folder'
PORT = 48768
TIMEOUT = 180


def register(interpreter, worker, active_site):
    command = [str(interpreter), '-B', str(worker), str(active_site)]
    if sys.platform == 'win32':
        import winreg

        command[0] = str(interpreter.with_name('pythonw.exe'))
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr'Software\Classes\{SCHEME}') as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'URL:Research Coach Folder')
            winreg.SetValueEx(key, 'URL Protocol', 0, winreg.REG_SZ, '')
            with winreg.CreateKey(key, r'shell\open\command') as handler:
                winreg.SetValueEx(handler, '', 0, winreg.REG_SZ, subprocess.list2cmdline(command) + ' "%1"')
        return

    import plistlib
    from tempfile import TemporaryDirectory
    import shutil

    applications = Path.home() / 'Applications'
    applications.mkdir(exist_ok=True)
    app = applications / 'Research Coach Folder.app'
    script = ('on open location pickURL\n'
              '  do shell script ' + json.dumps(shlex.join(command) + ' ', ensure_ascii=False) +
              ' & quoted form of pickURL & " >/dev/null 2>&1 &"\nend open location\n')
    with TemporaryDirectory(prefix='.research-coach-', dir=applications) as temporary:
        staged = Path(temporary) / app.name
        subprocess.run(['/usr/bin/osacompile', '-o', str(staged), '-e', script], check=True, timeout=30)
        info = staged / 'Contents/Info.plist'
        with info.open('rb') as source:
            manifest = plistlib.load(source)
        manifest.update(CFBundleIdentifier='org.openingnotebook.researchcoach.folder', LSUIElement=True,
                        CFBundleURLTypes=[{'CFBundleURLName': 'Research Coach Folder', 'CFBundleURLSchemes': [SCHEME]}])
        with info.open('wb') as target:
            plistlib.dump(manifest, target)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(staged)], check=True, timeout=30)
        if app.exists():
            shutil.rmtree(app)
        staged.rename(app)
    registry = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'
    subprocess.run([registry, '-f', str(app)], check=True, timeout=20)


def windows_dialog(create):
    executable = Path(sys.executable).with_name('folder-picker.exe')
    result = subprocess.run([str(executable), 'new' if create else 'choose'],
                            capture_output=True, encoding='utf-8', check=True, timeout=TIMEOUT - 15)
    selection = json.loads(result.stdout)
    return selection['folder'], selection['name']


def mac_prompt(script):
    result = subprocess.run(['/usr/bin/osascript', '-e', script], capture_output=True,
                            encoding='utf-8', timeout=(TIMEOUT - 15) / 2)
    if result.returncode and '(-128)' in result.stderr:
        return None
    result.check_returncode()
    return result.stdout.removesuffix('\n')


def select_folder(create):
    if sys.platform == 'win32':
        folder, name = windows_dialog(create)
    else:
        title = '选择新文件夹要放在哪里' if create else '选择课题文件夹'
        folder = mac_prompt(f'POSIX path of (choose folder with prompt "{title}")')
        name = mac_prompt('text returned of (display dialog "输入新文件夹的名称" default answer "" with title "新建课题文件夹")') if folder and create else None
    if not folder or create and name is None:
        return None
    path = Path(folder).resolve(strict=True)
    if not path.is_dir():
        raise ValueError('请选择一个文件夹。')
    if create:
        name = name.strip()
        if (not name or name in ('.', '..') or re.search(r'[\\/:*?"<>|\x00-\x1f]|[. ]$', name)
                or (path / name).is_reserved()):
            raise ValueError('这个文件夹名不能使用，请换一个名称。')
        path /= name
        try:
            path.mkdir()
        except FileExistsError as error:
            raise ValueError('这个名称已存在。请换一个名称，或选择已有文件夹。') from error
    return str(path)


def handoff(origin, nonce, create, port=PORT):
    result = None
    delivered = Event()

    class Handoff(BaseHTTPRequestHandler):
        def reply(self, preflight):
            if (self.path != '/folder/' + nonce or self.headers.get('Origin') != origin
                    or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'):
                self.send_error(403)
                return
            payload = result
            self.send_response(204 if preflight else 202 if payload is None else 200)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if not preflight and payload is not None:
                self.wfile.write(json.dumps(payload).encode('ascii'))
                delivered.set()

        def do_GET(self):
            self.reply(False)

        def do_OPTIONS(self):
            self.reply(True)

        def log_message(self, *_args):
            pass

    def choose():
        nonlocal result
        try:
            result = {'path': select_folder(create)}
        except ValueError as error:
            result = {'error': str(error)}
        except (OSError, subprocess.SubprocessError):
            result = {'error': '系统文件夹窗口未完成，请再试一次。'}

    with ThreadingHTTPServer(('127.0.0.1', port), Handoff) as service:
        service.timeout = .3
        Thread(target=choose, daemon=True).start()
        deadline = monotonic() + TIMEOUT
        while not delivered.is_set() and monotonic() < deadline:
            service.handle_request()


if __name__ == '__main__':
    if len(sys.argv) == 3:
        match = re.fullmatch(r'research-coach-folder://(choose|new)/([a-f0-9]{48})', sys.argv[2])
        if match:
            try:
                site = json.loads(Path(sys.argv[1]).read_text('utf-8'))
                handoff(site['origin'], match[2], match[1] == 'new')
            except (KeyError, OSError, ValueError):
                sys.exit(1)
