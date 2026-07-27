#!/usr/bin/env python3
"""按日期和关键词搜索印象笔记，并导出指定数量到 Obsidian。"""

import argparse
from datetime import date, datetime
from pathlib import Path

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.type.ttypes import NoteSortOrder

try:
    from .knowledge_base import finalize_knowledge_base, month_folder_name
except ImportError:
    from knowledge_base import finalize_knowledge_base, month_folder_name

try:
    from .runtime import (
        configure_utf8_output,
        create_note_store,
        find_notes_metadata,
        load_config,
    )
except ImportError:
    from runtime import (
        configure_utf8_output,
        create_note_store,
        find_notes_metadata,
        load_config,
    )

try:
    from .sync_to_obsidian import (
        enml_to_markdown,
        extract_resources,
        frontmatter,
        has_en_media,
        html_to_md,
        is_enml_clip,
        is_web_clip_by_content,
        make_attachments_section,
        referenced_attachment_filenames,
        resolve_note_path,
        save_attachments,
        simplify_markdown,
    )
except ImportError:
    from sync_to_obsidian import (
        enml_to_markdown,
        extract_resources,
        frontmatter,
        has_en_media,
        html_to_md,
        is_enml_clip,
        is_web_clip_by_content,
        make_attachments_section,
        referenced_attachment_filenames,
        resolve_note_path,
        save_attachments,
        simplify_markdown,
    )


def build_keyword_queries(keywords, since):
    since_text = since.strftime("%Y%m%d")
    return [f"created:{since_text} {keyword}" for keyword in keywords]


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def note_freshness_key(note):
    """按更新时间、创建时间和 GUID 判断同标题笔记的新旧。"""
    return (
        getattr(note, "updated", 0) or 0,
        getattr(note, "created", 0) or 0,
        str(getattr(note, "guid", "") or ""),
    )


def deduplicate_notes_by_title(notes):
    """标题完全一致时只保留最新的一篇。"""
    winners = {}
    for note in notes:
        title_key = (getattr(note, "title", "") or "").strip()
        existing = winners.get(title_key)
        if existing is None or note_freshness_key(note) > note_freshness_key(
            existing
        ):
            winners[title_key] = note
    return list(winners.values())


def select_top_notes(search_batches, keywords, limit):
    notes_by_guid = {}
    for batch in search_batches:
        for note in batch:
            existing = notes_by_guid.get(note.guid)
            if existing is None or (getattr(note, "updated", 0) or 0) > (
                getattr(existing, "updated", 0) or 0
            ):
                notes_by_guid[note.guid] = note

    folded_keywords = [keyword.casefold() for keyword in keywords]

    def sort_key(note):
        title = (getattr(note, "title", "") or "").casefold()
        title_matches = any(keyword in title for keyword in folded_keywords)
        return (
            title_matches,
            getattr(note, "updated", 0) or 0,
            getattr(note, "created", 0) or 0,
        )

    unique_titles = deduplicate_notes_by_title(notes_by_guid.values())
    return sorted(unique_titles, key=sort_key, reverse=True)[:limit]


def search_metadata_batches(
    note_store,
    token,
    keywords,
    since,
    max_per_keyword=250,
):
    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeContentLength=True,
        includeCreated=True,
        includeUpdated=True,
        includeNotebookGuid=True,
    )
    batches = []
    totals = []
    for query in build_keyword_queries(keywords, since):
        note_filter = NoteStore.NoteFilter(
            words=query,
            order=NoteSortOrder.UPDATED,
            ascending=False,
        )
        notes, total_notes = find_notes_metadata(
            note_store,
            token,
            note_filter,
            max_per_keyword,
            result_spec,
        )
        batches.append(notes)
        totals.append(total_notes)
    return batches, totals


