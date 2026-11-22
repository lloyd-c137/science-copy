"""Publish teaching skills and install them on a clean Codex workstation."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
import zipfile

NAME = 'research-proposal-coach'
REVIEW_NAME = 'research-proposal-review'
PACKAGES = {
    NAME: ('SKILL.md', 'references/yau-review.md', 'references/yau-awarded-papers.md',
           'references/workflow.md', 'references/search-evidence.md', 'references/objects-recheck.md',
           'references/research-types.md', 'references/deliverable-defense.md', 'references/retained-cases.md'),
    REVIEW_NAME: ('SKILL.md', 'references/workflow.md'),
}
FILES = PACKAGES[NAME]


def download_path(name=NAME):
    if name not in PACKAGES:
        raise ValueError('未知的教学 Skill。')
    return '/downloads/' + name + '.zip'


DOWNLOAD = download_path()
PREFIX = '.agents/skills/' + NAME + '/'
MAX_DOWNLOAD = 2 * 1024 * 1024


def release(name=NAME):
    source = Path(__file__).resolve().parent.parent / 'skills' / name
    download_path(name)
    files = {filename: (source / filename).read_bytes() for filename in PACKAGES[name]}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    manifest = {'name': name, 'files': hashes,
                'version': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]}
    return manifest, files


def version(name=NAME):
    return release(name)[0]['version']


def bundle(name=NAME):
    manifest, files = release(name)
    prefix = '.agents/skills/' + name + '/'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(prefix + name, data)
        archive.writestr(prefix + 'distribution.json', json.dumps(manifest, ensure_ascii=False))
        archive.writestr('使用说明.txt',
            '将压缩包解压到你的研究项目文件夹，保留 .agents/skills 目录。\n'
            f'在 Codex 中打开这个项目，新建聊天，输入 ${manifest["name"]} 开始使用。\n'
            '网站的本地工作台会在首次启动讨论时自动完成这一步。\n'
            'Skill 提供教学规则；网站项目的读写还需要工作台配置的 MCP 连接。\n')
    return output.getvalue()


def installed(root, name=NAME):
    download_path(name)
    declared = PACKAGES[name]
    folder = Path(root) / '.agents' / 'skills' / name
    try:
        manifest = json.loads((folder / 'distribution.json').read_text('utf-8'))
        if manifest['name'] != name or set(manifest['files']) != set(declared):
            return None
        if all(hashlib.sha256((folder / filename).read_bytes()).hexdigest() == manifest['files'][filename]
               for filename in declared):
            return folder
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def install(root, origin, expected_version=None, name=NAME):
    """Download once; validate the entire package before writing any skill files."""
    path = download_path(name)
    declared = PACKAGES[name]
    prefix = '.agents/skills/' + name + '/'
    existing = installed(root, name)
    if existing and (expected_version is None or json.loads((existing/'distribution.json').read_text('utf-8'))['version'] == expected_version):
        return existing
    parts = urlsplit(origin)
    if (parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in
            ('127.0.0.1', 'localhost', '::1'))) or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Skill 下载需要有效的教学网站地址。')
    try:
        with build_opener(NoRedirect()).open(origin.rstrip('/') + path, timeout=20) as response:
            data = response.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError('Skill 下载包过大。')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            expected = {prefix + filename for filename in (*declared, 'distribution.json')} | {'使用说明.txt'}
            if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
                raise ValueError('Skill 下载包内容不完整。')
            if sum(item.file_size for item in archive.infolist()) > MAX_DOWNLOAD:
                raise ValueError('Skill 解压内容过大。')
            manifest = json.loads(archive.read(prefix + 'distribution.json'))
            if expected_version is not None and manifest.get('version') != expected_version:
                raise ValueError('Skill 发布版本已变化，请刷新项目后重试。')
            if manifest['name'] != name or set(manifest['files']) != set(declared):
                raise ValueError('Skill 下载包标识不匹配。')
            files = {filename: archive.read(prefix + filename) for filename in declared}
            for filename, content in files.items():
                if hashlib.sha256(content).hexdigest() != manifest['files'][filename]:
                    raise ValueError('Skill 下载校验失败。')
                content.decode('utf-8-sig')
        folder = Path(root) / '.agents' / 'skills' / name
        for filename, content in {**files, 'distribution.json': json.dumps(manifest).encode()}.items():
            target = folder / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                temporary.write(content)
            try:
                os.replace(temporary.name, target)
            finally:
                Path(temporary.name).unlink(missing_ok=True)
        return folder
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        raise ValueError('无法从网站安装教学 Skill，请检查网站连接后重新连接。') from error
