#!/usr/bin/env python3
"""永久删除印象笔记废纸篓中的全部笔记。"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .list_trash import find_deleted_notes
    from .runtime import (
        configure_utf8_output,
        create_note_store,
        load_config,
    )
except ImportError:
    from list_trash import find_deleted_notes
    from runtime import configure_utf8_output, create_note_store, load_config


CONFIRMATION_TEXT = "DELETE_ALL"


def empty_trash(confirm_text):
    """永久删除废纸篓；确认文字不匹配时不读取配置、不调用 API。"""
    if confirm_text != CONFIRMATION_TEXT:
        print(f"❌ 已取消：必须完整输入确认词 {CONFIRMATION_TEXT}")
        return False

    token, note_store_url = load_config()
    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return False

    print("🔄 正在连接印象笔记...")
    note_store = create_note_store(note_store_url, token)
    print("✅ 连接成功\n")
    print("🔍 扫描废纸篓中的笔记...")
    try:
        deleted_notes = find_deleted_notes(
            note_store,
            token,
            max_count=None,
        )
    except Exception as exc:
        print(f"❌ 扫描失败: {exc}")
        return False

    print(f"📋 废纸篓中共有 {len(deleted_notes)} 条笔记\n")
    if not deleted_notes:
        print("✅ 废纸篓已是空的")
        return True

    for note in deleted_notes:
        print(f"  🗑️  {note.title}")
    print("\n⚠️  开始永久删除，删除后无法恢复...")

    count = 0
    for note in deleted_notes:
        try:
            note_store.expungeNote(token, note.guid)
            count += 1
            print(f"  ✅ 永久删除: {note.title}")
        except Exception as exc:
            print(f"  ❌ 删除失败: {note.title} - {exc}")

    print(f"\n清空结束：成功 {count} 条，失败 {len(deleted_notes) - count} 条")
    return count == len(deleted_notes)


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        description="永久删除印象笔记废纸篓中的全部笔记（无法恢复）"
    )
    parser.add_argument(
        "--confirm",
        required=True,
        metavar=CONFIRMATION_TEXT,
        help=f"必须完整输入 {CONFIRMATION_TEXT} 才会执行永久删除",
    )
    args = parser.parse_args()
    return 0 if empty_trash(args.confirm) else 1


if __name__ == "__main__":
    raise SystemExit(main())
