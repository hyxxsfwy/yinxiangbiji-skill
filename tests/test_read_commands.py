import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


class NotebookCommandTests(unittest.TestCase):
    def test_count_notebook_uses_offset_then_limit_then_spec(self):
        try:
            from scripts.list_notebooks import count_notebook_notes
        except ImportError:
            self.fail("尚未实现笔记本笔记数量查询帮助函数")

        class FakeNoteStore:
            def __init__(self):
                self.call = None

            def findNotesMetadata(self, *args):
                self.call = args
                return SimpleNamespace(totalNotes=7)

        note_store = FakeNoteStore()
        count = count_notebook_notes(
            note_store,
            token="test-token",
            notebook_guid="notebook-guid",
        )

        self.assertEqual(count, 7)
        self.assertEqual(note_store.call[2:4], (0, 1))
        self.assertTrue(note_store.call[4].includeTitle)


class EnmlCommandTests(unittest.TestCase):
    def test_analyze_enml_recognizes_native_enml(self):
        try:
            from scripts.get_note_enml import analyze_enml
        except ImportError:
            self.fail("尚未实现可复用的 ENML 分析函数")

        analysis = analyze_enml(
            '<!DOCTYPE en-note><en-note><div>正文</div><p>段落</p></en-note>'
        )

        self.assertTrue(analysis["has_doctype"])
        self.assertTrue(analysis["has_en_note"])
        self.assertFalse(analysis["has_html_tags"])
        self.assertEqual(analysis["div_count"], 1)
        self.assertEqual(analysis["p_count"], 1)
        self.assertEqual(analysis["kind"], "enml")

    def test_help_requires_guid_and_supports_output(self):
        script_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "get_note_enml.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )

        self.assertIn("--guid", result.stdout)
        self.assertIn("--output", result.stdout)


class SearchCommandTests(unittest.TestCase):
    def test_help_exposes_result_limit_without_connecting(self):
        script_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "search_notes.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )

        self.assertIn("--max-results", result.stdout)
        self.assertIn("印象笔记搜索语法", result.stdout)

    def test_metadata_search_paginates_past_server_page_size(self):
        from scripts.runtime import find_notes_metadata

        all_notes = [
            SimpleNamespace(guid=f"guid-{index}")
            for index in range(255)
        ]

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
                self.calls.append((offset, max_results))
                return SimpleNamespace(
                    notes=all_notes[offset:offset + max_results],
                    totalNotes=len(all_notes),
                )

        note_store = FakeNoteStore()
        notes, total = find_notes_metadata(
            note_store,
            token="test-token",
            note_filter=object(),
            max_results=255,
            result_spec=object(),
        )

        self.assertEqual(len(notes), 255)
        self.assertEqual(total, 255)
        self.assertEqual(note_store.calls, [(0, 250), (250, 5)])


if __name__ == "__main__":
    unittest.main()
