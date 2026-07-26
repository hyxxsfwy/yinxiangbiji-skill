import unittest
from datetime import datetime
from pathlib import Path

from tests.support import workspace_temp_dir


def write_note(path, title, created, updated, guid, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'created: "{created}"\n'
            f'updated: "{updated}"\n'
            f'source_guid: "{guid}"\n'
            "---\n\n"
            f"# {title}\n\n"
            f"{body}\n"
        ),
        encoding="utf-8",
    )
    return path


class MonthFolderTests(unittest.TestCase):
    def test_formats_created_time_as_chinese_month_folder(self):
        from scripts.knowledge_base import month_folder_name

        self.assertEqual(
            month_folder_name(datetime(2026, 7, 24, 11, 0)),
            "2026年07月",
        )


class SummaryTests(unittest.TestCase):
    def test_combines_first_effective_paragraph_with_outline(self):
        from scripts.knowledge_base import build_note_summary

        markdown = """---
created: "2026-07-24 11:00:27"
updated: "2026-07-26 09:00:00"
source_guid: "summary-guid"
---

# Agent 文章

原文链接: [来源](https://example.com)

原创测试作者 技术公众号

关注公众号获取更多内容

这篇文章解释 Agent 为什么会在长上下文中遗漏关键规则。第二句不进入首句摘要。

## 01 注意力机制

### 1.1 中间位置衰减

## 02 工程化解法
"""
        summary = build_note_summary(markdown, "Agent 文章")

        self.assertIn(
            "这篇文章解释 Agent 为什么会在长上下文中遗漏关键规则。",
            summary,
        )
        self.assertIn("“注意力机制”", summary)
        self.assertIn("“中间位置衰减”", summary)
        self.assertIn("“工程化解法”", summary)
        self.assertNotIn("原文链接", summary)
        self.assertNotIn("公众号", summary)
        self.assertLessEqual(summary.count("。"), 2)

    def test_uses_title_fallback_for_image_only_note(self):
        from scripts.knowledge_base import build_note_summary

        markdown = """---
created: "2026-07-24 11:00:27"
updated: "2026-07-26 09:00:00"
source_guid: "image-guid"
---

# 一张图看懂 AI Agent 全流程

![流程图](../_attachments/flow.png)
"""

        summary = build_note_summary(
            markdown,
            "一张图看懂 AI Agent 全流程",
        )

        self.assertEqual(
            summary,
            "该笔记主要以图片形式呈现“一张图看懂 AI Agent 全流程”相关内容。",
        )


class IndexTests(unittest.TestCase):
    def test_writes_months_and_notes_in_descending_order(self):
        from scripts.knowledge_base import write_knowledge_base_index

        with workspace_temp_dir() as root:
            write_note(
                root / "2026年06月" / "六月文章.md",
                title="六月文章",
                created="2026-06-30 09:00:00",
                updated="2026-07-01 09:00:00",
                guid="june",
                body="六月文章介绍 Agent 的基础概念和实际应用方式。",
            )
            write_note(
                root / "2026年07月" / "七月文章.md",
                title="七月文章",
                created="2026-07-24 11:00:27",
                updated="2026-07-26 09:00:00",
                guid="july",
                body=(
                    "七月文章分析长上下文中的注意力分配问题。"
                    "\n\n## 章节主题"
                ),
            )

            index_path = write_knowledge_base_index(root)
            index = index_path.read_text(encoding="utf-8")

        self.assertLess(
            index.index("## 2026年07月"),
            index.index("## 2026年06月"),
        )
        self.assertIn("位置：`2026年07月/七月文章.md`", index)
        self.assertIn(
            "[七月文章](2026%E5%B9%B407%E6%9C%88/"
            "%E4%B8%83%E6%9C%88%E6%96%87%E7%AB%A0.md)",
            index,
        )
        self.assertIn(
            "简介：七月文章分析长上下文中的注意力分配问题。",
            index,
        )
        self.assertNotIn("目录索引.md`", index)
