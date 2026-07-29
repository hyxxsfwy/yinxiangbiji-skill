"""AI 知识库的月度归档与目录索引工具。"""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re

try:
    from .sync_to_obsidian import resolve_note_path, safe_filename
except ImportError:
    from sync_to_obsidian import resolve_note_path, safe_filename


INDEX_FILENAME = "目录索引.md"


def month_folder_name(created: datetime) -> str:
    """把笔记创建时间转换为稳定的中文月份目录名。"""
    return created.strftime("%Y年%m月")


@dataclass(frozen=True)
class KnowledgeBaseNote:
    path: Path
    title: str
    created: datetime
    updated: datetime
    guid: str


@dataclass(frozen=True)
class ArchiveResult:
    moved: tuple[Path, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class FinalizationResult:
    moved: tuple[Path, ...]
    removed: tuple[Path, ...]
    index_path: Path
    errors: tuple[str, ...]


def _split_frontmatter(markdown_text):
    lines = str(markdown_text or "").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, lines
    try:
        closing_index = next(
            index
            for index, line in enumerate(lines[1:], 1)
            if line.strip() == "---"
        )
    except StopIteration:
        return {}, lines

    fields = {}
    for line in lines[1:closing_index]:
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        raw_value = raw_value.strip()
        if raw_value.startswith('"'):
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value.strip('"')
        else:
            value = raw_value.strip("'")
        fields[key.strip()] = str(value)
    return fields, lines[closing_index + 1:]


def _parse_datetime(value, field_name, markdown_path):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{markdown_path} 的 {field_name} 时间无效: {value!r}"
        ) from exc


def extract_note_metadata(markdown_path):
    """读取月度归档和索引所需的 Markdown 元数据。"""
    markdown_path = Path(markdown_path)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    fields, body_lines = _split_frontmatter(markdown_text)
    if not fields.get("created"):
        raise ValueError(f"{markdown_path} 缺少 created")
    identity = fields.get("source_guid") or fields.get("uid")
    if not identity:
        raise ValueError(f"{markdown_path} 缺少 source_guid 或 uid")

    raw_title = next(
        (
            match.group(1).strip()
            for line in body_lines
            if (match := re.match(r"^#\s+(.+?)\s*$", line.strip()))
        ),
        markdown_path.stem,
    )
    title = _plain_markdown_text(raw_title) or markdown_path.stem
    created = _parse_datetime(
        fields["created"],
        "created",
        markdown_path,
    )
    updated = _parse_datetime(
        fields.get("updated") or fields["created"],
        "updated",
        markdown_path,
    )
    return KnowledgeBaseNote(
        path=markdown_path,
        title=title,
        created=created,
        updated=updated,
        guid=identity,
    )


def _plain_markdown_text(value):
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", "", value)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`~]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_effective_paragraph(line):
    stripped = line.strip()
    if stripped.startswith("<!--"):
        return False
    plain = _plain_markdown_text(stripped)
    if len(plain) < 12:
        return False
    if re.match(r"^#{1,6}\s", stripped):
        return False
    if re.match(r"^(?:原文链接|原创|作者|来源)[:：]?", plain):
        return False
    if re.match(r"^(?:编译|译者)\s*[|｜]", plain):
        return False
    if re.match(r"^以下文章来源于", plain):
        return False
    if re.match(r"^共\s*\d+\s*字.*阅读需\s*\d+\s*分钟", plain):
        return False
    if re.match(r"^本文内容不构成.*(?:投资|财务).*建议", plain):
        return False
    if re.match(r"^本文为.+原创内容", plain):
        return False
    if re.fullmatch(r"(.{2,40})\s+\1", plain.rstrip("。")):
        return False
    if re.search(r"我是.+专注于.+(?:分享|干货)", plain):
        return False
    if "无法收到推送" in plain:
        return False
    if plain.endswith(("吴说Real", "AgenticHub", "聊AI")):
        return False
    if re.match(
        r"^(?:本漫画作者@|相关[:：]|[，,]\s*已帮助|（?食材不保证真实性)",
        plain,
    ):
        return False
    if re.match(r"^大家好(?:[，,]\s*我是|[。！!]?$)", plain):
        return False
    if re.match(r"^先问大家一个问题", plain):
        return False
    if re.search(r"offer", plain, re.IGNORECASE) and any(
        marker in plain
        for marker in ("学员", "总包", "上岸", "人才计划")
    ):
        return False
    if sum(
        marker in plain
        for marker in ("学员", "总包", "上岸", "人才计划")
    ) >= 2:
        return False
    if re.match(r"^(?:引言|前言|序言)[:：]", plain):
        return False
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?",
        plain,
    ):
        return False
    if "关注" in plain and any(
        marker in plain
        for marker in ("公众号", "开发者", "获取", "解锁")
    ):
        return False
    if any(
        prompt in plain
        for prompt in ("点击上方", "设置星标", "学习更多项目")
    ):
        return False
    if re.match(r"^(?:!\[|\||[-*+]\s|>\s|---+$|___+$)", stripped):
        return False
    if line.startswith("    ") or line.startswith("\t"):
        return False
    return True


