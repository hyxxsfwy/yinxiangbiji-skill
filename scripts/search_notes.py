#!/usr/bin/env python3
"""
搜索印象笔记
用法: python search_notes.py "关键词"
       python search_notes.py "标题:关键词"
       python search_notes.py "创建时间:2024-01-01"
       python search_notes.py "any:关键词1 关键词2"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .list_notebooks import load_config
except ImportError:
    from list_notebooks import load_config

import evernote.edam.notestore.NoteStore as NoteStore
import thrift.transport.THttpClient as THttpClient
import thrift.protocol.TBinaryProtocol as TBinaryProtocol


def parse_query(query):
    """解析搜索语法"""
    filter = NoteStore.NoteFilter()

    if query.startswith('标题:'):
        filter.words = f'intitle:{query[3:]}'
    elif query.startswith('创建时间:'):
        filter.words = f"created:{query[5:].replace('-', '')}"
    elif query.startswith('any:'):
        # any:关键词1 关键词2 -> 匹配任意关键词
        keywords = query[4:].strip()
        filter.words = f'any: {keywords}'
    else:
        # 默认：搜索标题和正文
        filter.words = query

    return filter


def search_notes(query, max_results=50):
    """搜索笔记"""
    token, note_store_url = load_config()

    if not token:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN")
        return []

    if not note_store_url:
        note_store_url = "https://app.yinxiang.com/shard/s16/notestore"

    print(f"🔄 正在连接印象笔记...")
    print(f"✅ Token: {token[:25]}...")
    print(f"🔍 搜索: {query}")
    print()

    transport = THttpClient.THttpClient(note_store_url)
    transport.setCustomHeaders({"Authorization": f"Bearer {token}"})
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    note_store = NoteStore.Client(protocol)

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
        result = note_store.findNotesMetadata(token, note_filter, 0, max_results, result_spec)

        print(f"{'='*60}")
        print(f"📋 搜索结果 (共 {result.totalNotes} 条，显示前 {len(result.notes)} 条)")
        print(f"{'='*60}")
        print()

        if not result.notes:
            print("未找到匹配的笔记")
            return []

        # 获取笔记本名称映射
        notebooks = note_store.listNotebooks(token)
        notebook_map = {nb.guid: nb.name for nb in notebooks}

        for i, note in enumerate(result.notes, 1):
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

        if result.totalNotes > max_results:
            print(f"⚠️ 还有 {result.totalNotes - max_results} 条结果未显示")

        return result.notes

    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python search_notes.py \"关键词\"")
        print("       python search_notes.py \"标题:关键词\"")
        print("       python search_notes.py \"创建时间:2024-01-01\"")
        print("       python search_notes.py \"any:关键词1 关键词2\"")
        sys.exit(1)

    query = ' '.join(sys.argv[1:])
    search_notes(query)
