#!/usr/bin/env python3
"""
创建印象笔记
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

import evernote.edam.type.ttypes as Types


def get_notebook_guid(note_store, token, notebook_name):
    """根据笔记本名获取 GUID"""
    notebooks = note_store.listNotebooks(token)
    for nb in notebooks:
        if nb.name == notebook_name:
            return nb.guid
    return None


def get_tag_guids(note_store, token, tag_names):
    """根据标签名列表返回 ``(GUID 列表, 缺失标签列表)``。"""
    if not tag_names:
        return [], []
    tag_map = {
        tag.name: tag.guid
        for tag in note_store.listTags(token)
    }
    tag_guids = [
        tag_map[name]
        for name in tag_names
        if name in tag_map
    ]
    missing = [name for name in tag_names if name not in tag_map]
    return tag_guids, missing


def create_note(title, content, notebook_name=None, tag_names=None):
    """创建笔记"""
    token, note_store_url = load_config()

    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return None

    print(f"🔄 正在连接印象笔记...")
    note_store = create_note_store(note_store_url, token)

    print("✅ 连接成功")
    print()

    # 构建笔记
    note = Types.Note()
    note.title = title
    note.content = content

    # 设置笔记本
    if notebook_name:
        guid = get_notebook_guid(note_store, token, notebook_name)
        if guid:
            note.notebookGuid = guid
            print(f"📓 目标笔记本: {notebook_name}")
        else:
            print(f"❌ 未找到笔记本: {notebook_name}")
            return None

    # 设置标签
    if tag_names:
        tag_guids, missing_tags = get_tag_guids(
            note_store,
            token,
            tag_names,
        )
        if missing_tags:
            print(f"❌ 标签不存在: {', '.join(missing_tags)}")
            return None
        if tag_guids:
            note.tagGuids = tag_guids
            print(f"🏷️ 标签: {', '.join(tag_names)}")

    print(f"📝 创建笔记: {title}")

    try:
        result = note_store.createNote(token, note)
        print(f"✅ 创建成功!")
        print(f"   GUID: {result.guid}")
        print(f"   创建时间: {result.created}")
        return result
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def comma_separated(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="在印象笔记中创建笔记")
    parser.add_argument("--title", required=True, help="笔记标题")
    parser.add_argument(
        "--content",
        required=True,
        help="合法的 ENML 内容，例如 <en-note>内容</en-note>",
    )
    parser.add_argument("--notebook", help="目标笔记本名称")
    parser.add_argument(
        "--tags",
        type=comma_separated,
        help="逗号分隔的现有标签名称",
    )
    args = parser.parse_args()
    result = create_note(
        args.title,
        args.content,
        args.notebook,
        args.tags,
    )
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
