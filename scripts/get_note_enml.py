#!/usr/bin/env python3
"""下载指定笔记的原始 ENML 内容并分析其结构。"""

import argparse
import os
from pathlib import Path
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


def analyze_enml(content):
    """分析 ENML/HTML 内容结构，返回便于测试和复用的摘要。"""
    content = content or ""
    lowered = content.lower()
    if "<html" in lowered and "<head" in lowered and "<body" in lowered:
        kind = "html"
    elif "<en-note" in lowered:
        kind = "enml"
    else:
        kind = "fragment"

    return {
        "has_doctype": "<!doctype" in lowered,
        "has_html_tags": "<html" in lowered,
        "has_head": "<head" in lowered,
        "has_body": "<body" in lowered,
        "has_en_note": "<en-note" in lowered,
        "en_clipped": "--en-clipped-content" in content,
        "div_count": lowered.count("<div"),
        "span_count": lowered.count("<span"),
        "p_count": lowered.count("<p"),
        "kind": kind,
    }


def print_analysis(analysis):
    labels = [
        ("DOCTYPE", "has_doctype"),
        ("<html> 标签", "has_html_tags"),
        ("<head> 标签", "has_head"),
        ("<body> 标签", "has_body"),
        ("<en-note> 标签", "has_en_note"),
        ("--en-clipped-content", "en_clipped"),
    ]
    print("\n📊 内容结构分析:")
    for label, key in labels:
        print(f"  - {label}: {'✅' if analysis[key] else '❌'}")
    print(f"\n  - <div> 标签数量: {analysis['div_count']}")
    print(f"  - <span> 标签数量: {analysis['span_count']}")
    print(f"  - <p> 标签数量: {analysis['p_count']}")

    conclusions = {
        "html": "这是【完整的 HTML 文档】结构",
        "enml": "这是【印象笔记 ENML 格式】",
        "fragment": "这是【简单文本/片段】",
    }
    print(f"\n🔍 结论: {conclusions[analysis['kind']]}")


def download_note_enml(note_store, token, guid, output_path):
    """下载一篇笔记并把原始 ENML 写入指定路径。"""
    note = note_store.getNote(token, guid, True, True, False, False)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(note.content or "", encoding="utf-8")
    return note


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        description="下载指定印象笔记的原始 ENML 并分析结构"
    )
    parser.add_argument("--guid", required=True, help="要下载的笔记 GUID")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("note_enml_output.xml"),
        help="输出 XML 文件路径（默认当前目录下 note_enml_output.xml）",
    )
    args = parser.parse_args()

    token, note_store_url = load_config()
    if not token or not note_store_url:
        parser.error("未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")

    note_store = create_note_store(note_store_url, token)
    print(f"📥 获取笔记: {args.guid}")
    try:
        note = download_note_enml(
            note_store,
            token,
            args.guid,
            args.output,
        )
    except Exception as exc:
        print(f"❌ 获取笔记失败: {exc}")
        return 1

    print(f"标题: {note.title}")
    print(f"内容长度: {len(note.content or '')} 字符")
    print(f"✅ 已保存到: {args.output.resolve()}")
    print_analysis(analyze_enml(note.content))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
