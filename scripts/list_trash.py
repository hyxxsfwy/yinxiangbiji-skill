#!/usr/bin/env python3
"""查看印象笔记废纸篓中的笔记。"""

import argparse
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .runtime import (
        configure_utf8_output,
        create_note_store,
        load_config,
    )
except ImportError:
    from runtime import configure_utf8_output, create_note_store, load_config

import evernote.edam.notestore.NoteStore as NoteStore


def find_deleted_notes(note_store, token, max_count=None):
    """分页查询废纸篓，最多返回 ``max_count`` 条。"""
    if max_count is not None and max_count <= 0:
        return []

    deleted_notes = []
    offset = 0
    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeDeleted=True,
        includeCreated=True,
    )

    while True:
        remaining = (
            None
            if max_count is None
            else max_count - len(deleted_notes)
        )
        if remaining is not None and remaining <= 0:
            break
        page_size = 100 if remaining is None else min(100, remaining)
        result = note_store.findNotesMetadata(
            token,
            NoteStore.NoteFilter(inactive=True),
            offset,
            page_size,
            result_spec,
        )
        notes = list(result.notes or [])
        if not notes:
            break

        deleted_notes.extend(
            note
            for note in notes
            if (getattr(note, "deleted", 0) or 0) > 0
        )
        offset += len(notes)
        if offset >= result.totalNotes:
            break

    if max_count is not None:
        return deleted_notes[:max_count]
    return deleted_notes


def list_trash(max_count=500):
    """列出废纸篓中的笔记。"""
    token, note_store_url = load_config()
    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return []

    print("🔄 正在连接印象笔记...")
    note_store = create_note_store(note_store_url, token)
    print("✅ 连接成功\n")

    try:
        deleted_notes = find_deleted_notes(
            note_store,
            token,
            max_count=max_count,
        )
    except Exception as exc:
        print(f"❌ 扫描出错: {exc}")
        return []

    print(f"{'=' * 60}")
    print(f"🗑️  废纸篓（显示 {len(deleted_notes)} 条）")
    print(f"{'=' * 60}\n")
    if not deleted_notes:
        print("✅ 废纸篓是空的")
        return []

    for index, note in enumerate(deleted_notes, 1):
        deleted_at = datetime.fromtimestamp(note.deleted / 1000)
        print(f"{index}. {note.title}")
        print(f"   删除时间: {deleted_at:%Y-%m-%d %H:%M}")
        print(f"   GUID: {note.guid}\n")
    return deleted_notes


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="只读列出印象笔记废纸篓")
    parser.add_argument(
        "--max-count",
        type=positive_int,
        default=500,
        help="最多显示的笔记数（默认 500）",
    )
    args = parser.parse_args()
    list_trash(max_count=args.max_count)


if __name__ == "__main__":
    main()
