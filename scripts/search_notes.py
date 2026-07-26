#!/usr/bin/env python3
"""
搜索印象笔记
支持原生印象笔记搜索语法，以及少量中文快捷写法。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

import evernote.edam.notestore.NoteStore as NoteStore


def parse_query(query):
    """解析搜索语法"""
    note_filter = NoteStore.NoteFilter()

    if query.startswith('标题:'):
        note_filter.words = f'intitle:{query[3:]}'
    elif query.startswith('创建时间:'):
        note_filter.words = f"created:{query[5:].replace('-', '')}"
    elif query.startswith('any:'):
        # any:关键词1 关键词2 -> 匹配任意关键词
        keywords = query[4:].strip()
        note_filter.words = f'any: {keywords}'
    else:
        # 默认：搜索标题和正文
        note_filter.words = query

    return note_filter


def search_notes(query, max_results=50):
    """搜索笔记"""
    token, note_store_url = load_config()

    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return []

    print(f"🔄 正在连接印象笔记...")
    print(f"🔍 搜索: {query}")
    print()

    note_store = create_note_store(note_store_url, token)

    print("✅ 连接成功")
    print()

    # 解析查询
    note_filter = parse_query(query)

    # 设置返回字段
    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeContentLength=True,
        includeCreated=True,
        includeUpdated=True,
        includeNotebookGuid=True
    )

    try:
        notes, total_notes = find_notes_metadata(
            note_store,
            token,
            note_filter,
            max_results,
            result_spec,
        )

        print(f"{'='*60}")
        print(f"📋 搜索结果 (共 {total_notes} 条，显示前 {len(notes)} 条)")
        print(f"{'='*60}")
        print()

        if not notes:
            print("未找到匹配的笔记")
            return []

        # 获取笔记本名称映射
        notebooks = note_store.listNotebooks(token)
        notebook_map = {nb.guid: nb.name for nb in notebooks}

        for i, note in enumerate(notes, 1):
            nb_name = notebook_map.get(note.notebookGuid, '未知笔记本')
            created = note.created if hasattr(note, 'created') else 0
            # 印象笔记时间戳是毫秒
            from datetime import datetime
            dt = datetime.fromtimestamp(created / 1000) if created else None
            date_str = dt.strftime('%Y-%m-%d') if dt else '未知'

            print(f"{i}. {note.title}")
            print(f"   📓 笔记本: {nb_name}")
            print(f"   📅 创建: {date_str}")
            if hasattr(note, 'contentLength') and note.contentLength:
                print(f"   📏 内容长度: {note.contentLength} 字符")
            print()

        if total_notes > max_results:
            print(f"⚠️ 还有 {total_notes - max_results} 条结果未显示")

        return notes

    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        description="使用印象笔记搜索语法查询标题和正文",
        epilog=(
            '示例：search_notes.py "intitle:Agent" --max-results 10；'
            '也支持“标题:关键词”“创建时间:2024-01-01”和“any:词1 词2”。'
        ),
    )
    parser.add_argument("query", nargs="+", help="搜索表达式")
    parser.add_argument(
        "--max-results",
        type=positive_int,
        default=50,
        help="最多显示的结果数（默认 50）",
    )
    args = parser.parse_args()
    search_notes(" ".join(args.query), max_results=args.max_results)


if __name__ == "__main__":
    main()