def _first_sentence(paragraph, max_length=180):
    paragraph = _plain_markdown_text(paragraph)
    match = re.match(r"^(.+?[。！？!?])(?:\s|$|.)", paragraph)
    sentence = match.group(1) if match else paragraph
    if len(sentence) > max_length:
        sentence = sentence[:max_length].rstrip("，,；;：:。！？!? ") + "。"
    elif sentence and sentence[-1] not in "。！？!?":
        sentence = sentence.rstrip("：:") + "。"
    return sentence


def _outline_titles(body_lines, limit=4):
    titles = []
    for line in body_lines:
        match = re.match(r"^#{2,3}\s+(.+?)\s*#*\s*$", line.strip())
        if not match:
            continue
        title = re.sub(
            r"^\d+(?:\.\d+)*[.、]?\s*",
            "",
            _plain_markdown_text(match.group(1)),
        )
        title = re.sub(r"^\\\.\s*", "", title)
        if (
            not title
            or title in {"附件", "相关笔记"}
            or title in titles
        ):
            continue
        titles.append(title)
        if len(titles) == limit:
            break
    return titles


def build_note_summary(markdown_text, title):
    """用首段有效正文和二、三级标题生成一到两句话简介。"""
    _, body_lines = _split_frontmatter(markdown_text)
    paragraph = next(
        (
            _plain_markdown_text(line)
            for line in body_lines
            if _is_effective_paragraph(line)
        ),
        "",
    )
    if not paragraph:
        return f"该笔记主要以图片形式呈现“{title}”相关内容。"

    summary = _first_sentence(paragraph)
    outline = _outline_titles(body_lines)
    if outline:
        quoted = "、".join(f"“{heading}”" for heading in outline)
        summary += f"本文目录包括{quoted}等内容。"
    return summary


def write_knowledge_base_index(root, domain="AI"):
    """只收录契约匹配的本领域资料，并完整重建目录索引。"""
    root = Path(root)
    notes = []
    month_pattern = re.compile(r"^\d{4}年\d{2}月$")
    for month_dir in root.iterdir():
        if not month_dir.is_dir() or not month_pattern.fullmatch(
            month_dir.name
        ):
            continue
        for path in month_dir.glob("*.md"):
            if path.name == INDEX_FILENAME:
                continue
            fields, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            if fields.get("type") != "资料" or fields.get("domain") != domain:
                continue
            notes.append(extract_note_metadata(path))

    grouped = {}
    for note in notes:
        grouped.setdefault(note.path.parent.name, []).append(note)

    lines = [
        "---",
        "type: 索引",
        f"domain: {domain}",
        "status: 常青",
        "tags: []",
        "review_status: human-approved",
        "llm_policy: standard",
        "---",
        "",
        f"# {domain} 精选资料目录",
        "",
        "> [!info] 功能",
        f"> 本文件列出 {domain} 领域的全部精选资料，提供位置和简要说明。",
        "",
        "> [!info] 构建规则",
        f"> 只收录 `type: 资料` 且 `domain: {domain}` 的文档；缺失或不匹配时忽略。",
        "> 扫描本目录的年月归档，按创建月份和创建时间倒序排列。",
        "> 简介由首段有效正文和目录大纲综合生成；本文件可由导出脚本完整重建，不保存人工评论。",
        "",
    ]
    for month in sorted(grouped, reverse=True):
        lines.extend([f"## {month}", ""])
        month_notes = sorted(grouped[month], key=lambda note: note.title)
        month_notes.sort(key=lambda note: note.created, reverse=True)
        for note in month_notes:
            relative = note.path.relative_to(root).as_posix()
            markdown_text = note.path.read_text(encoding="utf-8")
            summary = build_note_summary(markdown_text, note.title)
            alias = note.title.replace("|", "｜").replace("]", "］")
            lines.extend(
                [
                    f"- [[{relative}|{alias}]]",
                    f"  - 位置：`{relative}`",
                    f"  - 简介：{summary}",
                ]
            )
        lines.append("")
    if not grouped:
        lines.extend(["## 当前资料", "", "- 暂无", ""])

    rendered = "\n".join(lines).rstrip() + "\n"
    temporary = root / f".{INDEX_FILENAME}.tmp"
    temporary.write_text(rendered, encoding="utf-8")
    index_path = root / INDEX_FILENAME
    temporary.replace(index_path)
    return index_path


