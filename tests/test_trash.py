import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class DeletedNoteSearchTests(unittest.TestCase):
    def test_deleted_search_sets_inactive_filter_and_honors_limit(self):
        try:
            from scripts.list_trash import find_deleted_notes
        except ImportError:
            self.fail("尚未实现共享的废纸篓查询函数")

        notes = [
            SimpleNamespace(
                guid=f"guid-{index}",
                title=f"笔记 {index}",
                deleted=1000 + index,
            )
            for index in range(5)
        ]

        class FakeNoteStore:
            def __init__(self):
                self.filters = []
                self.limits = []

            def findNotesMetadata(
                self,
                token,
                note_filter,
                offset,
                max_results,
                result_spec,
            ):
                self.filters.append(note_filter)
                self.limits.append(max_results)
                page = notes[offset:offset + max_results]
                return SimpleNamespace(notes=page, totalNotes=len(notes))

        note_store = FakeNoteStore()
        deleted = find_deleted_notes(
            note_store,
            token="test-token",
            max_count=3,
        )

        self.assertEqual(
            [note.guid for note in deleted],
            [note.guid for note in notes[:3]],
        )
        self.assertTrue(note_store.filters[0].inactive)
        self.assertEqual(note_store.limits, [3])

    def test_no_limit_returns_all_deleted_pages(self):
        from scripts.list_trash import find_deleted_notes

        notes = [
            SimpleNamespace(
                guid=f"guid-{index}",
                title=f"笔记 {index}",
                deleted=1000 + index,
            )
            for index in range(105)
        ]

        class FakeNoteStore:
            def findNotesMetadata(
                self,
                token,
                note_filter,
                offset,
                max_results,
                result_spec,
            ):
                return SimpleNamespace(
                    notes=notes[offset:offset + max_results],
                    totalNotes=len(notes),
                )

        deleted = find_deleted_notes(
            FakeNoteStore(),
            token="test-token",
            max_count=None,
        )

        self.assertEqual(len(deleted), 105)


class EmptyTrashSafetyTests(unittest.TestCase):
    def test_wrong_confirmation_stops_before_loading_credentials(self):
        from scripts.empty_trash import empty_trash

        with patch(
            "scripts.empty_trash.load_config",
            side_effect=AssertionError("不应读取配置"),
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(empty_trash(confirm_text="yes"))

    def test_help_documents_exact_confirmation_text(self):
        script_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "empty_trash.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )

        self.assertIn("--confirm DELETE_ALL", result.stdout)
        self.assertIn("永久删除", result.stdout)


if __name__ == "__main__":
    unittest.main()
