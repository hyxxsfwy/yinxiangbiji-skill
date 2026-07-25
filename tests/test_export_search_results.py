import unittest
from datetime import date
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from evernote.edam.type.ttypes import NoteSortOrder


class SearchQueryTests(unittest.TestCase):
    def test_builds_one_date_scoped_query_per_keyword(self):
        try:
            from scripts.export_search_results import build_keyword_queries
        except ModuleNotFoundError:
            self.fail("尚未实现按日期和多关键词构建查询")

        queries = build_keyword_queries(
            ["AI", "Agent", "人工智能"],
            since=date(2025, 7, 26),
        )

        self.assertEqual(
            queries,
            [
                "created:20250726 AI",
                "created:20250726 Agent",
                "created:20250726 人工智能",
            ],
        )

    def test_deduplicates_and_prioritizes_recent_title_matches(self):
        try:
            from scripts.export_search_results import select_top_notes
        except ImportError:
            self.fail("尚未实现搜索结果去重与排序")

        image_only = SimpleNamespace(
            guid="image",
            title="图片",
            created=400,
            updated=400,
        )
        agent_note = SimpleNamespace(
            guid="agent",
            title="Agent 技术总结",
            created=200,
            updated=200,
        )
        ai_note_old = SimpleNamespace(
            guid="ai",
            title="AI 编程指南",
            created=250,
            updated=250,
        )
        ai_note_new = SimpleNamespace(
            guid="ai",
            title="AI 编程指南",
            created=250,
            updated=300,
        )
        chinese_note = SimpleNamespace(
            guid="cn",
            title="人工智能评测",
            created=100,
            updated=100,
        )

        selected = select_top_notes(
            [
                [image_only, ai_note_old, agent_note],
                [ai_note_new, chinese_note],
            ],
            keywords=["AI", "Agent", "人工智能"],
            limit=3,
        )

        self.assertEqual([note.guid for note in selected], ["ai", "agent", "cn"])
        self.assertEqual(selected[0].updated, 300)

    def test_searches_each_keyword_with_updated_descending_order(self):
        try:
            from scripts.export_search_results import search_metadata_batches
        except ImportError:
            self.fail("尚未实现多关键词元数据搜索")

        class FakeNoteStore:
            def __init__(self):
                self.calls = []

            def findNotesMetadata(
                self,
                token,
                note_filter,
                offset,
                max_results,
                result_spec,
            ):
                self.calls.append(
                    {
                        "token": token,
                        "words": note_filter.words,
                        "order": note_filter.order,
                        "ascending": note_filter.ascending,
                        "offset": offset,
                        "max_results": max_results,
                    }
                )
                return SimpleNamespace(
                    notes=[SimpleNamespace(guid=note_filter.words)],
                    totalNotes=1,
                )

        note_store = FakeNoteStore()
        batches, totals = search_metadata_batches(
            note_store,
            token="test-token",
            keywords=["AI", "Agent"],
            since=date(2025, 7, 26),
            max_per_keyword=25,
        )

        self.assertEqual(
            [call["words"] for call in note_store.calls],
            ["created:20250726 AI", "created:20250726 Agent"],
        )
        self.assertTrue(
            all(
                call["order"] == NoteSortOrder.UPDATED
                and call["ascending"] is False
                and call["offset"] == 0
                and call["max_results"] == 25
                for call in note_store.calls
            )
        )
        self.assertEqual([len(batch) for batch in batches], [1, 1])
        self.assertEqual(totals, [1, 1])


class ExportNoteTests(unittest.TestCase):
    def test_exports_plain_text_note_with_source_metadata(self):
        try:
            from scripts.export_search_results import export_note_to_obsidian
        except ImportError:
            self.fail("尚未实现单篇笔记导出")

        note = SimpleNamespace(
            guid="note-guid",
            title="AI 笔记",
            created=1753488000000,
            updated=1753574400000,
            content="<en-note>AI 内容</en-note>",
            resources=[],
        )

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            exported_path = export_note_to_obsidian(
                note,
                notebook_name="2026",
                target_dir=Path(temp_dir),
            )
            exported_content = exported_path.read_text(encoding="utf-8")

        self.assertEqual(exported_path.name, "AI 笔记.md")
        self.assertIn("source_guid: note-guid", exported_content)
        self.assertIn("notebook: 2026", exported_content)
        self.assertIn("# AI 笔记", exported_content)
        self.assertIn("AI 内容", exported_content)

    def test_exports_inline_image_resource_and_markdown_reference(self):
        from scripts.export_search_results import export_note_to_obsidian

        image_data = b"test-image"
        image_hash = hashlib.md5(image_data).hexdigest()
        resource = SimpleNamespace(
            data=SimpleNamespace(body=image_data),
            mime="image/png",
            attributes=SimpleNamespace(fileName=None),
        )
        note = SimpleNamespace(
            guid="image-note-guid",
            title="Agent 图片笔记",
            created=1753488000000,
            updated=1753574400000,
            content=(
                "<en-note><div>Agent 图片</div>"
                f'<en-media type="image/png" hash="{image_hash}"/>'
                "</en-note>"
            ),
            resources=[resource],
        )

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            target_dir = Path(temp_dir)
            exported_path = export_note_to_obsidian(
                note,
                notebook_name="微信",
                target_dir=target_dir,
            )
            exported_content = exported_path.read_text(encoding="utf-8")
            image_path = target_dir / "_attachments" / f"{image_hash}.png"

            self.assertTrue(image_path.exists())
            self.assertEqual(image_path.read_bytes(), image_data)

        self.assertIn(
            f"![{image_hash}.png](_attachments/{image_hash}.png)",
            exported_content,
        )


class CommandLineTests(unittest.TestCase):
    def test_help_is_emitted_as_utf8_on_windows(self):
        script_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "export_search_results.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        self.assertIn(
            "搜索最近一段时间内的相关笔记并导出到 Obsidian",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
