#!/usr/bin/env python3
"""
删除印象笔记（移至废纸篓）
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


def get_note_title(note_store, token, guid):
    """获取笔记标题"""
    try:
        note = note_store.getNote(token, guid, False, False, False, False)
        return note.title
    except Exception:
        return None


def delete_note(guid, confirm=False):
    """删除笔记（移至废纸篓，客户端清空废纸篓后永久删除）"""
    token, note_store_url = load_config()

    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return False

    print(f"🔄 正在连接印象笔记...")
    note_store = create_note_store(note_store_url, token)

    print("✅ 连接成功")
    print()

    # 先获取笔记标题
    title = get_note_title(note_store, token, guid)
    if not title:
        print(f"❌ 未找到笔记 GUID: {guid}")
        return False

    print(f"📝 准备删除笔记: {title}")
    print(f"   GUID: {guid}")
    print()

    if not confirm:
        print("ℹ️ 预览完成；未指定 --confirm，不会删除")
        return True

    print("🗑️  将笔记移至废纸篓...")

    try:
        note_store.deleteNote(token, guid)
        print(f"\n✅ 删除成功！笔记已移至废纸篓")
        print(f"   标题: {title}")
        print(f"   GUID: {guid}")
        print()
        print("💡 提示：笔记已进入废纸篓，在印象笔记客户端中清空废纸篓才会永久删除")
        return True
    except Exception as e:
        print(f"❌ 删除失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        description="预览或将指定印象笔记移至废纸篓"
    )
    parser.add_argument("--guid", required=True, help="笔记 GUID")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认移至废纸篓；省略时只预览",
    )
    args = parser.parse_args()
    succeeded = delete_note(args.guid, args.confirm)
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
