import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import textwrap
import threading
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

    def test_rollback_has_no_identity_check_then_unlink_window_on_target(
        self,
    ):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            first_source = legacy_root / "export-AI-first.json"
            second_source = legacy_root / "jobs" / "task.json"
            second_source.parent.mkdir()
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            paths = VaultStatePaths.for_vault(vault)
            first_target = paths.single_domain / first_source.name
            second_target = paths.jobs / second_source.name
            concurrent = b"concurrent-after-identity-check"
            raced = []
            real_samefile = os.path.samefile
            real_link = os.link

            def conflict_on_second(source_path, target_path):
                if Path(target_path) == second_target:
                    second_target.parent.mkdir(parents=True, exist_ok=True)
                    second_target.write_bytes(b"second-conflict")
                return real_link(source_path, target_path)

            def replace_after_identity_check(first_path, second_path):
                result = real_samefile(first_path, second_path)
                if Path(second_path) == first_target and result:
                    raced.append(True)
                    first_target.unlink()
                    first_target.write_bytes(concurrent)
                return result

            with (
                patch(
                    "scripts.vault_state.os.link",
                    side_effect=conflict_on_second,
                ),
                patch(
                    "scripts.vault_state.os.path.samefile",
                    side_effect=replace_after_identity_check,
                ),
                self.assertRaises(StateMigrationConflict),
            ):
                migrate_legacy_state(paths, legacy_root)

            self.assertEqual(raced, [])
            self.assertFalse(first_target.exists())
            self.assertEqual(
                second_target.read_bytes(),
                b"second-conflict",
            )

    def test_rollback_preserves_quarantine_if_restore_target_is_reoccupied(
        self,
    ):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            legacy_root = temp_dir / "legacy"
            vault.mkdir()
            legacy_root.mkdir()
            first_source = legacy_root / "export-AI-first.json"
            second_source = legacy_root / "jobs" / "task.json"
            second_source.parent.mkdir()
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            paths = VaultStatePaths.for_vault(vault)
            first_target = paths.single_domain / first_source.name
            second_target = paths.jobs / second_source.name
            displaced = b"displaced-concurrent-file"
            reoccupied = b"newer-concurrent-file"
            real_link = os.link

            def race_during_publish_or_restore(source_path, target_path):
                source = Path(source_path)
                target = Path(target_path)
                if target == second_target:
                    first_target.unlink()
                    first_target.write_bytes(displaced)
                    second_target.parent.mkdir(parents=True, exist_ok=True)
                    second_target.write_bytes(b"second-conflict")
                elif (
                    target == first_target
                    and "rollback-quarantine-" in source.as_posix()
                ):
                    first_target.write_bytes(reoccupied)
                return real_link(source_path, target_path)

            with (
                patch(
                    "scripts.vault_state.os.link",
                    side_effect=race_during_publish_or_restore,
                ),
                self.assertRaises(StateMigrationConflict),
            ):
                migrate_legacy_state(paths, legacy_root)

            self.assertEqual(first_target.read_bytes(), reoccupied)
            quarantines = list(
                paths.migrations.glob(
                    "rollback-quarantine-*/*"
                )
            )
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), displaced)


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

    def test_legacy_operation_guard_file_does_not_block_os_mutex(self):
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            paths.root.mkdir(parents=True)
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            guard_bytes = b'{"guard_id":"unknown-owner"}\n'
            guard.write_bytes(guard_bytes)

            with runtime_write_lock(
                paths,
                "task",
                recover_stale=True,
            ):
                self.assertTrue(paths.lock.exists())

            self.assertEqual(guard.read_bytes(), guard_bytes)
            self.assertFalse(paths.lock.exists())

    def test_business_exception_is_not_masked_by_concurrent_guard(self):
        from scripts.vault_state import (
            StateLockConflict,
            _lock_operation_guard,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            contender_ready = threading.Event()
            release_contender = threading.Event()
            contender_errors = []

            def contend_for_guard():
                try:
                    with _lock_operation_guard(paths, "contender"):
                        contender_ready.set()
                        release_contender.wait(timeout=2)
                except StateLockConflict as exc:
                    contender_errors.append(exc)
                    contender_ready.set()

            contender = threading.Thread(target=contend_for_guard)
            try:
                with self.assertRaisesRegex(RuntimeError, "业务失败"):
                    with runtime_write_lock(paths, "failing-task"):
                        contender.start()
                        self.assertTrue(contender_ready.wait(timeout=2))
                        raise RuntimeError("业务失败")
            finally:
                release_contender.set()
                contender.join(timeout=2)

            self.assertFalse(contender.is_alive())
            self.assertFalse(paths.lock.exists())
            self.assertEqual(len(contender_errors), 1)

    def test_recover_stale_archives_dead_local_lock_and_guard(self):
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            paths.root.mkdir(parents=True)
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            dead_pid = 424242
            lock_payload = {
                "device": socket.gethostname(),
                "pid": dead_pid,
                "task_id": "dead-task",
                "created_at": "2026-07-28T00:00:00+00:00",
                "lock_id": "dead-lock",
            }
            guard_payload = {
                "guard_id": "dead-guard",
                "device": socket.gethostname(),
                "pid": dead_pid,
                "operation": "runtime",
                "created_at": "2026-07-28T00:00:00+00:00",
            }
            lock_bytes = (
                json.dumps(lock_payload, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            guard_bytes = (
                json.dumps(guard_payload, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            paths.lock.write_bytes(lock_bytes)
            guard.write_bytes(guard_bytes)

            with patch(
                "scripts.vault_state.os.kill",
                side_effect=ProcessLookupError,
            ):
                with runtime_write_lock(
                    paths,
                    "recovered-task",
                    recover_stale=True,
                ):
                    active = json.loads(
                        paths.lock.read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        active["task_id"],
                        "recovered-task",
                    )

            self.assertFalse(paths.lock.exists())
            self.assertTrue(guard.exists())
            self.assertEqual(guard.read_bytes(), guard_bytes)
            stale_locks = list(
                paths.migrations.glob("stale-lock-*.json")
            )
            stale_guards = list(
                paths.migrations.glob("stale-guard-*.json")
            )
            self.assertEqual(len(stale_locks), 1)
            self.assertEqual(len(stale_guards), 0)
            self.assertEqual(stale_locks[0].read_bytes(), lock_bytes)

    def test_recover_stale_never_overwrites_live_local_guard(self):
        from scripts.vault_state import (
            StateLockConflict,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            paths.root.mkdir(parents=True)
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            lock_bytes = (
                json.dumps(
                    {
                        "device": socket.gethostname(),
                        "pid": os.getpid(),
                        "task_id": "live-task",
                        "created_at": "2026-07-28T00:00:00+00:00",
                        "lock_id": "live-lock",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
            guard_bytes = (
                json.dumps(
                    {
                        "guard_id": "live-guard",
                        "device": socket.gethostname(),
                        "pid": os.getpid(),
                        "operation": "runtime",
                        "created_at": "2026-07-28T00:00:00+00:00",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
            paths.lock.write_bytes(lock_bytes)
            guard.write_bytes(guard_bytes)

            with self.assertRaises(StateLockConflict):
                with runtime_write_lock(
                    paths,
                    "intruder",
                    recover_stale=True,
                ):
                    self.fail("活跃本机 guard 不得被恢复")

            self.assertEqual(paths.lock.read_bytes(), lock_bytes)
            self.assertEqual(guard.read_bytes(), guard_bytes)
            self.assertFalse(paths.migrations.exists())

    def test_legacy_recovery_gate_file_is_inert(self):
        from scripts.vault_state import _lock_operation_guard

        with workspace_temp_dir() as temp_dir:
            paths = VaultStatePaths.for_vault(temp_dir / "vault")
            guard = paths.lock.with_name(f"{paths.lock.name}.guard")
            recovery_gate = guard.with_name(f"{guard.name}.recovery")
            recovery_gate.parent.mkdir(parents=True)
            recovery_gate.write_text(
                '{"recovery_id":"legacy"}\n',
                encoding="utf-8",
            )

            with _lock_operation_guard(paths, "contender"):
                pass

            self.assertTrue(guard.exists())
            self.assertTrue(recovery_gate.exists())

    def test_operation_mutex_is_released_when_holder_process_crashes(self):
        from scripts.vault_state import _lock_operation_guard

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import os
                        from pathlib import Path
                        import sys
                        from scripts.vault_state import (
                            VaultStatePaths,
                            _lock_operation_guard,
                        )

                        paths = VaultStatePaths.for_vault(Path(sys.argv[1]))
                        with _lock_operation_guard(paths, "crashing-child"):
                            os._exit(73)
                        """
                    ),
                    str(vault),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(child.returncode, 73, child.stderr)

            with _lock_operation_guard(
                VaultStatePaths.for_vault(vault),
                "parent-after-crash",
            ):
                pass

    def test_crashed_recovery_gate_does_not_block_dead_lock_audit(self):
        from scripts.vault_state import runtime_write_lock

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            paths = VaultStatePaths.for_vault(vault)
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import json
                        import os
                        from pathlib import Path
                        import socket
                        import sys
                        from scripts.vault_state import VaultStatePaths

                        paths = VaultStatePaths.for_vault(Path(sys.argv[1]))
                        paths.root.mkdir(parents=True, exist_ok=True)
                        payload = {
                            "device": socket.gethostname(),
                            "pid": os.getpid(),
                            "task_id": "crashed-recovery",
                            "created_at": "2026-07-28T00:00:00+00:00",
                            "lock_id": "crashed-recovery-lock",
                        }
                        paths.lock.write_text(
                            json.dumps(payload, ensure_ascii=False) + "\\n",
                            encoding="utf-8",
                        )
                        gate = paths.lock.with_name(
                            f"{paths.lock.name}.guard.recovery"
                        )
                        gate.write_text(
                            json.dumps(
                                {
                                    "recovery_id": "crashed-gate",
                                    "device": socket.gethostname(),
                                    "pid": os.getpid(),
                                },
                                ensure_ascii=False,
                            )
                            + "\\n",
                            encoding="utf-8",
                        )
                        os._exit(74)
                        """
                    ),
                    str(vault),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(child.returncode, 74, child.stderr)
            stale_bytes = paths.lock.read_bytes()

            with patch(
                "scripts.vault_state.os.kill",
                side_effect=ProcessLookupError,
            ):
                with runtime_write_lock(
                    paths,
                    "parent-recovery",
                    recover_stale=True,
                ):
                    self.assertEqual(
                        json.loads(paths.lock.read_text(encoding="utf-8"))[
                            "task_id"
                        ],
                        "parent-recovery",
                    )

            audits = list(paths.migrations.glob("stale-lock-*.json"))
            self.assertEqual(len(audits), 1)
            self.assertEqual(audits[0].read_bytes(), stale_bytes)


if __name__ == "__main__":
    unittest.main()
