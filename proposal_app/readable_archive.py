"""Student-readable exports; only files recorded in our manifest may be replaced."""
import hashlib
import json
import os
from pathlib import Path
import re
from threading import RLock
import uuid


_LOCK = RLock()
_MANIFEST = ".coach/readable-manifest.json"
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.I)
_LABELS = {
    "papers": "参考论文", "title": "标题", "study": "研究对象与内容",
    "location": "原文位置", "finding": "研究发现", "limit": "局限",
    "source": "来源", "url": "原文链接", "help": "对本研究的帮助",
    "file_id": "附件编号", "file_ids": "附件编号", "key": "要点",
    "route": "后续方向", "comparison": "比较", "decision": "我的决定",
    "reason": "理由", "evidence": "证据", "method": "研究方法",
    "notes": "补充记录", "summary": "小结", "result": "结果",
}
_ROUTES = {"continue": "继续下一阶段", "pilot": "先做小试", "revise": "返回调整问题"}


def _safe_name(value, fallback="未命名"):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")[:100].rstrip(" .")
    if not value:
        value = fallback
    if _RESERVED.match(value):
        value = "_" + value
    return value


def _path(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("导出路径必须位于项目目录内。")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("导出路径不能指向项目目录外。") from exc
    return path


def _atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(content)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _load(root):
    try:
        value = json.loads(_path(root, _MANIFEST).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return value.get("files", {}) if isinstance(value, dict) and isinstance(value.get("files"), dict) else {}


def _save(root, manifest):
    _atomic(_path(root, _MANIFEST), json.dumps({"version": 1, "files": manifest}, ensure_ascii=False, indent=2).encode("utf-8"))


def _write(root, manifest, key, preferred, content):
    relative = manifest.get(key)
    path = _path(root, relative) if isinstance(relative, str) else None
    if path is None or path.is_symlink() or path.is_dir():
        candidate = Path(preferred)
        index = 0
        while True:
            relative = candidate.as_posix()
            path = _path(root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Claim a new path exclusively, without overwriting unknown files.
                with path.open("xb"):
                    pass
                break
            except FileExistsError:
                index += 1
                original = Path(preferred)
                candidate = original.with_name(f"{original.stem}-自动导出{index}{original.suffix}")
        manifest[key] = relative
    _atomic(path, content if isinstance(content, bytes) else content.encode("utf-8"))
    return relative


def _has_content(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return value is not None


def _text(value, key=None):
    if isinstance(value, list):
        return "\n".join("- " + _text(item).replace("\n", "\n  ") for item in value if _has_content(item))
    if isinstance(value, dict):
        return "\n".join(f"{_LABELS.get(key, key)}：{_text(item, key)}" for key, item in value.items() if _has_content(item))
    if key == "route" and isinstance(value, str):
        return _ROUTES.get(value, value)
    return str(value) if value is not None else ""


def _stage(step):
    lines = [f"# {step.get('title', '阶段成果')}", ""]
    data = step.get("data") or {}
    known = set()
    for field in step.get("fields", []):
        known.add(field["key"])
        if field["key"] in data and _has_content(data[field["key"]]):
            lines.extend([f"## {field['label']}", "", _text(data[field["key"]], field["key"]), ""])
    for key, value in data.items():
        if key not in known and _has_content(value):
            lines.extend([f"## {_LABELS.get(key, key)}", "", _text(value, key), ""])
    if not _has_content(data):
        lines.extend(["本阶段尚未保存成果。", ""])
    return "\n".join(lines)


def export_readable(root: Path, card: dict, archive: dict):
    """Refresh owned Markdown files and return their logical-key/path mapping."""
    root = Path(root)
    with _LOCK:
        manifest = _load(root)
        for folder in ("阶段成果", "文献", "学习记录", "研究过程", "我的笔记"):
            _path(root, folder).mkdir(parents=True, exist_ok=True)
        def write(key, name, content):
            return _write(root, manifest, key, name, content)
        if card.get('research'):
            if __package__:
                from .research_export import documents
            else:
                from research_export import documents
            for relative, content in documents(card).items():
                write('research:'+relative, relative, content)
        if card.get('quality', {}).get('records'):
            try:
                from .quality_records import markdown
            except ImportError:
                from quality_records import markdown
            write('quality', '研究过程/依据与选择.md', markdown(card))
        description = [f"# {card.get('title') or '我的研究项目'}", ""]
        if card.get("student_name"):
            description.extend([f"研究者：{card['student_name']}", ""])
        description.extend([f"当前阶段：{card.get('current_step', 1)}", ""])
        if card.get("next_action"):
            description.extend([f"下一步：{card['next_action']}", ""])
        description.extend(["阶段成果保存各阶段已确认或暂存的内容；文献保存参考资料；学习记录保存对话和反馈。", "", "这些成果文件由工作台自动同步更新。个人补充请放在“我的笔记”中，工作台不会覆盖其中的文件。", ""])
        write("project", "项目说明.md", "\n".join(description))
        for index, step in enumerate(card.get("steps", []), 1):
            number = int(step.get("number", index))
            key = f"stage:{number}"
            if _has_content(step.get("data")) or key in manifest:
                write(key, f"阶段成果/{number:02d}-{_safe_name(step.get('title', '阶段成果'))}.md", _stage(step))
            if number == 6 and _has_content(step.get("data")):
                write("report", "开题报告.md", "# 开题报告\n\n" + _stage(step).split("\n", 1)[1])
        materials = ["# 参考资料", ""]
        for item in card.get("materials", []):
            if not any(_has_content(item.get(key)) for key in ("title", "url", "help", "limit")):
                continue
            materials.extend([f"## {item.get('title') or '参考资料'}", ""])
            for key in ("url", "help", "limit"):
                if _has_content(item.get(key)):
                    materials.extend([f"{_LABELS[key]}：{_text(item[key])}", ""])
        if len(materials) > 2 or "materials" in manifest:
            write("materials", "文献/参考资料.md", "\n".join(materials))
        by_stage = {}
        evidence = {}
        for conversation in archive.get("conversations", []):
            number = int(conversation.get("step", 0))
            lines = by_stage.setdefault(number, [f"# 阶段 {number:02d} 对话", ""])
            for message in conversation.get("messages", []):
                if message.get("role") not in ("user", "assistant") or not message.get("text"):
                    continue
                evidence[message.get("id")] = message["text"]
                role = "学生" if message["role"] == "user" else "导师"
                lines.extend([f"## {role}" + (f" · {message['time']}" if message.get("time") else ""), "", message["text"], ""])
        for number, lines in by_stage.items():
            if len(lines) > 2 or f"chat:{number}" in manifest:
                write(f"chat:{number}", f"学习记录/阶段{number:02d}-对话.md", "\n".join(lines))
        feedback = ["# 学习反馈", ""]
        for item in archive.get("feedback", []):
            quote = evidence.get(item.get("evidence_id"))
            if not any(_has_content(value) for value in (item.get("observation"), item.get("next_action"), quote)):
                continue
            feedback.extend([f"## 阶段 {item.get('step', '')} · {item.get('dimension', '学习观察')}", "", _text(item.get("observation", "")), ""])
            if quote:
                feedback.extend(["学生原话：", "", "\n".join("> " + line for line in quote.splitlines()), ""])
            if _has_content(item.get("next_action")):
                feedback.extend([f"下一项练习：{item['next_action']}", ""])
        if len(feedback) > 2 or "feedback" in manifest:
            write("feedback", "学习记录/学习反馈.md", "\n".join(feedback))
        _save(root, manifest)
        return dict(manifest)


def export_attachment(root, fid, name, content):
    """Export uploaded bytes, returning a stable relative POSIX path."""
    root = Path(root)
    basename = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    filename = _safe_name(basename, "附件")
    suffix = Path(filename).suffix
    stem = filename[:-len(suffix)] if suffix else filename
    short_id = _safe_name(fid, "文件")[:12]
    # Keep a recognizable ID and disambiguate IDs sharing the same prefix.
    short_id += "-" + hashlib.sha256(str(fid).encode()).hexdigest()[:6]
    folder = "研究过程" if suffix.lower() in (".md", ".txt", ".csv", ".tsv", ".json", ".py", ".ipynb", ".xlsx") else "文献"
    with _LOCK:
        manifest = _load(root)
        relative = _write(root, manifest, f"attachment:{fid}", f"{folder}/{stem}-{short_id}{suffix}", content)
        _save(root, manifest)
        return relative
