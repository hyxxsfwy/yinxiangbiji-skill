#!/usr/bin/env python3
"""
印象笔记 -> Obsidian 增量同步脚本

判断逻辑：
- 资源有 fileName+扩展名  → 附件笔记，存入 _attachments/
- 资源无 fileName，有 en-media 内嵌图片  → 内嵌图片笔记，转 Markdown + 附件 section
- 资源无 fileName，div+span≥3 且 < 200KB  → 短网页片段，转 Markdown
- 资源无 fileName，div+span≥3 且 ≥ 200KB 且是网页裁剪 → 存 HTML 进 _clips/
- 其余  → 转 Markdown
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .runtime import (
        configure_utf8_output,
        create_note_store,
        load_config,
        load_setting,
    )
except ImportError:
    from runtime import (
        configure_utf8_output,
        create_note_store,
        load_config,
        load_setting,
    )
import evernote.edam.notestore.NoteStore as NoteStore
import html as html_module
from datetime import datetime
import html2text

# ─── 配置 ────────────────────────────────────────────────
DEFAULT_MAX_SYNC_PER_RUN = 50
DEFAULT_API_DELAY = 1.0
CLIP_SIZE_THRESHOLD = 200 * 1024  # 200KB 网页片段阈值
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
EN_MEDIA_PATTERN = re.compile(
    r'<en-media\b(?=[^>]*\bhash="([0-9a-fA-F]{32})")[^>]*'
    r'(?:/>|>.*?</en-media\s*>)',
    flags=re.IGNORECASE | re.DOTALL,
)


# ─── 工具函数 ──────────────────────────────────────────────

def safe_filename(name):
    cleaned = re.sub(r'[\x00-\x1f\\/:*?"<>|]', '_', str(name))
    cleaned = cleaned.strip().rstrip(" .")
    if not cleaned:
        cleaned = "untitled"
    stem = cleaned.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    if len(cleaned) > 120:
        base, extension = os.path.splitext(cleaned)
        if 1 < len(extension) <= 16:
            cleaned = base[:120 - len(extension)].rstrip(" .") + extension
        else:
            cleaned = cleaned[:120]
    return cleaned.rstrip(" .") or "untitled"


def clip_filename_for_guid(guid):
    """使用完整 GUID 生成不会因前缀相同而碰撞的网页裁剪文件名。"""
    return f"clip_{safe_filename(guid)}.html"


def resource_has_filename(res):
    """检查资源是否有原始文件名（最关键的判断条件）"""
    if not hasattr(res, 'attributes') or not res.attributes:
        return False
    fname = getattr(res.attributes, 'fileName', None)
    if not fname:
        return False
    # 有文件名且带扩展名 → 是真实附件
    _, ext = os.path.splitext(fname)
    return bool(ext)


def get_resource_filename(res):
    """获取资源的原始文件名，无则返回 None"""
    if not hasattr(res, 'attributes') or not res.attributes:
        return None
    return getattr(res.attributes, 'fileName', None)


def extract_resources(note):
    """提取所有附件，返回 {hash: {filename, data, mime}}"""
    # 已知的 MIME type → 扩展名映射
    MIME_EXT_MAP = {
        'image/png': '.png', 'image/jpeg': '.jpg',
        'image/gif': '.gif', 'image/webp': '.webp',
        'image/svg+xml': '.svg', 'application/pdf': '.pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        'application/vnd.ms-excel': '.xls',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    }
    KNOWN_EXTS = set(MIME_EXT_MAP.values())
    
    resources = {}
    if not hasattr(note, 'resources') or not note.resources:
        return resources
    for res in note.resources:
        if not hasattr(res, 'data') or not res.data or not res.data.body:
            continue
        mime = getattr(res, 'mime', 'application/octet-stream')
        data = res.data.body
        h = hashlib.md5(data).hexdigest()

        # 优先用原始文件名，否则用 hash
        orig_name = get_resource_filename(res)
        if orig_name:
            safe_name = safe_filename(orig_name)
            _, ext = os.path.splitext(orig_name)
            # 如果扩展名不是已知类型，根据 MIME 添加正确的扩展名
            if ext.lower() not in KNOWN_EXTS:
                correct_ext = MIME_EXT_MAP.get(mime, '')
                if correct_ext:
                    safe_name += correct_ext
            filename = safe_name
        else:
            # 无文件名 → inline 资源，用 hash 做文件名
            ext = MIME_EXT_MAP.get(mime, '')
            filename = h + ext

        h = hashlib.md5(data).hexdigest()
        resources[h] = {'filename': filename, 'data': data, 'mime': mime, 'hash': h}
    return resources


def save_attachments(resources, attachments_dir):
    """保存附件到目录（按文件名，hash 去重）"""
    os.makedirs(attachments_dir, exist_ok=True)
    saved = {}
    for h, res in resources.items():
        original = res['filename']
        stem, ext = os.path.splitext(original)
        candidates = [
            original,
            f"{stem}_{h[:8]}{ext}",
            f"{stem}_{h}{ext}",
        ]
        counter = 2
        while True:
            filename = (
                candidates.pop(0)
                if candidates
                else f"{stem}_{h}_{counter}{ext}"
            )
            if not candidates and filename.endswith(f"_{counter}{ext}"):
                counter += 1
            fp = os.path.join(attachments_dir, filename)
            if not os.path.exists(fp):
                with open(fp, 'wb') as f:
                    f.write(res['data'])
                break
            if os.path.isfile(fp):
                with open(fp, 'rb') as f:
                    existing_hash = hashlib.md5(f.read()).hexdigest()
                if existing_hash == h:
                    break
        saved[h] = filename
    return saved


def make_attachment_link(fname, prefix="_attachments"):
    """根据文件类型生成正确的 Markdown 链接格式"""
    ext = os.path.splitext(fname)[1].lower()
    label = fname.replace("[", r"\[").replace("]", r"\]")
    url = attachment_url(fname, prefix=prefix)
    if ext in IMAGE_EXTS:
        return f'![{label}]({url})'
    else:
        return f'[{label}]({url})'


def attachment_url(fname, prefix="_attachments"):
    """生成可用于 Markdown/HTML 的相对附件 URL。"""
    encoded_name = quote(str(fname), safe="-._~")
    return f"{prefix}/{encoded_name}"


def make_attachments_section(
    hash_to_file,
    exclude_filenames=None,
    prefix="_attachments",
):
    """生成附件列表 section"""
    if not hash_to_file:
        return ''
    excluded = set(exclude_filenames or ())
    lines = ['\n---\n', '## 附件\n']
    seen_filenames = set()
    for fname in hash_to_file.values():
        if fname in seen_filenames or fname in excluded:
            continue
        seen_filenames.add(fname)
        ext = os.path.splitext(fname)[1].lower()
        if ext in IMAGE_EXTS:
            lines.append(make_attachment_link(fname, prefix=prefix))
        else:
            lines.append(f"- {make_attachment_link(fname, prefix=prefix)}")
    if not seen_filenames:
        return ''
    return '\n'.join(lines)


def referenced_attachment_filenames(
    markdown_body,
    hash_to_file,
    prefix="_attachments",
):
    """返回正文中已经引用的附件文件名，避免在文末重复展示。"""
    return {
        filename
        for filename in hash_to_file.values()
        if attachment_url(filename, prefix=prefix) in (markdown_body or "")
    }


def is_enml_clip(content):
    """检查 ENML 内容是否有网页裁剪属性（更可靠的判断）"""
    if not content:
        return False
    return '--en-clipped-content' in content


def is_web_clip_by_content(content):
    """通过内容结构判断是否为网页裁剪（用于无 fileName 的资源）"""
    if not content:
        return False
    return (content.count('<div') + content.count('<span') +
            content.count('<script') + content.count('<style')) >= 3


def has_en_media(content):
    """检查内容是否包含 en-media 标签（内嵌图片等资源）"""
    if not content:
        return False
    return bool(EN_MEDIA_PATTERN.search(content))


def enml_to_markdown(enml_content):
    """ENML 纯文本笔记转 Markdown"""
    if not enml_content:
        return ""
    c = enml_content
    c = re.sub(r'<\?xml[^?]*\?>', '', c)
    c = re.sub(r'<!DOCTYPE[^>]*>', '', c)
    c = re.sub(r'<en-note[^>]*>', '', c)
    c = re.sub(r'</en-note>', '', c)
    c = re.sub(r'<br\/?>', '\n', c)
    c = re.sub(r'<p[^>]*>', '', c)
    c = re.sub(r'</p>', '\n\n', c)
    c = re.sub(r'<li[^>]*>', '- ', c)
    c = re.sub(r'</li>', '\n', c)
    for tag in ['b', 'strong', 'i', 'em', 'u']:
        c = re.sub(f'<{tag}[^>]*>(.*?)</{tag}>', r'\1', c, flags=re.DOTALL)
    c = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', c, flags=re.DOTALL)
    c = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', c, flags=re.DOTALL)
    c = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', c, flags=re.DOTALL)
    c = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', c, flags=re.DOTALL)
    c = html_module.unescape(c)
    c = re.sub(r'\n{3,}', '\n\n', c)
    return c.strip()


def _normalized_markdown_title(value):
    """移除 Markdown 标题/强调标记，便于识别正文中的重复标题。"""
    text = html_module.unescape(str(value or "")).strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"\s*#+\s*$", "", text)
    for marker in ("**", "__", "*", "_", "`"):
        if text.startswith(marker) and text.endswith(marker):
            text = text[len(marker):-len(marker)].strip()
    return re.sub(r"\s+", " ", text).casefold()


def _is_plain_section_title(line):
    """判断编号标题之后的一行是否可安全合并为章节标题。"""
    stripped = line.strip()
    if not stripped or len(stripped) > 100:
        return False
    return not re.match(
        r"^(?:#{1,6}\s|[-*+>]\s|\d+[.)、]\s|!\[|\[|\||```|~~~|<)",
        stripped,
    )


def simplify_markdown(markdown, document_title=None):
    """统一为单一文档标题、简洁章节层级和紧凑空行。"""
    if not markdown:
        return ""

    lines = (
        str(markdown)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    )
    expected_title = _normalized_markdown_title(document_title)
    simplified = []
    in_fence = False
    index = 0

    while index < len(lines):
        line = lines[index].replace("\u200b", "").replace("\xa0", " ").rstrip()
        stripped = line.strip()

        if re.match(r"^(?:```|~~~)", stripped):
            in_fence = not in_fence
            simplified.append(line)
            index += 1
            continue

        is_indented_code = line.startswith("    ") or line.startswith("\t")
        if not in_fence and not is_indented_code:
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
            line_title = _normalized_markdown_title(stripped)

            if expected_title and line_title == expected_title:
                index += 1
                continue

            if heading:
                level = len(heading.group(1))
                heading_text = heading.group(2).strip()
                section_number = re.fullmatch(
                    r"(\d{1,2})[.、]?",
                    heading_text,
                )
                if section_number:
                    next_index = index + 1
                    while (
                        next_index < len(lines)
                        and not lines[next_index].strip()
                    ):
                        next_index += 1
                    if (
                        next_index < len(lines)
                        and _is_plain_section_title(lines[next_index])
                    ):
                        simplified.append(
                            f"## {section_number.group(1)} "
                            f"{lines[next_index].strip()}"
                        )
                        index = next_index + 1
                        continue

                level = max(2, level)
                simplified.append(f"{'#' * level} {heading_text}")
                index += 1
                continue

            if re.match(r"^\d+(?:\.\d+)+\s+\S", stripped):
                simplified.append(f"### {stripped}")
                index += 1
                continue

        simplified.append(line)
        index += 1

    compact = "\n".join(simplified)
    compact = re.sub(r"[ \t]+\n", "\n", compact)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    return compact.strip()


def _evernote_codeblocks_to_html(content):
    """把印象笔记专用代码块标记转换成保留换行的标准 HTML。"""
    pattern = re.compile(
        r"<div\b(?=[^>]*--en-codeblock\s*:\s*true)[^>]*>"
        r"(.*?)</div\s*>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def replace_codeblock(match):
        inner = match.group(1)
        inner = re.sub(r"<br\s*/?>", "\n", inner, flags=re.IGNORECASE)
        inner = re.sub(
            r"</(?:div|p|li)\s*>",
            "\n",
            inner,
            flags=re.IGNORECASE,
        )
        inner = re.sub(r"<[^>]+>", "", inner)
        text = html_module.unescape(inner).replace("\xa0", " ")
        text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        return f"<pre>{html_module.escape(text, quote=False)}</pre>"

    return pattern.sub(replace_codeblock, content or "")


def html_to_md(content, hash_to_file, attachment_prefix="_attachments"):
    """ENML 网页裁剪内容转 Markdown（使用 html2text）"""
    if not content:
        return ""

    IMAGE_EXTS_LOCAL = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}

    def en_media_to_img(match):
        h = match.group(1).lower()
        if hash_to_file and h in hash_to_file:
            fname = hash_to_file[h]
            ext = os.path.splitext(fname)[1].lower()
            url = html_module.escape(
                attachment_url(fname, prefix=attachment_prefix),
                quote=True,
            )
            alt = html_module.escape(fname, quote=True)
            if ext in IMAGE_EXTS_LOCAL:
                return f'<img src="{url}" alt="{alt}">'
            else:
                return f'<a href="{url}">{alt}</a>'
        return (
            f'<img src="{attachment_url(h, prefix=attachment_prefix)}" '
            f'alt="{h}">'
        )

    c = _evernote_codeblocks_to_html(content)
    c = re.sub(r'<img[^>]*src="data:image/svg\+xml[^"]*"[^>]*/?\s*>', '', c)
    c = re.sub(r'<img[^>]*src="data:image/svg\+xml[^"]*"[^>]*>\s*</img>', '', c)
    c = EN_MEDIA_PATTERN.sub(en_media_to_img, c)
    c = re.sub(r'<\?xml[^?]*\?>', '', c)
    c = re.sub(r'<!DOCTYPE[^>]*>', '', c)
    c = re.sub(r'<en-note[^>]*>', '<div>', c)
    c = re.sub(r'</en-note>', '</div>', c)
    c = re.sub(r'<en-todo[^>]*checked="true"[^>]*>', '[x] ', c)
    c = re.sub(r'<en-todo[^>]*>', '[ ] ', c)
    c = re.sub(r'</en-todo>', '', c)

    h2t = html2text.HTML2Text()
    h2t.body_width = 0
    h2t.ignore_links = False
    h2t.ignore_images = False
    h2t.unescape = True
    md = h2t.handle(c)
    md = re.sub(r'\n{3,}', '\n\n', md)
    md = re.sub(r'(\]\([\s\S]*?\))([^)\n]*)\!\[' , r'\1\2\n\n![' , md)
    md = re.sub(r'(\]\([\s\S]*?\))([^\n])', r'\1\n\n\2', md)
    md = re.sub(r'[ \t]+\n', '\n', md)
    md = re.sub(r'\n[ \t]+\n', '\n\n', md)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def make_clip_html(enml_content, hash_to_file=None):
    """ENML 内容转纯 HTML 文件（en-media 替换为 <img> 标签）"""
    IMAGE_EXTS_LOCAL = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}

    def en_media_to_img_full(match):
        h = match.group(1).lower()
        if hash_to_file and h in hash_to_file:
            fname = hash_to_file[h]
            ext = os.path.splitext(fname)[1].lower()
            url = html_module.escape(
                attachment_url(fname, prefix="../_attachments"),
                quote=True,
            )
            alt = html_module.escape(fname, quote=True)
            if ext in IMAGE_EXTS_LOCAL:
                return f'<img src="{url}" alt="{alt}">'
            else:
                return f'<a href="{url}">{alt}</a>'
        return (
            f'<img src="{attachment_url(h, prefix="../_attachments")}" '
            f'alt="{h}">'
        )

    c = EN_MEDIA_PATTERN.sub(en_media_to_img_full, enml_content)
    c = re.sub(r'<\?xml[^?]*\?>', '', c)
    c = re.sub(r'<!DOCTYPE[^>]*>', '', c)
    c = re.sub(r'<en-note[^>]*>', '<div>', c)
    c = re.sub(r'</en-note>', '</div>', c)
    return c.strip()


def yaml_string(value):
    """生成 YAML 兼容的双引号字符串。"""
    return json.dumps(str(value), ensure_ascii=False)


def frontmatter(
    title,
    nb_name,
    guid,
    created,
    updated,
    extra=None,
    include_title=True,
):
    fm = "---\n"
    if include_title:
        fm += f"title: {yaml_string(title)}\n"
    fm += (
        f"created: {yaml_string(created.strftime('%Y-%m-%d %H:%M:%S'))}\n"
        f"updated: {yaml_string(updated.strftime('%Y-%m-%d %H:%M:%S'))}\n"
        f"source: {yaml_string('Evernote')}\n"
        f"source_guid: {yaml_string(guid)}\n"
        f"notebook: {yaml_string(nb_name)}\n"
    )
    if extra:
        if isinstance(extra, dict):
            extra_items = extra.items()
        else:
            key, separator, value = str(extra).partition(":")
            if not separator or not re.fullmatch(r"[A-Za-z_][\w-]*", key):
                raise ValueError(f"无效的 frontmatter 扩展字段: {extra}")
            extra_items = [(key, value.strip())]
        for key, value in extra_items:
            fm += f"{key}: {yaml_string(value)}\n"
    fm += "---\n\n"
    return fm


# ─── 状态管理 ──────────────────────────────────────────────

def extract_source_guid(markdown_path):
    """读取 Markdown frontmatter 中的 source_guid。"""
    try:
        content = Path(markdown_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        closing_index = next(
            index
            for index, line in enumerate(lines[1:], 1)
            if line.strip() == "---"
        )
    except StopIteration:
        return None
    frontmatter_content = "\n".join(lines[1:closing_index])
    match = re.search(
        r"(?m)^source_guid:\s*(.+?)\s*$",
        frontmatter_content,
    )
    if not match:
        return None
    raw_value = match.group(1).strip()
    if raw_value.startswith('"'):
        try:
            return str(json.loads(raw_value))
        except (json.JSONDecodeError, TypeError):
            return None
    return raw_value.strip("'")


def resolve_note_path(folder, title, guid, existing_guid_map):
    """按 GUID 复用文件；同标题冲突时追加 GUID 前八位。"""
    existing = existing_guid_map.get(guid)
    if existing and existing.get("file"):
        return Path(existing["file"])

    folder = Path(folder)
    candidate = folder / f"{safe_filename(title)}.md"
    if not candidate.exists() or extract_source_guid(candidate) == guid:
        return candidate

    compact_guid = re.sub(r"[^0-9A-Za-z]", "", str(guid))
    suffix = compact_guid[:8] or hashlib.sha256(
        str(guid).encode("utf-8")
    ).hexdigest()[:8]
    suffixed = folder / f"{safe_filename(title)}_{suffix}.md"
    if not suffixed.exists() or extract_source_guid(suffixed) == guid:
        return suffixed

    full_suffix = hashlib.sha256(str(guid).encode("utf-8")).hexdigest()
    return folder / f"{safe_filename(title)}_{full_suffix}.md"


def load_state(state_file):
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'last_sync': None, 'synced_guids': {}, 'progress': {'notebook_idx': 0, 'note_idx': 0}}


def save_state(state_file, state):
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with state_file.open('w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def prepare_sync_state(state, target_notebook):
    """同步范围变化时重置断点，避免把旧索引套到新笔记本列表。"""
    if state.get("target_notebook") != target_notebook:
        state["progress"] = {"notebook_idx": 0, "note_idx": 0}
    state["target_notebook"] = target_notebook
    return state


def scan_local_vault(vault_path):
    guid_map = {}
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d != '.obsidian']
        for file in files:
            if not file.endswith('.md'):
                continue
            fp = os.path.join(root, file)
            try:
                mtime_ms = int(os.path.getmtime(fp) * 1000)
                guid = extract_source_guid(fp)
                if guid:
                    guid_map[guid] = {'file': fp, 'local_updated_ms': mtime_ms}
            except Exception:
                continue
    return guid_map


def find_all_note_metadata(
    note_store,
    token,
    notebook_guid,
    page_size=250,
):
    """分页获取笔记本中的全部有效笔记元数据。"""
    note_filter = NoteStore.NoteFilter(
        notebookGuid=notebook_guid,
        inactive=False,
    )
    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeCreated=True,
        includeUpdated=True,
    )
    notes = []
    offset = 0
    while True:
        result = note_store.findNotesMetadata(
            token,
            note_filter,
            offset,
            page_size,
            result_spec,
        )
        page = list(result.notes or [])
        if not page:
            break
        notes.extend(page)
        offset += len(page)
        if offset >= result.totalNotes:
            break
    return notes


# ─── 主同步 ────────────────────────────────────────────────

def sync_to_obsidian(
    vault_path,
    state_file=None,
    max_sync_per_run=DEFAULT_MAX_SYNC_PER_RUN,
    target_notebook=None,
    api_delay=DEFAULT_API_DELAY,
):
    vault_path = Path(vault_path)
    state_file = (
        Path(state_file)
        if state_file is not None
        else vault_path / ".yinxiang_sync_state.json"
    )
    print("=" * 60)
    print("🔄 印象笔记 -> Obsidian 增量同步")
    print("=" * 60)
    print(f"目标: {vault_path}")
    print(
        f"本次上限: {max_sync_per_run} 条 | "
        f"HTML片段阈值: {CLIP_SIZE_THRESHOLD // 1024} KB"
    )
    print()

    token, note_store_url = load_config()
    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return False

    note_store = create_note_store(note_store_url, token)

    state = prepare_sync_state(
        load_state(state_file),
        target_notebook,
    )
    synced_guids = state.get('synced_guids', {})
    progress = state.get('progress', {'notebook_idx': 0, 'note_idx': 0})

    if state.get('last_sync'):
        dt = datetime.fromtimestamp(state['last_sync'] / 1000)
        print(f"上次同步: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"已同步: {len(synced_guids)} 条")
    else:
        print("首次同步：全量")
    print()

    print("🔍 扫描本地 vault...")
    local_guid_map = scan_local_vault(vault_path)
    print(f"   本地已有笔记: {len(local_guid_map)} 条\n")

    try:
        notebooks = note_store.listNotebooks(token)
    except Exception as e:
        print(f"❌ 获取笔记本列表失败: {e}")
        return False

    print(f"📓 印象笔记: {len(notebooks)} 个笔记本\n")
    (vault_path / ".obsidian").mkdir(parents=True, exist_ok=True)

    new_notes = updated = skipped = errors = sync_count = 0
    total_notebooks = len(notebooks)

    # 过滤到目标笔记本（仅当 target_notebook 设置时生效）
    if target_notebook:
        notebooks = [nb for nb in notebooks if nb.name == target_notebook]
        total_notebooks = len(notebooks)
        if total_notebooks == 0:
            print(f"❌ 未找到笔记本: {target_notebook}")
            return False
        print(f"🎯 只同步笔记本: {target_notebook}\n")

    initial_notebook_idx = progress.get("notebook_idx", 0)
    initial_note_idx = progress.get("note_idx", 0)
    for nb_idx in range(initial_notebook_idx, total_notebooks):
        nb = notebooks[nb_idx]
        progress['notebook_idx'] = nb_idx
        start_note_idx = (
            initial_note_idx
            if nb_idx == initial_notebook_idx
            else 0
        )
        progress['note_idx'] = start_note_idx
        save_state(state_file, state)

        nb_folder = vault_path / safe_filename(nb.name)
        nb_folder.mkdir(parents=True, exist_ok=True)
        (nb_folder / "_attachments").mkdir(exist_ok=True)
        (nb_folder / "_clips").mkdir(exist_ok=True)

        try:
            notes_meta = find_all_note_metadata(
                note_store,
                token,
                nb.guid,
            )
        except Exception as e:
            print(f"  ⚠️ 获取失败: {nb.name}: {e}")
            errors += 1
            continue

        if not notes_meta:
            print(f"  [{nb_idx+1}/{total_notebooks}] 📓 {nb.name}: 0 条")
            continue

        print(f"  [{nb_idx+1}/{total_notebooks}] 📓 {nb.name}: {len(notes_meta)} 条")

        for meta_idx in range(start_note_idx, len(notes_meta)):
            meta = notes_meta[meta_idx]
            progress['note_idx'] = meta_idx
            save_state(state_file, state)

            if sync_count >= max_sync_per_run:
                print(f"\n⚠️  达上限（{max_sync_per_run} 条），下次继续")
                state['last_sync'] = int(time.time() * 1000)
                save_state(state_file, state)
                return errors == 0

            ev_updated = getattr(meta, 'updated', 0) or 0
            if meta.guid in local_guid_map:
                if ev_updated <= local_guid_map[meta.guid]['local_updated_ms']:
                    skipped += 1
                    continue
                need_sync = 'update'
            else:
                need_sync = 'new'

            try:
                note = note_store.getNote(token, meta.guid, True, True, True, True)
            except Exception as e:
                print(f"     ⚠️ 获取失败: {meta.title[:30]}: {e}")
                errors += 1
                continue

            # ── 提取附件 ──
            resources = extract_resources(note)
            att_dir = nb_folder / "_attachments"
            hash_to_file = save_attachments(resources, str(att_dir))

            # ── 保存原始 ENML（用于 clip 生成，make_replacer 会修改 note.content） ──
            original_content = note.content

            # ── 替换 en-media 引用 ──
            def make_replacer():
                def replacer(m):
                    h = m.group(1)
                    if h in hash_to_file:
                        return make_attachment_link(hash_to_file[h])
                    return ''
                return replacer

            # 自闭合 en-media
            note.content = re.sub(
                r'<en-media[^>]*hash="([^"]*)"[^>]*/>',
                make_replacer(),
                note.content or ''
            )

            # ── 清理 ENML 结构 ──
            raw = re.sub(r'<\?xml[^?]*\?>', '',
                re.sub(r'<!DOCTYPE[^>]*>', '',
                    re.sub(r'<en-note[^>]*>', '',
                        re.sub(r'</en-note>', '', original_content or ''))))

            # ── 判断笔记类型 ──
            has_named_resource = any(resource_has_filename(r) for r in (note.resources or []))
            raw_content = original_content or ''
            is_clip = is_enml_clip(raw_content) or is_web_clip_by_content(raw_content)
            has_inline_media = has_en_media(raw_content) and not has_named_resource
            size_kb = len(raw) / 1024

            dt_c = datetime.fromtimestamp(note.created / 1000)
            dt_u = datetime.fromtimestamp(note.updated / 1000) if note.updated else dt_c
            # ══════════════════════════════════════════════════════
            # 类型 2：长网页片段 ≥200KB → 网页裁剪存 HTML，否则转 Markdown
            # ══════════════════════════════════════════════════════
            if is_clip and size_kb >= CLIP_SIZE_THRESHOLD / 1024:
                if is_enml_clip(original_content):
                    clip_filename = clip_filename_for_guid(meta.guid)
                    clip_dir = nb_folder / "_clips"
                    clip_fp = clip_dir / clip_filename
                    with open(clip_fp, 'w', encoding='utf-8') as f:
                        f.write(f"<!-- source_guid: {meta.guid} -->\n")
                        f.write(f"<!-- notebook: {nb.name} -->\n")
                        f.write(make_clip_html(original_content or '', hash_to_file))
                    md = frontmatter(
                        note.title,
                        nb.name,
                        note.guid,
                        dt_c,
                        dt_u,
                        'type: webclip',
                        include_title=False,
                    )
                    md += f"# {note.title}\n\n![[_clips/{clip_filename}]]\n"
                    icon = '🔗'
                    clip_target = clip_filename
                else:
                    md_body = html_to_md(original_content or '', hash_to_file)
                    md_body = simplify_markdown(md_body, note.title)
                    md = frontmatter(
                        note.title,
                        nb.name,
                        note.guid,
                        dt_c,
                        dt_u,
                        'type: webclip',
                        include_title=False,
                    )
                    md += f"# {note.title}\n\n{md_body}\n"
                    icon = '📄'
                    clip_target = None

            # ══════════════════════════════════════════════════════
            # 类型 3：网页裁剪 <200KB → 转 Markdown
            # ══════════════════════════════════════════════════════
            elif is_clip and size_kb < CLIP_SIZE_THRESHOLD / 1024:  # size_kb 是 KB，CLIP_SIZE_THRESHOLD 是 bytes
                md_body = html_to_md(original_content or '', hash_to_file)
                md_body = simplify_markdown(md_body, note.title)
                md = frontmatter(
                    note.title,
                    nb.name,
                    note.guid,
                    dt_c,
                    dt_u,
                    include_title=False,
                )
                md += f"# {note.title}\n\n{md_body}\n"
                icon = '📄'
                clip_target = None

            # ══════════════════════════════════════════════════════
            # 类型 1：有原始文件名的附件笔记（非 clip 时）
            # ══════════════════════════════════════════════════════
            elif has_named_resource:
                if has_inline_media:
                    md_body = html_to_md(original_content or '', hash_to_file)
                else:
                    md_body = enml_to_markdown(note.content or '')
                md_body = simplify_markdown(md_body, note.title)
                md = frontmatter(
                    note.title,
                    nb.name,
                    note.guid,
                    dt_c,
                    dt_u,
                    include_title=False,
                )
                md += f"# {note.title}\n\n{md_body}\n"
                md += make_attachments_section(
                    hash_to_file,
                    referenced_attachment_filenames(md_body, hash_to_file),
                )
                icon = '📎'
                clip_target = None

            # ══════════════════════════════════════════════════════
            # 类型 5：内嵌图片笔记（有 en-media 但无 fileName，非 clip）
            # ══════════════════════════════════════════════════════
            elif has_inline_media:
                md_body = html_to_md(original_content or '', hash_to_file)
                md_body = simplify_markdown(md_body, note.title)
                md = frontmatter(
                    note.title,
                    nb.name,
                    note.guid,
                    dt_c,
                    dt_u,
                    'type: inline-images',
                    include_title=False,
                )
                md += f"# {note.title}\n\n{md_body}\n"
                md += make_attachments_section(
                    hash_to_file,
                    referenced_attachment_filenames(md_body, hash_to_file),
                )
                icon = '🖼️'
                clip_target = None

            # ══════════════════════════════════════════════════════
            # 类型 4：纯文本笔记
            # ══════════════════════════════════════════════════════
            else:
                md_body = enml_to_markdown(note.content or '')
                md_body = simplify_markdown(md_body, note.title)
                md = frontmatter(
                    note.title,
                    nb.name,
                    note.guid,
                    dt_c,
                    dt_u,
                    include_title=False,
                )
                md += f"# {note.title}\n\n{md_body}\n"
                icon = '📝'
                clip_target = None

            # ── 写入文件 ──
            md_fp = resolve_note_path(
                nb_folder,
                note.title,
                note.guid,
                local_guid_map,
            )
            try:
                md_fp.write_text(md, encoding="utf-8")
            except Exception as e:
                print(f"     ❌ 写入失败: {meta.title[:30]}: {e}")
                errors += 1
                continue

            if need_sync == 'new':
                new_notes += 1
            else:
                updated += 1

            sync_count += 1
            print(f"     {icon} {meta.title[:45]}")
            if clip_target:
                print(f"        ({size_kb:.0f}KB → _clips/{clip_target})")

            synced_guids[meta.guid] = {
                'file': str(md_fp), 'ev_updated': ev_updated,
                'notebook': nb.name, 'title': note.title
            }
            local_guid_map[meta.guid] = {
                "file": str(md_fp),
                "local_updated_ms": int(md_fp.stat().st_mtime * 1000),
            }
            time.sleep(api_delay)

        progress['note_idx'] = 0
        time.sleep(0.5)

    state['last_sync'] = int(time.time() * 1000)
    state['synced_guids'] = synced_guids
    state['progress'] = {'notebook_idx': 0, 'note_idx': 0}
    save_state(state_file, state)

    print()
    print("=" * 60)
    print("🎉 同步完成!")
    print("=" * 60)
    print(f"🆕 新增: {new_notes}  🔄 更新: {updated}  ⏭️  跳过: {skipped}  ❌ 错误: {errors}")
    print()
    print("📝 = 纯文本  📎 = 附件笔记  🖼 = 内嵌图片  📄 = 网页裁剪<200KB转MD  🔗 = 网页裁剪>=200KB存HTML")
    return errors == 0


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def nonnegative_float(value):
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须是大于或等于 0 的数字")
    return parsed


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(description='印象笔记 -> Obsidian 增量同步')
    parser.add_argument(
        "--vault",
        type=Path,
        default=load_setting("OBSIDIAN_VAULT_PATH"),
        help="Obsidian vault 路径；也可在环境变量或 .env 中设置 OBSIDIAN_VAULT_PATH",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="同步状态文件（默认 <vault>/.yinxiang_sync_state.json）",
    )
    parser.add_argument(
        "--max-sync",
        type=positive_int,
        default=DEFAULT_MAX_SYNC_PER_RUN,
        help=f"本次最多同步的笔记数（默认 {DEFAULT_MAX_SYNC_PER_RUN}）",
    )
    parser.add_argument(
        "--api-delay",
        type=nonnegative_float,
        default=DEFAULT_API_DELAY,
        help=f"每篇笔记后的等待秒数（默认 {DEFAULT_API_DELAY}）",
    )
    parser.add_argument('--notebook', '-n', type=str, default=None,
                        help='只同步此笔记本（名称匹配）')
    args = parser.parse_args()
    if not args.vault:
        parser.error("请使用 --vault 或 OBSIDIAN_VAULT_PATH 指定 Obsidian vault")
    succeeded = sync_to_obsidian(
        vault_path=args.vault,
        state_file=args.state_file,
        max_sync_per_run=args.max_sync,
        target_notebook=args.notebook,
        api_delay=args.api_delay,
    )
    return 0 if succeeded else 1


if __name__ == '__main__':
    raise SystemExit(main())
