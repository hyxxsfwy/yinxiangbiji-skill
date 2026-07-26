#!/usr/bin/env python3
"""
获取印象笔记笔记本列表
直接使用 NoteStore URL
"""

import argparse
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


def count_notebook_notes(note_store, token, notebook_guid):
    """返回指定笔记本的笔记总数。"""
    note_filter = NoteStore.NoteFilter(notebookGuid=notebook_guid)
    result_spec = NoteStore.NotesMetadataResultSpec(includeTitle=True)
    result = note_store.findNotesMetadata(
        token,
        note_filter,
        0,
        1,
        result_spec,
    )
    return result.totalNotes


def list_notebooks(verbose=False):
    """获取并显示笔记本列表"""
    print("🔄 正在连接印象笔记...")
    print()

    try:
        token, note_store_url = load_config()
        
        if not token:
            print("❌ 错误: 未找到 EVERNOTE_TOKEN")
            sys.exit(1)
        
        if not note_store_url:
            print("❌ 错误: 未找到 EVERNOTE_NOTESTORE_URL")
            print("请在 .env 文件中设置: EVERNOTE_NOTESTORE_URL=https://app.yinxiang.com/shard/s16/notestore")
            sys.exit(1)
        
        print(f"✅ NoteStore URL: {note_store_url}")
        print()

        note_store = create_note_store(note_store_url, token)

        print("✅ 成功连接到 NoteStore")
        print()

        # 获取笔记本列表
        notebooks = note_store.listNotebooks(token)

        print(f"📓 笔记本列表 (共 {len(notebooks)} 个):\n")

        for i, notebook in enumerate(notebooks, 1):
            print(f"{i}. {notebook.name}")
            
            if verbose:
                try:
                    note_count = count_notebook_notes(
                        note_store,
                        token,
                        notebook.guid,
                    )
                    print(f"   └─ 笔记数量: {note_count}")
                except Exception as e:
                    print(f"   └─ 无法获取笔记数量: {e}")

        print("\n✅ 连接成功!")
        return notebooks

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="列出印象笔记中的笔记本")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="逐个查询并显示笔记数量",
    )
    args = parser.parse_args()
    list_notebooks(verbose=args.verbose)


if __name__ == "__main__":
    main()