def _rewrite_root_attachment_paths(markdown_text):
    markdown_text = markdown_text.replace(
        "](_attachments/",
        "](../_attachments/",
    )
    markdown_text = markdown_text.replace(
        'src="_attachments/',
        'src="../_attachments/',
    )
    return markdown_text.replace(
        'href="_attachments/',
        'href="../_attachments/',
    )


def archive_root_notes(root):
    """把根目录文章迁入创建月份目录，并报告无法迁移的文件。"""
    root = Path(root)
    moved = []
    errors = []
    for source in sorted(root.glob("*.md")):
        if source.name == INDEX_FILENAME:
            continue
        try:
            metadata = extract_note_metadata(source)
            month_dir = root / month_folder_name(metadata.created)
            month_dir.mkdir(parents=True, exist_ok=True)
            destination = month_dir / source.name
            if destination.exists():
                destination_metadata = extract_note_metadata(destination)
                if destination_metadata.guid == metadata.guid:
                    source.unlink()
                    moved.append(destination)
                    continue
                destination = resolve_note_path(
                    month_dir,
                    metadata.title,
                    metadata.guid,
                    {},
                )

            markdown_text = source.read_text(encoding="utf-8")
            destination.write_text(
                _rewrite_root_attachment_paths(markdown_text),
                encoding="utf-8",
            )
            source.unlink()
            moved.append(destination)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{source}: {exc}")
    return ArchiveResult(tuple(moved), tuple(errors))


def _monthly_markdown_paths(root):
    month_pattern = re.compile(r"^\d{4}年\d{2}月$")
    for month_dir in Path(root).iterdir():
        if month_dir.is_dir() and month_pattern.fullmatch(month_dir.name):
            yield from month_dir.glob("*.md")


def _archived_freshness_key(note):
    return archived_freshness_key(
        note.updated,
        note.created,
        note.guid,
    )


def archived_freshness_key(updated, created, guid):
    return (updated, created, guid)


def archived_title_owners(root):
    """返回每个归档标题按最终去重规则选出的当前 owner。"""
    root = Path(root)
    if not root.is_dir():
        return {}

    owners = {}
    for path in _monthly_markdown_paths(root):
        note = extract_note_metadata(path)
        title = note.title.strip()
        current = owners.get(title)
        if (
            current is None
            or _archived_freshness_key(note)
            > _archived_freshness_key(current)
        ):
            owners[title] = note
    return owners


def deduplicate_archived_notes(root):
    """删除同标题旧版本，并把胜出文件恢复为规范标题文件名。"""
    groups = {}
    for path in _monthly_markdown_paths(root):
        note = extract_note_metadata(path)
        groups.setdefault(note.title.strip(), []).append(note)

    removed = []
    for title, notes in groups.items():
        if len(notes) == 1:
            continue
        winner = max(notes, key=_archived_freshness_key)
        group_paths = {note.path for note in notes}
        canonical = winner.path.parent / f"{safe_filename(title)}.md"
        if canonical.exists() and canonical not in group_paths:
            raise FileExistsError(f"规范路径被其他文章占用: {canonical}")

        for note in notes:
            if note.path == winner.path:
                continue
            note.path.unlink()
            removed.append(note.path)

        if winner.path != canonical:
            winner.path.replace(canonical)
    return removed


def finalize_knowledge_base(root, domain="AI"):
    """迁移、去重并重建索引；重复运行保持幂等。"""
    archive = archive_root_notes(root)
    removed = tuple(deduplicate_archived_notes(root))
    index_path = write_knowledge_base_index(root, domain=domain)
    return FinalizationResult(
        moved=archive.moved,
        removed=removed,
        index_path=index_path,
        errors=archive.errors,
    )
