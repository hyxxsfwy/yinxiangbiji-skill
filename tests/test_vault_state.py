import hashlib
import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from tests.support import workspace_temp_dir

from scripts.vault_state import (
    StateMigrationConflict,
    VaultStatePaths,
    migrate_legacy_state,
)


class VaultStatePathTests(unittest.TestCase):
    def test_for_vault_derives_all_paths_under_vault_state_directory(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()

            paths = VaultStatePaths.for_vault(vault)

        self.assertEqual(
            paths.catalog,
            vault / ".state" / "yinxiang-notes" / "export-catalog.sqlite3",
        )
        self.assertEqual(paths.jobs.name, "jobs")
        self.assertEqual(paths.runs.name, "runs")
        self.assertEqual(paths.reports.name, "reports")
        self.assertEqual(paths.single_domain.name, "single-domain")
        self.assertEqual(paths.migrations.name, "migrations")
        self.assertEqual(paths.lock.name, "active-run.lock")


class LegacyMigrationTests(unittest.TestCase):
    def _prepare_legacy_files(self, legacy_root):
        contents = {
            Path("export-AI-abc.json"): b'{"domain":"AI"}\n',
            Path("multi-export-task.json"): b'{"task":"multi"}\n',
            Path("jobs/task.json"): b'{"task":"job"}\n',
            Path("reports/task.json"): b'{"task":"report"}\n',
        }
        for relative_path, content in contents.items():
            source = legacy_root / relative_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
        return contents

    def test_first_migration_copies_allowed_files_and_records_sha256(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            contents = self._prepare_legacy_files(legacy_root)
            paths = VaultStatePaths.for_vault(vault)

            report = migrate_legacy_state(paths, legacy_root)

            expected_targets = {
                Path("single-domain/export-AI-abc.json"):
                contents[Path("export-AI-abc.json")],
                Path("multi-export-task.json"):
                contents[Path("multi-export-task.json")],
                Path("jobs/task.json"): contents[Path("jobs/task.json")],
                Path("reports/task.json"):
                contents[Path("reports/task.json")],
            }
            self.assertEqual(len(report.copied), 4)
            self.assertEqual(report.skipped, ())
            for relative_path, expected_content in expected_targets.items():
                self.assertEqual(
                    (paths.root / relative_path).read_bytes(),
                    expected_content,
                )

            self.assertIsNotNone(report.manifest)
            manifest = json.loads(report.manifest.read_text(encoding="utf-8"))
            entries = {
                entry["source"]: entry for entry in manifest["copied"]
            }
            self.assertEqual(
                set(entries),
                {
                    "export-AI-abc.json",
                    "multi-export-task.json",
                    "jobs/task.json",
                    "reports/task.json",
                },
            )
            for source, expected_content in contents.items():
                entry = entries[source.as_posix()]
                self.assertEqual(entry["size"], len(expected_content))
                self.assertEqual(
                    entry["sha256"],
                    hashlib.sha256(expected_content).hexdigest(),
                )

    def test_second_migration_skips_identical_destinations(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            self._prepare_legacy_files(legacy_root)
            paths = VaultStatePaths.for_vault(vault)
            first = migrate_legacy_state(paths, legacy_root)

            second = migrate_legacy_state(paths, legacy_root)

            self.assertEqual(len(first.copied), 4)
            self.assertEqual(second.copied, ())
            self.assertEqual(len(second.skipped), 4)
            self.assertIsNone(second.manifest)
            self.assertEqual(
                len(list(paths.migrations.glob("migration-*.json"))),
                1,
            )

    def test_conflicting_destination_is_not_overwritten_or_partially_migrated(
        self,
    ):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            self._prepare_legacy_files(legacy_root)
            paths = VaultStatePaths.for_vault(vault)
            paths.reports.mkdir(parents=True)
            conflict = paths.reports / "task.json"
            conflict.write_bytes(b"keep-existing")

            with self.assertRaises(StateMigrationConflict):
                migrate_legacy_state(paths, legacy_root)

            self.assertEqual(conflict.read_bytes(), b"keep-existing")
            self.assertFalse(
                (paths.single_domain / "export-AI-abc.json").exists()
            )
            self.assertFalse((paths.jobs / "task.json").exists())
            self.assertFalse((paths.root / "multi-export-task.json").exists())

    def test_publish_race_never_overwrites_concurrent_target(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            source = legacy_root / "export-AI-race.json"
            source.write_bytes(b"legacy")
            paths = VaultStatePaths.for_vault(vault)
            target = paths.single_domain / source.name
            concurrent = b"concurrent"
            real_replace = os.replace
            real_link = os.link

            def race(real_publish, source_path, target_path):
                if Path(target_path) == target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(concurrent)
                return real_publish(source_path, target_path)

            with (
                patch(
                    "scripts.vault_state.os.replace",
                    side_effect=lambda source_path, target_path: race(
                        real_replace,
                        source_path,
                        target_path,
                    ),
                ),
                patch(
                    "scripts.vault_state.os.link",
                    side_effect=lambda source_path, target_path: race(
                        real_link,
                        source_path,
                        target_path,
                    ),
                ),
                self.assertRaises(StateMigrationConflict),
            ):
                migrate_legacy_state(paths, legacy_root)

            self.assertEqual(target.read_bytes(), concurrent)

    def test_publish_conflict_rolls_back_only_batch_owned_targets(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            export_source = legacy_root / "export-AI-first.json"
            job_source = legacy_root / "jobs" / "task.json"
            job_source.parent.mkdir()
            export_source.write_bytes(b"first-source")
            job_source.write_bytes(b"second-source")
            paths = VaultStatePaths.for_vault(vault)
            first_target = paths.single_domain / export_source.name
            second_target = paths.jobs / job_source.name
            replacement = b"replacement-after-first-publish"
            concurrent = b"concurrent-second-target"
            real_replace = os.replace
            real_link = os.link

            def publish_with_race(real_publish, source_path, target_path):
                destination = Path(target_path)
                if destination == second_target:
                    first_target.unlink()
                    first_target.write_bytes(replacement)
                    second_target.parent.mkdir(parents=True, exist_ok=True)
                    second_target.write_bytes(concurrent)
                return real_publish(source_path, target_path)

            with (
                patch(
                    "scripts.vault_state.os.replace",
                    side_effect=lambda source_path, target_path:
                    publish_with_race(
                        real_replace,
                        source_path,
                        target_path,
                    ),
                ),
                patch(
                    "scripts.vault_state.os.link",
                    side_effect=lambda source_path, target_path:
                    publish_with_race(
                        real_link,
                        source_path,
                        target_path,
                    ),
                ),
                self.assertRaises(StateMigrationConflict),
            ):
                migrate_legacy_state(paths, legacy_root)

            self.assertEqual(first_target.read_bytes(), replacement)
            self.assertEqual(second_target.read_bytes(), concurrent)

    def test_manifest_hash_and_size_describe_staged_bytes(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            source = legacy_root / "export-AI-changing.json"
            source.write_bytes(b"before-copy")
            changed = b"changed-while-copying"
            paths = VaultStatePaths.for_vault(vault)
            import shutil
            real_copyfile = shutil.copyfile

            def mutate_then_copy(source_path, target_path):
                Path(source_path).write_bytes(changed)
                return real_copyfile(source_path, target_path)

            with patch(
                "scripts.vault_state.shutil.copyfile",
                side_effect=mutate_then_copy,
            ):
                report = migrate_legacy_state(paths, legacy_root)

            target = paths.single_domain / source.name
            manifest = json.loads(
                report.manifest.read_text(encoding="utf-8")
            )
            entry = manifest["copied"][0]
            self.assertEqual(target.read_bytes(), changed)
            self.assertEqual(entry["size"], len(changed))
            self.assertEqual(
                entry["sha256"],
                hashlib.sha256(changed).hexdigest(),
            )


class RuntimeLockTests(unittest.TestCase):
    def test_lock_is_exclusive_contains_owner_metadata_and_exits_cleanly(self):
        from scripts.vault_state import (
            StateLockConflict,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")

            with runtime_write_lock(paths, "task-123"):
                payload = json.loads(paths.lock.read_text(encoding="utf-8"))
                self.assertEqual(payload["device"], socket.gethostname())
                self.assertEqual(payload["pid"], os.getpid())
                self.assertEqual(payload["task_id"], "task-123")
                self.assertRegex(
                    payload["created_at"],
                    r"^\d{4}-\d{2}-\d{2}T",
                )
                original_lock = paths.lock.read_bytes()

                with self.assertRaises(StateLockConflict):
                    with runtime_write_lock(paths, "task-duplicate"):
                        self.fail("同一运行进程不得重复获得写锁")

                self.assertEqual(paths.lock.read_bytes(), original_lock)

            self.assertFalse(paths.lock.exists())

    def test_exception_inside_context_releases_owned_lock(self):
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")

            with self.assertRaisesRegex(RuntimeError, "业务失败"):
                with runtime_write_lock(paths, "task-failing"):
                    self.assertTrue(paths.lock.exists())
                    raise RuntimeError("业务失败")

            self.assertFalse(paths.lock.exists())

    def test_live_local_lock_cannot_be_recovered(self):
        from scripts.vault_state import (
            StateLockConflict,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")

            with runtime_write_lock(paths, "task-live"):
                original_lock = paths.lock.read_bytes()
                with self.assertRaises(StateLockConflict):
                    with runtime_write_lock(
                        paths,
                        "task-intruder",
                        recover_stale=True,
                    ):
                        self.fail("仍存活的本机锁不得被恢复模式覆盖")
                self.assertEqual(paths.lock.read_bytes(), original_lock)

    def test_foreign_lock_requires_recovery_and_is_archived_before_rebuild(
        self,
    ):
        from scripts.vault_state import (
            StateLockConflict,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            paths.root.mkdir(parents=True)
            old_payload = {
                "device": "另一台设备",
                "pid": 1234,
                "task_id": "old-task",
                "created_at": "2026-07-27T00:00:00+00:00",
                "lock_id": "old-lock",
            }
            old_bytes = (
                json.dumps(old_payload, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            paths.lock.write_bytes(old_bytes)

            with self.assertRaises(StateLockConflict):
                with runtime_write_lock(paths, "new-task"):
                    self.fail("默认模式不得清理其他设备的锁")
            self.assertEqual(paths.lock.read_bytes(), old_bytes)

            with runtime_write_lock(
                paths,
                "new-task",
                recover_stale=True,
            ):
                active = json.loads(paths.lock.read_text(encoding="utf-8"))
                self.assertEqual(active["task_id"], "new-task")
                audits = list(
                    paths.migrations.glob("stale-lock-*.json")
                )
                self.assertEqual(len(audits), 1)
                self.assertEqual(audits[0].read_bytes(), old_bytes)

            self.assertFalse(paths.lock.exists())
            self.assertEqual(len(list(paths.migrations.iterdir())), 1)

    def test_context_exit_does_not_delete_replacement_lock(self):
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            replacement = {
                "device": "另一台设备",
                "pid": 5678,
                "task_id": "replacement",
                "created_at": "2026-07-28T00:00:00+00:00",
                "lock_id": "replacement-lock",
            }

            with runtime_write_lock(paths, "original"):
                paths.lock.write_text(
                    json.dumps(replacement, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            self.assertEqual(
                json.loads(paths.lock.read_text(encoding="utf-8")),
                replacement,
            )

    def test_recovery_guard_prevents_replacement_between_check_and_archive(
        self,
    ):
        from scripts import vault_state
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            paths.root.mkdir(parents=True)
            paths.lock.write_text(
                json.dumps(
                    {
                        "device": "另一台设备",
                        "pid": 1234,
                        "task_id": "old-task",
                        "created_at": "2026-07-27T00:00:00+00:00",
                        "lock_id": "old-lock",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            raced = []
            real_archive = vault_state._archive_stale_lock

            def race_before_archive(received_paths):
                if not guard.exists():
                    raced.append(True)
                    received_paths.lock.write_text(
                        json.dumps(
                            {
                                "device": socket.gethostname(),
                                "pid": os.getpid(),
                                "task_id": "concurrent-task",
                                "created_at":
                                "2026-07-28T00:00:00+00:00",
                                "lock_id": "concurrent-lock",
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                return real_archive(received_paths)

            with patch(
                "scripts.vault_state._archive_stale_lock",
                side_effect=race_before_archive,
            ):
                with runtime_write_lock(
                    paths,
                    "new-task",
                    recover_stale=True,
                ):
                    self.assertEqual(
                        json.loads(
                            paths.lock.read_text(encoding="utf-8")
                        )["task_id"],
                        "new-task",
                    )

            self.assertEqual(raced, [])

    def test_release_guard_prevents_replacement_between_check_and_delete(self):
        from scripts import vault_state
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            raced = []
            real_read = vault_state._read_lock_payload

            def race_after_read(lock):
                payload = real_read(lock)
                if (
                    Path(lock) == paths.lock
                    and isinstance(payload, dict)
                    and payload.get("task_id") == "original"
                    and not guard.exists()
                ):
                    raced.append(True)
                    paths.lock.write_text(
                        json.dumps(
                            {
                                "device": "另一台设备",
                                "pid": 5678,
                                "task_id": "replacement",
                                "created_at":
                                "2026-07-28T00:00:00+00:00",
                                "lock_id": "replacement-lock",
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                return payload

            with patch(
                "scripts.vault_state._read_lock_payload",
                side_effect=race_after_read,
            ):
                with runtime_write_lock(paths, "original"):
                    pass

            self.assertEqual(raced, [])
            self.assertFalse(paths.lock.exists())

    def test_existing_operation_guard_is_never_silently_recovered(self):
        from scripts.vault_state import (
            StateLockConflict,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            paths.root.mkdir(parents=True)
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            guard_bytes = b'{"guard_id":"unknown-owner"}\n'
            guard.write_bytes(guard_bytes)

            with self.assertRaises(StateLockConflict):
                with runtime_write_lock(
                    paths,
                    "task",
                    recover_stale=True,
                ):
                    self.fail("残留操作 guard 不得被静默覆盖")

            self.assertEqual(guard.read_bytes(), guard_bytes)
            self.assertFalse(paths.lock.exists())


if __name__ == "__main__":
    unittest.main()
