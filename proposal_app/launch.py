"""Launch the local teaching service and open the student site in a browser."""

import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
import argparse


APP = pathlib.Path(__file__).resolve().parent
URL = "http://127.0.0.1:8767"


def service_is_ready():
    try:
        with urllib.request.urlopen(URL + "/api/me", timeout=1) as response:
            return response.headers.get_content_type() == "application/json"
    except urllib.error.HTTPError as exc:
        return exc.code == 401 and exc.headers.get_content_type() == "application/json"
    except OSError:
        return False


def main():
    global URL
    parser=argparse.ArgumentParser(description='打开本地开题工作台')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--db')
    parser.add_argument('--plugin-origin')
    parser.add_argument('--plugin-package')
    parser.add_argument('--plugin-macos-package')
    args=parser.parse_args()
    URL=f'http://127.0.0.1:{args.port}'
    if service_is_ready():
        webbrowser.open(URL)
        return 0
    command=[sys.executable,str(APP/'server.py'),'--port',str(args.port)]
    if args.db: command+=['--db',str(pathlib.Path(args.db).resolve())]
    if args.plugin_origin: command+=['--plugin-origin',args.plugin_origin]
    if args.plugin_package: command+=['--plugin-package',str(pathlib.Path(args.plugin_package).resolve())]
    if args.plugin_macos_package: command+=['--plugin-macos-package',str(pathlib.Path(args.plugin_macos_package).resolve())]
    process = subprocess.Popen(command, cwd=APP)
    try:
        for _ in range(80):
            if process.poll() is not None:
                return process.returncode
            if service_is_ready():
                print(f"开题工作台已启动 {URL}，关闭此窗口或按 Ctrl+C 即可退出。", flush=True)
                webbrowser.open(URL)
                return process.wait()
            time.sleep(0.15)
        print("教学服务启动超时，请查看本窗口中的服务信息。")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    sys.exit(main())
