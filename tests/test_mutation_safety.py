import inspect
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace


class DeleteSafetyTests(unittest.TestCase):
    def test_programmatic_delete_requires_explicit_confirmation(self):
        from scripts.delete_note import delete_note

        confirmation = inspect.signature(delete_note).parameters["confirm"]
        self.assertFalse(confirmation.default)

    def test_preview_succeeds_without_calling_delete_api(self):
        from scripts.delete_note import delete_note

        class FakeNoteStore:
            def __init__(self):
                self.deleted = False

            def getNote(self, *args):
                return SimpleNamespace(title="待预览笔记")

            def deleteNote(self, token, guid):
                self.deleted = True
                raise AssertionError("预览不应删除")

        note_store = FakeNoteStore()
        with patch(
            "scripts.delete_note.load_config",
            return_value=("test-token", "https://example.invalid/notestore"),
        ), patch(
            "scripts.delete_note.create_note_store",
            return_value=note_store,
        ), contextlib.redirect_stdout(io.StringIO()):
            succeeded = delete_note("note-guid")

        self.assertTrue(succeeded)
        self.assertFalse(note_store.deleted)


class MutationCommandLineTests(unittest.TestCase):
    def test_help_is_non_mutating_and_successful(self):
        scripts_dir = (
            Path(__file__).resolve().parent.parent / "scripts"
        )
        for script_name in (
            "create_note.py",
            "update_note.py",
            "delete_note.py",
        ):
            with self.subTest(script=script_name):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(scripts_dir / script_name),
                        "--help",
                    ],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(result.returncode, 0)
                self.assertIn("options:", result.stdout)

    def test_update_requires_at_least_one_requested_change(self):
        try:
            from scripts.update_note import has_requested_updates
        except ImportError:
            self.fail("尚未实现空更新拦截")

        self.assertFalse(
            has_requested_updates(
                title=None,
                content=None,
                add_tags=None,
                remove_tags=None,
            )
        )
        self.assertTrue(
            has_requested_updates(
                title="新标题",
                content=None,
                add_tags=None,
                remove_tags=None,
            )
        )


class CreateSafetyTests(unittest.TestCase):
    def test_missing_requested_notebook_aborts_creation(self):
        from scripts.create_note import create_note

        class FakeNoteStore:
            def __init__(self):
                self.created = False

            def listNotebooks(self, token):
                return []

            def createNote(self, token, note):
                self.created = True
                raise AssertionError("不应创建到默认笔记本")

        note_store = FakeNoteStore()
        with patch(
            "scripts.create_note.load_config",
            return_value=("test-token", "https://example.invalid/notestore"),
        ), patch(
            "scripts.create_note.create_note_store",
            return_value=note_store,
        ), contextlib.redirect_stdout(io.StringIO()):
            result = create_note(
                "标题",
                "<en-note>内容</en-note>",
                notebook_name="不存在的笔记本",
            )

        self.assertIsNone(result)
        self.assertFalse(note_store.created)

    def test_missing_requested_tag_aborts_creation(self):
        from scripts.create_note import create_note

        class FakeNoteStore:
            def __init__(self):
                self.created = False

            def listTags(self, token):
                return []

            def createNote(self, token, note):
                self.created = True
                raise AssertionError("不应忽略用户指定的标签")

        note_store = FakeNoteStore()
        with patch(
            "scripts.create_note.load_config",
            return_value=("test-token", "https://example.invalid/notestore"),
        ), patch(
            "scripts.create_note.create_note_store",
            return_value=note_store,
        ), contextlib.redirect_stdout(io.StringIO()):
            result = create_note(
                "标题",
                "<en-note>内容</en-note>",
                tag_names=["不存在的标签"],
            )

        self.assertIsNone(result)
        self.assertFalse(note_store.created)


class UpdateSafetyTests(unittest.TestCase):
    def test_tag_only_update_aborts_when_no_tag_can_change(self):
        from scripts.update_note import update_note

        class FakeNoteStore:
            def __init__(self):
                self.updated = False

            def getNote(self, *args):
                return SimpleNamespace(
                    title="原标题",
                    content="<en-note>内容</en-note>",
                    tagGuids=[],
                )

            def listTags(self, token):
                return []

            def updateNote(self, token, note):
                self.updated = True
                raise AssertionError("不应提交空更新")

        note_store = FakeNoteStore()
        with patch(
            "scripts.update_note.load_config",
            return_value=("test-token", "https://example.invalid/notestore"),
        ), patch(
            "scripts.update_note.create_note_store",
            return_value=note_store,
        ), contextlib.redirect_stdout(io.StringIO()):
            result = update_note(
                "note-guid",
                add_tags=["不存在的标签"],
            )

        self.assertIsNone(result)
        self.assertFalse(note_store.updated)


if __name__ == "__main__":
    unittest.main()
