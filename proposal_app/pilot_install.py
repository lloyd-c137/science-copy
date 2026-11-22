"""Install Research Coach into the current Windows or macOS user's profile."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

if __package__:
    from . import pilot_folder
else:
    import pilot_folder

MARKET = 'research-coach-local'
PLUGIN = 'research-coach'
VERSION = '1.3.15'


def codex():
    if sys.platform == 'darwin':
        candidates = [folder / 'Codex.app/Contents/Resources/codex'
                      for folder in (Path('/Applications'), Path.home() / 'Applications')]
        command = shutil.which('codex')
        if command:
            candidates.append(Path(command))
        candidates.extend(Path(folder) / 'codex' for folder in ('/opt/homebrew/bin', '/usr/local/bin'))
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        raise ValueError('请把 Codex.app 放到「应用程序」中，打开它并登录。')
    executable = shutil.which('codex.exe')
    if executable:
        return Path(executable)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                             '(Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1).InstallLocation'],
                            capture_output=True, text=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
    location = result.stdout.strip()
    candidate = Path(location) / 'app/resources/codex.exe'
    if location and candidate.is_file():
        return candidate
    raise ValueError('请先安装 Windows 版 Codex 并用自己的账号登录。')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.config-', dir=path.parent) as temporary:
        staged = Path(temporary) / path.name
        staged.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
        staged.replace(path)


def website_origin(value):
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    parts = urlsplit(value)
    port = parts.port
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or
            any(char.isspace() for char in parts.netloc) or port == 0 or
            parts.path not in ('', '/') or not (parts.scheme == 'https' or
            parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost', '::1'))):
        raise ValueError('请输入开题手记网站的完整地址，例如 https://school.example。')
    host = parts.hostname.encode('idna').decode('ascii')
    if ':' in host:
        host = f'[{host}]'
    suffix = f':{port}' if port and (parts.scheme, port) not in (('https', 443), ('http', 80)) else ''
    return f'{parts.scheme}://{host}{suffix}'


def install(bundle, appdata, origin=None, *, interpreter=None, executable=None):
    config = json.loads((bundle / 'website.json').read_text('utf-8'))
    config['origin'] = website_origin(origin or config['origin'])
    # Keep credentials and archives separate for each website.
    site = hashlib.sha256(config['origin'].encode()).hexdigest()[:12]
    root = appdata / 'ProposalCoachPilot' / site
    root.mkdir(parents=True, exist_ok=True)
    release = root / VERSION
    with TemporaryDirectory(prefix='install-', dir=root) as temporary:
        staging = Path(temporary) / 'app'
        if not release.exists():
            if interpreter is None:
                shutil.copytree(bundle / 'runtime', staging / 'runtime')
            shutil.copytree(bundle / 'bridge', staging / 'bridge')
            shutil.copytree(bundle / 'marketplace', staging / 'marketplace')
            plugin = staging / 'marketplace' / 'plugins' / PLUGIN
            worker = release / 'bridge' / 'pilot_client.py'
            python = interpreter or release / 'runtime' / 'python.exe'
            codex_home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')).resolve()
            env = {'PROPOSAL_PILOT_STATE': str(root / 'state'),
                   'PROPOSAL_CODEX_SESSIONS': str(codex_home / 'sessions'),
                   'PROPOSAL_SKILL_DIR': str(release / plugin.relative_to(staging) / 'skills/research-proposal-coach')}
            if executable:
                env['PROPOSAL_CODEX_BINARY'] = str(executable)
            write_json(plugin / '.mcp.json', {'mcpServers': {'proposal_coach': {
                'command': str(python), 'args': ['-B', str(worker), 'serve', '--origin', config['origin']],
                'startup_timeout_sec': 25, 'tool_timeout_sec': 90,
                'env': env,
            }}})
            try:
                staging.rename(release)
            except FileExistsError:
                pass  # The concurrent install published the same version.
    return release, root / 'state', config['origin']


def register(executable, bundle, release, appdata, origin):
    # Codex pins the registered marketplace path. Keep that path stable across
    # releases and school URL changes, while runtime files live per site/version.
    catalog = appdata / 'ProposalCoachPilot' / 'marketplace'
    source = bundle / 'marketplace'
    selected = catalog.parent / 'active-site.json'
    previous = json.loads(selected.read_text('utf-8')) if selected.exists() else {}
    shutil.copytree(source, catalog, dirs_exist_ok=True)
    shutil.copyfile(release / 'marketplace' / 'plugins' / PLUGIN / '.mcp.json',
                    catalog / 'plugins' / PLUGIN / '.mcp.json')
    cli = [str(executable), 'plugin']
    subprocess.run([*cli, 'marketplace', 'add', str(catalog)], check=True, timeout=40)
    if previous and previous.get('origin') != origin:
        # The cache key includes plugin version, so a same-version site switch
        # needs to refresh the installed copy of .mcp.json.
        subprocess.run([*cli, 'remove', f'{PLUGIN}@{MARKET}'], check=True, timeout=40)
    subprocess.run([*cli, 'add', f'{PLUGIN}@{MARKET}'], check=True, timeout=40)
    write_json(selected, {'origin': origin, 'version': VERSION})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'connect'))
    parser.add_argument('--no-connect', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--origin', help='开题手记网站地址')
    options = parser.parse_args()
    bundle = Path(__file__).resolve().parents[1]
    try:
        settings = json.loads((bundle / 'website.json').read_text('utf-8'))
        target = settings.get('platform', 'windows')
        actual = {'darwin': 'macos', 'win32': 'windows'}.get(sys.platform)
        if actual != target:
            raise ValueError('请从开题手记下载与这台电脑系统对应的安装包。')
        interpreter = Path(sys.executable).absolute() if actual == 'macos' else None
        if interpreter and sys.version_info < (3, 12):
            raise ValueError('请安装 Python 3.12 或更新版本，然后重新运行。')
        appdata = Path.home() / 'Library/Application Support' if interpreter else Path(os.environ['LOCALAPPDATA'])
        executable = codex() if options.action == 'install' else None
        default = settings['origin']
        selected = appdata / 'ProposalCoachPilot/active-site.json'
        if options.action == 'connect' and selected.is_file():
            default = json.loads(selected.read_text('utf-8'))['origin']
        origin = options.origin
        if not origin and not options.no_connect:
            while not origin:
                try:
                    origin = website_origin(input(f'开题手记网址 [{default}]（回车使用默认网址）：').strip() or default)
                except ValueError as error:
                    print(error, flush=True)
        if options.action == 'connect':
            candidate = hashlib.sha256(website_origin(origin or default).encode()).hexdigest()[:12]
            installed = appdata / 'ProposalCoachPilot' / candidate / VERSION
            if not installed.is_dir():
                raise ValueError('这个站点尚未安装插件，请先运行「安装开题手记」。')
        release, state, origin = install(bundle, appdata, origin, interpreter=interpreter, executable=executable)
        if executable:
            register(executable, bundle, release, appdata, origin)
            pilot_folder.register(interpreter or release / 'runtime/python.exe',
                                  release / 'bridge/pilot_folder.py', selected)
        if not options.no_connect:
            subprocess.run([str(interpreter or release / 'runtime/python.exe'), '-B', str(release / 'bridge/pilot_client.py'),
                            'connect', '--origin', origin, '--local'], env={**os.environ, 'PROPOSAL_PILOT_STATE': str(state)}, check=True)
        print('完成。如果 Codex 正在运行，请先退出，再重新打开。', flush=True)
    except (OSError, ValueError, EOFError, subprocess.SubprocessError) as error:
        sys.exit(f'安装或连接没有完成：{error}')


if __name__ == '__main__':
    main()
