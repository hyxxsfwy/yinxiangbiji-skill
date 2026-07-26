#!/usr/bin/env python3
"""
更新印象笔记
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


def get_note(note_store, token, guid):
    """获取笔记"""
    return note_store.getNote(token, guid, True, False, False, False)


def has_requested_updates(title, content, add_tags, remove_tags):
    return any(
        (
            title is not None,
            content is not None,
            bool(add_tags),
            bool(remove_tags),
        )
    )


def update_note(guid, title=None, content=None, add_tags=None, remove_tags=None):
    """更新笔记"""
    if not has_requested_updates(title, content, add_tags, remove_tags):
        print("❌ 未指定任何更新内容")
        return None

    token, note_store_url = load_config()

    if not token or not note_store_url:
        print("❌ 错误: 未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
        return None

    print(f"🔄 正在连接印象笔记...")
    note_store = create_note_store(note_store_url, token)

    print("✅ 连接成功")
    print()

    # 获取原笔记
    try:
        original = get_note(note_store, token, guid)
        print(f"📝 当前笔记: {original.title}")
    except Exception as e:
        print(f"❌ 获取笔记失败: {e}")
        return None

    # 构建更新对象
    update_note = Types.Note()
    update_note.guid = guid
    update_note.title = original.title
    update_note.content = original.content if content is None else content
    update_note.tagGuids = list(original.tagGuids) if original.tagGuids else []
    changed = False

    tag_map = {}
    if add_tags or remove_tags:
        tag_map = {
            tag.name: tag.guid
            for tag in note_store.listTags(token)
        }

    # 添加标签
    if add_tags:
        for tag_name in add_tags:
            tag_guid = tag_map.get(tag_name)
            if tag_guid and tag_guid not in update_note.tagGuids:
                update_note.tagGuids.append(tag_guid)
                changed = True
                print(f"   🏷️ +添加标签: {tag_name}")
            elif not tag_guid:
                print(f"   ⚠️ 标签不存在: {tag_name}")

    # 移除标签
    if remove_tags:
        for tag_name in remove_tags:
            tag_guid = tag_map.get(tag_name)
            if tag_guid and tag_guid in update_note.tagGuids:
                update_note.tagGuids.remove(tag_guid)
                changed = True
                print(f"   🏷️ -移除标签: {tag_name}")

    if title is not None:
        update_note.title = title
        changed = changed or title != original.title
        print(f"   📝 新标题: {title}")

    if content is not None:
        changed = changed or content != original.content
        print(f"   📄 内容已更新")

    if not changed:
        print("❌ 请求不会产生实际变化，已取消更新")
        return None

    try:
        result = note_store.updateNote(token, update_note)
        print(f"\n✅ 更新成功!")
        print(f"   GUID: {result.guid}")
        print(f"   更新时间: {result.updated}")
        return result
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def comma_separated(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="更新指定的印象笔记")
    parser.add_argument("--guid", required=True, help="笔记 GUID")
    parser.add_argument("--title", help="新标题")
    parser.add_argument("--content", help="新的完整 ENML 内容")
    parser.add_argument(
        "--add-tags",
        type=comma_separated,
        help="要添加的现有标签，使用逗号分隔",
    )
    parser.add_argument(
        "--remove-tags",
        type=comma_separated,
        help="要移除的标签，使用逗号分隔",
    )
    args = parser.parse_args()
    if not has_requested_updates(
        args.title,
        args.content,
        args.add_tags,
        args.remove_tags,
    ):
        parser.error("至少指定 --title、--content、--add-tags 或 --remove-tags 之一")
    result = update_note(
        args.guid,
        args.title,
        args.content,
        args.add_tags,
        args.remove_tags,
    )
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
