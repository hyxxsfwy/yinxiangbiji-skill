import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

from tests.support import workspace_temp_dir


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _create_catalog(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE notes (guid TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO notes VALUES ('before')")
        connection.commit()
    finally:
        connection.close()


class ExportTransactionTests(unittest.TestCase):
    def test_records_preimages_and_restores_write_delete_and_move(self):
        from scripts.export_transaction import VaultMutationJournal

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            state_root = vault / ".state" / "yinxiang-notes"
            existing = vault / "30_精选资料" / "AI" / "文章.md"
            deleted = vault / "30_精选资料" / "AI" / "删除.md"
            source = vault / "30_精选资料" / "AI" / "移动.md"
            destination = vault / "30_精选资料" / "AI" / "归档" / "移动.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("before", encoding="utf-8")
            deleted.write_text("delete-before", encoding="utf-8")
            source.write_text("move-before", encoding="utf-8")
            catalog = state_root / "catalog.sqlite3"
            _create_catalog(catalog)

            journal = VaultMutationJournal.begin(
                vault,
                state_root,
                "1111111111111111",
                "selection-hash",
                catalog,
            )
            journal.prepare_write(existing)
            existing.write_text("after", encoding="utf-8")
            journal.record_write(existing)
            journal.prepare_write(existing)
            journal.record_write(existing)

            journal.prepare_delete(deleted)
            deleted.unlink()
            journal.record_delete(deleted)

            journal.prepare_move(source, destination)
            destination.parent.mkdir(parents=True)
            source.replace(destination)
            journal.record_move(source, destination)

            summary = journal.seal()
            restored = journal.restore("ROLLBACK_KEYWORD_EXPORT")

            self.assertEqual(summary.changed_paths, 4)
            self.assertEqual(summary.object_count, 3)
            self.assertEqual(restored.state, "rolled_back")
            self.assertEqual(existing.read_text(encoding="utf-8"), "before")
            self.assertEqual(deleted.read_text(encoding="utf-8"), "delete-before")
            self.assertEqual(source.read_text(encoding="utf-8"), "move-before")
            self.assertFalse(destination.exists())
            connection = sqlite3.connect(catalog)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )
            finally:
                connection.close()

    def test_new_file_is_removed_on_restore_without_storing_an_object(self):
        from scripts.export_transaction import VaultMutationJournal

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            state_root = vault / ".state" / "yinxiang-notes"
            created = vault / "30_精选资料" / "AI" / "新增.md"
            catalog = state_root / "catalog.sqlite3"
            journal = VaultMutationJournal.begin(
                vault,
                state_root,
                "2222222222222222",
                "selection-hash",
                catalog,
            )
            journal.prepare_write(created)
            created.parent.mkdir(parents=True)
            created.write_text("new", encoding="utf-8")
            journal.record_write(created)
            summary = journal.seal()
            journal.restore("ROLLBACK_KEYWORD_EXPORT")

            self.assertEqual(summary.object_count, 0)
            self.assertFalse(created.exists())
            self.assertFalse(catalog.exists())

    def test_repeated_begin_preserves_original_preimage(self):
        from scripts.export_transaction import VaultMutationJournal

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            state_root = vault / ".state" / "yinxiang-notes"
            existing = vault / "文章.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("original", encoding="utf-8")
            catalog = state_root / "catalog.sqlite3"

            first = VaultMutationJournal.begin(
                vault,
                state_root,
                "3333333333333333",
                "selection-hash",
                catalog,
            )
            first.prepare_write(existing)
            existing.write_text("first-run", encoding="utf-8")
            first.record_write(existing)

            resumed = VaultMutationJournal.begin(
                vault,
                state_root,
                "3333333333333333",
                "selection-hash",
                catalog,
            )
            resumed.prepare_write(existing)
            existing.write_text("second-run", encoding="utf-8")
            resumed.record_write(existing)
            resumed.seal()
            resumed.restore("ROLLBACK_KEYWORD_EXPORT")

            self.assertEqual(existing.read_text(encoding="utf-8"), "original")

    def test_rejects_paths_outside_vault_and_wrong_confirmation(self):
        from scripts.export_transaction import VaultMutationJournal

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            state_root = vault / ".state" / "yinxiang-notes"
            catalog = state_root / "catalog.sqlite3"
            journal = VaultMutationJournal.begin(
                vault,
                state_root,
                "4444444444444444",
                "selection-hash",
                catalog,
            )
            with self.assertRaisesRegex(ValueError, "Vault"):
                journal.prepare_write(temp_dir / "outside.md")
            with self.assertRaisesRegex(ValueError, "确认词"):
                journal.restore("NO")

    def test_manifest_and_objects_are_content_addressed_and_atomic(self):
        from scripts.export_transaction import VaultMutationJournal

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            state_root = vault / ".state" / "yinxiang-notes"
            first_path = vault / "a.md"
            second_path = vault / "b.md"
            vault.mkdir()
            first_path.write_text("same", encoding="utf-8")
            second_path.write_text("same", encoding="utf-8")
            journal = VaultMutationJournal.begin(
                vault,
                state_root,
                "5555555555555555",
                "selection-hash",
                state_root / "catalog.sqlite3",
            )
            for path in (first_path, second_path):
                journal.prepare_delete(path)
                path.unlink()
                journal.record_delete(path)
            summary = journal.seal()
            manifest_path = (
                state_root
                / "transactions"
                / "5555555555555555"
                / "manifest.json"
            )
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            object_path = manifest_path.parent / "objects" / hashlib.sha256(
                b"same"
            ).hexdigest()

            self.assertEqual(summary.object_count, 1)
            self.assertTrue(object_path.is_file())
            self.assertEqual(_sha256(object_path), object_path.name)
            self.assertEqual(payload["state"], "in_progress")
            self.assertFalse(manifest_path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
