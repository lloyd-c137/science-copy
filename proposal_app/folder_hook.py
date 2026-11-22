"""Shared-folder entry point, installed beneath the selected research root."""
import json
from pathlib import Path
import sys

from tutor_folder import project_folder
from tutor_runtime import hook

def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    event = json.load(sys.stdin)
    root = Path(__file__).resolve().parents[2]
    try:
        folder = project_folder(event['cwd'],root)
        if folder is None:
            context = ''
        else:
            context = hook(dict(event,cwd=str(folder)))
        print(json.dumps({'hookSpecificOutput':{'hookEventName':event['hook_event_name'],
                                               'additionalContext':context}},ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'decision':'block','reason':'科研接续尚未就绪：'+str(error)},ensure_ascii=False))

if __name__ == '__main__':
    main()
