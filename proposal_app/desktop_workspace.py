"""Register native Codex projects in the background without opening a blank chat."""
import os
import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
from threading import Lock, Thread
import time
import uuid

if __package__:
    from .setup_coach import codex_binary
else:
    from setup_coach import codex_binary

_registration_lock = Lock()


def desktop_is_active():
    """Only navigate automatically when the foreground app is Codex itself."""
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    user=ctypes.windll.user32;kernel=ctypes.windll.kernel32
    user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(),ctypes.byref(pid))
    handle=kernel.OpenProcess(0x1000,False,pid.value)
    if not handle:return False
    try:
        name=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)):return False
        path=name.value.lower()
        return 'openai.codex' in path and Path(path).name in ('codex.exe','chatgpt.exe')
    finally:kernel.CloseHandle(handle)


def _same_path(left, right):
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _has_root(project, folder):
    return isinstance(project, dict) and any(
        isinstance(root, dict) and isinstance(root.get("path"), str)
        and _same_path(root["path"], folder)
        for root in project.get("roots", [])
    )


class _Rpc:
    """Bounded stdio requests; never starts a model turn."""
    def __init__(self, folder, deadline):
        self.deadline = deadline
        self.sequence = 0
        self.rows = Queue()
        self.process = subprocess.Popen(
            [str(codex_binary()), "app-server"], cwd=str(folder),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.reader = Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.rows.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            self.rows.put(None)

    def initialize(self):
        self.request("initialize", {
            "clientInfo": {"name": "proposal_desktop_workspace", "version": "1"},
            "capabilities": {"experimentalApi": True},
        })
        self._send({"method": "initialized", "params": {}})

    def _send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex 项目服务响应较慢，请重试；系统会先检查已建立的项目，不必手工输入指令。")
            try:
                row = self.rows.get(timeout=remaining)
            except Empty:
                raise TimeoutError("Codex 项目服务响应较慢，请重试；系统会先检查已建立的项目，不必手工输入指令。") from None
            if row is None:
                raise RuntimeError("Codex 项目连接已关闭。")
            if row.get("id") == request_id:
                if "error" in row:
                    raise RuntimeError(f"Codex {method}：{row['error'].get('message', '请求失败')}")
                return row.get("result", {})
            if "id" in row and "method" in row:
                self._send({"id": row["id"], "error": {"code": -32601, "message": "Unsupported request"}})

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=0.1)
        # A child MCP process can briefly retain the pipe handle on Windows.
        # Closing TextIO while the reader owns its lock would block navigation.
        streams = (self.process.stdin,) if self.reader.is_alive() else (self.process.stdin, self.process.stdout)
        for stream in streams:
            if stream:
                stream.close()


def _find_project(rpc, folder):
    cursor = None
    seen = set()
    while True:
        page = rpc.request("project/list", {"cursor": cursor, "limit": 100})
        for project in page.get("data", []):
            if _has_root(project, folder):
                return project
        cursor = page.get("nextCursor")
        if cursor is None:
            return None
        if cursor in seen:
            raise RuntimeError("Codex 项目列表分页异常。")
        seen.add(cursor)


def ensure_workspace_project(path, timeout=90, keep_connection=False):
    """Confirm the native project before any stage conversation is created."""
    with _registration_lock:
        return _ensure_workspace_project(path, timeout, keep_connection)


def _ensure_workspace_project(path, timeout, keep_connection=False):
    rpc = None
    try:
        folder = Path(path).expanduser().resolve(strict=True)
        if not folder.is_dir():
            raise ValueError("研究项目目录或会话无效。")
        deadline = time.monotonic() + max(0.1, timeout)
        marker = folder / ".coach" / "desktop-project.json"
        try:
            saved = json.loads(marker.read_text("utf-8"))
        except (OSError, ValueError):
            saved = {}
        rpc = _Rpc(folder, deadline)
        rpc.initialize()
        # Trust only this app-owned project before Desktop sees its deep link.
        rpc.request('config/value/write', {
            'keyPath':'projects.'+json.dumps(str(folder),ensure_ascii=False)+'.trust_level',
            'value':'trusted','mergeStrategy':'upsert'})
        # The native registration gets its own budget: starting app-server can
        # consume most of the deadline on a cold desktop.
        deadline=time.monotonic()+max(0.1,timeout)
        rpc.deadline=deadline
        project = None
        valid_saved = isinstance(saved, dict) and saved.get("version") in (1, 2) and _same_path(saved.get("path", ""), folder)
        if valid_saved and saved.get("project_id"):
            try:
                candidate = rpc.request("project/read", {"projectId": saved["project_id"]}).get("project")
                if _has_root(candidate, folder):
                    project = candidate
            except RuntimeError as exc:
                if "project not found" not in str(exc).lower():
                    raise
        if project is None:
            # Registration may have completed just after a previous timeout.
            # A missing marker is not evidence that the native project is absent.
            project=_find_project(rpc,folder)
        if project is None:
            # Stable key makes retries safe if creation succeeded before a timeout.
            project=rpc.request("project/create", {
                "idempotencyKey":str(uuid.uuid5(uuid.NAMESPACE_URL,"proposal-workspace:"+os.path.normcase(str(folder)))),
                "name":folder.name,"roots":[{"path":str(folder)}]
            }).get("project")
            if not _has_root(project,folder):
                raise RuntimeError("Codex 返回的项目目录不匹配。")
        project_id = project.get("id")
        if not project_id:
            raise RuntimeError("Codex 未返回有效项目编号。")
        marker.parent.mkdir(parents=True, exist_ok=True)
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "path": str(folder), "project_id": project_id}, ensure_ascii=False), "utf-8")
        temporary.replace(marker)
        result={"status": "ready", "registered": True, "project_id": project_id, "path": str(folder)}
        if keep_connection:
            result['_rpc']=rpc
            rpc=None  # Caller owns the initialized connection from this point.
        return result
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        return {"status": "error", "registered": False, "error": f"无法确认 Codex 项目归组：{exc}"}
    finally:
        if rpc is not None:
            rpc.close()
