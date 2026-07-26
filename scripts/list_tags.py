#!/usr/bin/env python3
"""
获取所有标签列表
"""

import argparse

try:
    from .runtime import (
        configure_utf8_output,
        create_note_store,
        load_config,
    )
except ImportError:
    from runtime import configure_utf8_output, create_note_store, load_config


def list_tags():
    """获取并按名称排序显示所有标签。"""
    token, note_store_url = load_config()
    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return []

    print("🔄 正在获取标签...")
    note_store = create_note_store(note_store_url, token)
    tags = note_store.listTags(token)
    print(f"\n🏷️ 标签列表 (共 {len(tags)} 个):\n")

    for tag in sorted(tags, key=lambda item: item.name.casefold()):
        print(f"  • {tag.name}")
    print(f"📊 统计: 共 {len(tags)} 个标签")
    return tags


def main():
    configure_utf8_output()
    argparse.ArgumentParser(description="列出印象笔记中的全部标签").parse_args()
    list_tags()


if __name__ == "__main__":
    main()