def export_note_to_obsidian(note, notebook_name, target_dir, domain="AI"):
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    resources = extract_resources(note)
    hash_to_file = {}
    if resources:
        attachments_dir = target_dir / "_attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        hash_to_file = save_attachments(resources, str(attachments_dir))

    created = datetime.fromtimestamp(note.created / 1000)
    updated_ms = getattr(note, "updated", 0) or note.created
    updated = datetime.fromtimestamp(updated_ms / 1000)
    month_dir = target_dir / month_folder_name(created)
    month_dir.mkdir(parents=True, exist_ok=True)
    attachment_prefix = "../_attachments"
    content = note.content or ""
    is_web_clip = is_enml_clip(content) or is_web_clip_by_content(content)
    contains_media = has_en_media(content)
    if is_web_clip:
        body = html_to_md(
            content,
            hash_to_file,
            attachment_prefix=attachment_prefix,
        )
    elif contains_media:
        body = html_to_md(
            content,
            hash_to_file,
            attachment_prefix=attachment_prefix,
        )
    else:
        body = enml_to_markdown(content)
    body = simplify_markdown(body, note.title)
    extra = {
        "type": "资料",
        "domain": domain,
        "status": "待提炼",
        "tags": [],
        "review_status": "pending",
        "llm_policy": "strict",
    }

    markdown = frontmatter(
        note.title,
        notebook_name,
        note.guid,
        created,
        updated,
        extra,
        include_title=False,
    )
    markdown += f"# {note.title}\n"
    if body:
        markdown += f"\n{body}\n"
    if resources:
        markdown += make_attachments_section(
            hash_to_file,
            referenced_attachment_filenames(
                body,
                hash_to_file,
                prefix=attachment_prefix,
            ),
            prefix=attachment_prefix,
        )

    output_path = resolve_note_path(
        month_dir,
        note.title,
        note.guid,
        {},
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main():
    configure_utf8_output()

    parser = argparse.ArgumentParser(
        description="搜索最近一段时间内的相关笔记并导出到 Obsidian"
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        required=True,
        help="创建日期下限，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=["AI", "Agent", "人工智能"],
        help="任一匹配的关键词",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=3,
        help="导出数量",
    )
    parser.add_argument(
        "--max-per-keyword",
        type=positive_int,
        default=250,
        help="每个关键词最多拉取的候选数",
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Obsidian 目标目录",
    )
    parser.add_argument(
        "--domain",
        choices=("AI", "Quant", "软件工程", "投资理财", "个人成长"),
        default="AI",
        help="精选资料所属领域（默认 AI）",
    )
    args = parser.parse_args()

    token, note_store_url = load_config()
    if not token or not note_store_url:
        parser.error("未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")

    note_store = create_note_store(note_store_url, token)

    batches, totals = search_metadata_batches(
        note_store,
        token,
        args.keywords,
        args.since,
        args.max_per_keyword,
    )
    for keyword, total, batch in zip(args.keywords, totals, batches):
        print(f"关键词 {keyword}: 共 {total} 条，拉取 {len(batch)} 条候选")

    selected = select_top_notes(batches, args.keywords, args.limit)
    if not selected:
        print("未找到符合条件的笔记")
        return 1

    notebooks = note_store.listNotebooks(token)
    notebook_map = {notebook.guid: notebook.name for notebook in notebooks}

    print(f"\n选中前 {len(selected)} 篇：")
    exported_paths = []
    for index, metadata in enumerate(selected, 1):
        created = datetime.fromtimestamp(metadata.created / 1000)
        updated = datetime.fromtimestamp(metadata.updated / 1000)
        notebook_name = notebook_map.get(metadata.notebookGuid, "未知笔记本")
        print(
            f"{index}. {metadata.title} "
            f"(创建 {created:%Y-%m-%d}，更新 {updated:%Y-%m-%d}，"
            f"笔记本 {notebook_name})"
        )

        note = note_store.getNote(
            token,
            metadata.guid,
            True,
            True,
            True,
            True,
        )
        exported_paths.append(
            export_note_to_obsidian(
                note,
                notebook_name=notebook_name,
                target_dir=args.target,
                domain=args.domain,
            )
        )

    finalization = finalize_knowledge_base(args.target, domain=args.domain)
    print(f"\n已导出到: {args.target}")
    for exported_path in exported_paths:
        print(f"- {exported_path.relative_to(args.target)}")
    print(f"- 目录索引: {finalization.index_path}")
    if finalization.errors:
        for error in finalization.errors:
            print(f"迁移失败: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
