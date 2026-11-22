"""Synchronize site defaults through Codex's supported config API, without a model turn."""
import json
from contextlib import closing
import os
from pathlib import Path
from queue import Queue, Empty
import sqlite3
import subprocess
import threading
import time

if __package__:
    from . import pilot_install
else:
    import pilot_install


def apply_defaults(settings, executable=None):
    executable = executable or os.environ.get('PROPOSAL_CODEX_BINARY') or pilot_install.codex()
    process = subprocess.Popen([str(executable), 'app-server'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    rows = Queue()
    def read():
        for line in process.stdout:
            try:
                rows.put(json.loads(line))
            except ValueError:
                continue
        rows.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    def call(identifier, method, params):
        process.stdin.write(json.dumps(dict(id=identifier, method=method, params=params)) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                row = rows.get(timeout=max(.01, deadline - time.monotonic()))
            except Empty:
                break
            if row is None:
                raise ValueError('Codex 配置服务提前退出。')
            if row.get('id') == identifier:
                if 'error' in row:
                    raise ValueError('Codex 未接受默认配置：' + str(row['error'].get('message', '未知错误')))
                return row['result']
        raise ValueError('Codex 配置同步超时。')
    try:
        call(1, 'initialize', {'clientInfo': {'name': 'proposal_defaults', 'version': pilot_install.VERSION},
                               'capabilities': {'experimentalApi': True}})
        result = call(2, 'config/batchWrite', {'edits': [
            {'keyPath': 'model', 'value': settings['model'], 'mergeStrategy': 'replace'},
            {'keyPath': 'model_reasoning_effort', 'value': settings['reasoning_effort'], 'mergeStrategy': 'replace'}],
            'reloadUserConfig': True})
        if result.get('overriddenMetadata'):
            raise ValueError('本机更高优先级配置覆盖了网站默认值。')
        return result
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        reader.join(timeout=1)
        process.stdout.close()


def sync(device, folder):
    """One application per site revision across all MCP processes; no override loop."""
    settings = device.request('/api/plugin/runtime-settings', {})
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(folder / 'defaults.sqlite3', timeout=2)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS defaults (owner TEXT PRIMARY KEY, revision TEXT, status TEXT)')
        db.execute('BEGIN IMMEDIATE')
        owner = device.origin + ':' + device.account
        previous = db.execute('SELECT revision,status FROM defaults WHERE owner=?', (owner,)).fetchone()
        if previous == (settings['revision'], 'applied'):
            return
        try:
            apply_defaults(settings)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            db.execute('INSERT OR REPLACE INTO defaults VALUES (?,?,?)', (owner, settings['revision'], str(error)))
            db.commit()
            raise ValueError(str(error)) from error
        db.execute('INSERT OR REPLACE INTO defaults VALUES (?,?,?)', (owner, settings['revision'], 'applied'))
