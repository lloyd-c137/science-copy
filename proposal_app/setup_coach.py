"""Interactive, once-per-device registration for the teaching MCP."""
from pathlib import Path
import os
import shutil
from functools import lru_cache
import subprocess
import sys

if __package__:
    from .coach_mcp import DEFAULT_SERVER, ToolError, connect
    from .skill_distribution import install as install_skill
else:
    from coach_mcp import DEFAULT_SERVER, ToolError, connect
    from skill_distribution import install as install_skill


@lru_cache(maxsize=1)
def packaged_codex_binary():
    if os.name != 'nt':
        return None
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            '(Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1).InstallLocation'],
            capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        location = result.stdout.strip()
        path = Path(location) / 'app/resources/codex.exe'
        return path if location and path.is_file() else None
    except (OSError, subprocess.SubprocessError):
        return None


def codex_binary():
    pinned = os.environ.get('PROPOSAL_CODEX_BINARY')
    if pinned:
        path = Path(pinned)
        if not path.is_file():
            raise ValueError('指定的 Codex 客户端不存在，请重新核对桌面版本。')
        return path
    packaged = packaged_codex_binary()
    if packaged:
        return packaged
    desktop = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    candidates = sorted(desktop.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    return shutil.which("codex.cmd" if os.name == "nt" else "codex")


def main():
    binary = codex_binary()
    if not binary:
        sys.exit("这台电脑上还没找到 Codex。请先安装并登录，再打开本程序。")
    print("将把本机 Codex 连接到你的开题工作台。请用与网站相同的教学账号登录。")
    origin = input(f"教学网站地址（本机体验直接回车，默认 {DEFAULT_SERVER}）：").strip() or DEFAULT_SERVER
    connect(origin, None)
    install_skill(Path.home(), origin)
    subprocess.run([str(binary), "mcp", "add", "proposal_coach", "--", sys.executable,
                    str(Path(__file__).with_name("coach_mcp.py").resolve()), "serve"], check=True)
    print("教学工具已登记。回到本地工作台点「和导师开始讨论」，导师会自动读取项目并发起第一问。")


if __name__ == "__main__":
    try:
        main()
    except (ToolError, OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
