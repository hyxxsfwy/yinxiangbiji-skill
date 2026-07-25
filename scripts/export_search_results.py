#!/usr/bin/env python3
"""按日期和关键词搜索印象笔记，并导出指定数量到 Obsidian。"""

import argparse
from datetime import date, datetime
from pathlib import Path
import sys

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.type.ttypes import NoteSortOrder
import thrift.protocol.TBinaryProtocol as TBinaryProtocol
import thrift.transport.THttpClient as THttpClient

try:
    from .list_notebooks import load_config
except ImportError:
    from list_notebooks import load_config

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
        safe_filename,
        save_attachments,
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
        safe_filename,
        save_attachments,
    )


def build_keyword_queries(keywords, since):
    since_text = since.strftime("%Y%m%d")
    return [f"created:{since_text} {keyword}" for keyword in keywords]


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

    return sorted(notes_by_guid.values(), key=sort_key, reverse=True)[:limit]


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
        result = note_store.findNotesMetadata(
            token,
            note_filter,
            0,
            max_per_keyword,
            result_spec,
        )
        batches.append(list(result.notes or []))
        totals.append(result.totalNotes)
    return batches, totals


def export_note_to_obsidian(note, notebook_name, target_dir):
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
    content = note.content or ""
    is_web_clip = is_enml_clip(content) or is_web_clip_by_content(content)
    contains_media = has_en_media(content)
    extra = None
    if is_web_clip:
        body = html_to_md(content, hash_to_file)
        extra = "type: webclip"
    elif contains_media:
        body = html_to_md(content, hash_to_file)
        extra = "type: inline-images"
    else:
        body = enml_to_markdown(content)

    markdown = frontmatter(
        note.title,
        notebook_name,
        note.guid,
        created,
        updated,
        extra,
    )
    markdown += f"# {note.title}\n\n{body}\n"
    if resources:
        markdown += make_attachments_section(hash_to_file)

    output_path = target_dir / f"{safe_filename(note.title)}.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

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
    parser.add_argument("--limit", type=int, default=3, help="导出数量")
    parser.add_argument(
        "--max-per-keyword",
        type=int,
        default=250,
        help="每个关键词最多拉取的候选数",
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Obsidian 目标目录",
    )
    args = parser.parse_args()

    token, note_store_url = load_config()
    if not token or not note_store_url:
        parser.error("未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")

    transport = THttpClient.THttpClient(note_store_url)
    transport.setCustomHeaders({"Authorization": f"Bearer {token}"})
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    note_store = NoteStore.Client(protocol)

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
            )
        )

    print(f"\n已导出到: {args.target}")
    for exported_path in exported_paths:
        print(f"- {exported_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
