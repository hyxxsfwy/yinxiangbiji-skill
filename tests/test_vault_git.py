import subprocess
import unittest

from tests.support import workspace_temp_dir


def _git(vault, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(vault), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _configure_identity(vault):
    _git(vault, "config", "user.name", "测试用户")
    _git(vault, "config", "user.email", "test@example.invalid")


class VaultGitTests(unittest.TestCase):
    def test_initialize_batches_a_large_markdown_baseline(self):
        from scripts.vault_git import initialize_vault_git

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            notes = vault / "30_精选资料" / "AI" / "2026年07月"
            notes.mkdir(parents=True)
            _git(vault, "init", "-b", "main")
            _configure_identity(vault)
            for index in range(1500):
                (notes / f"{index:04d}-这是一篇用于验证批量暂存边界的文章.md").write_text(
                    "正文",
                    encoding="utf-8",
                )

            result = initialize_vault_git(vault)

            self.assertEqual(result.tracked_paths, 1502)

    def test_initialize_tracks_only_markdown_and_stable_configuration(self):
        from scripts.vault_git import initialize_vault_git, verify_tracked_paths

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            _git(vault, "init", "-b", "main")
            _configure_identity(vault)
            (vault / "文章.md").write_text("正文", encoding="utf-8")
            (vault / ".obsidian" / "app.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (vault / ".obsidian" / "workspace.json").write_text(
                "{}",
                encoding="utf-8",
            )
            attachments = vault / "30_精选资料" / "AI" / "_attachments"
            attachments.mkdir(parents=True)
            (attachments / "a.png").write_bytes(b"image")
            state = vault / ".state" / "yinxiang-notes"
            state.mkdir(parents=True)
            (state / "report.json").write_text("{}", encoding="utf-8")

            result = initialize_vault_git(vault)
            tracked = set(
                item
                for item in _git(vault, "ls-files").stdout.splitlines()
                if item
            )

            self.assertEqual(result.status, "initialized")
            self.assertIn("文章.md", tracked)
            self.assertIn(".obsidian/app.json", tracked)
            self.assertIn(".gitignore", tracked)
            self.assertIn(".gitattributes", tracked)
            self.assertNotIn(".obsidian/workspace.json", tracked)
            self.assertNotIn(
                "30_精选资料/AI/_attachments/a.png",
                tracked,
            )
            self.assertNotIn(".state/yinxiang-notes/report.json", tracked)
            self.assertEqual(verify_tracked_paths(vault), tuple())
            self.assertEqual(
                _git(vault, "status", "--porcelain").stdout,
                "",
            )

    def test_verifier_rejects_a_forced_binary_path(self):
        from scripts.vault_git import verify_tracked_paths, write_git_policy

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            _git(vault, "init", "-b", "main")
            _configure_identity(vault)
            write_git_policy(vault)
            binary = vault / "secret.bin"
            binary.write_bytes(b"secret")
            _git(vault, "add", "-f", "secret.bin")

            violations = verify_tracked_paths(vault)

            self.assertEqual(violations, ("secret.bin",))

    def test_preflight_rejects_dirty_tracked_markdown(self):
        from scripts.vault_git import (
            initialize_vault_git,
            preflight_vault_git,
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            _git(vault, "init", "-b", "main")
            _configure_identity(vault)
            note = vault / "文章.md"
            note.write_text("before", encoding="utf-8")
            initialize_vault_git(vault)
            note.write_text("after", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "不干净"):
                preflight_vault_git(vault)

    def test_commit_stages_only_changed_paths_from_transaction(self):
        from scripts.export_transaction import VaultMutationJournal
        from scripts.vault_git import (
            commit_transaction,
            initialize_vault_git,
            preflight_vault_git,
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            _git(vault, "init", "-b", "main")
            _configure_identity(vault)
            note = vault / "文章.md"
            note.write_text("before", encoding="utf-8")
            initialize_vault_git(vault)
            baseline = preflight_vault_git(vault)
            state_root = vault / ".state" / "yinxiang-notes"
            journal = VaultMutationJournal.begin(
                vault,
                state_root,
                "git-job",
                "selection",
                state_root / "catalog.sqlite3",
                baseline_git_head=baseline.head,
            )
            journal.prepare_write(note)
            note.write_text("after", encoding="utf-8")
            journal.record_write(note)
            ignored = vault / "30_精选资料" / "AI" / "_attachments" / "a.png"
            journal.prepare_write(ignored)
            ignored.parent.mkdir(parents=True)
            ignored.write_bytes(b"image")
            journal.record_write(ignored)
            journal.seal()

            result = commit_transaction(
                vault,
                journal,
                baseline,
                "同步测试导出",
            )

            self.assertEqual(result.status, "committed")
            self.assertEqual(
                _git(vault, "show", "--format=", "--name-only", "HEAD").stdout.strip(),
                "文章.md",
            )
            self.assertNotIn(
                "a.png",
                _git(vault, "ls-files").stdout,
            )

    def test_commit_rejects_tracked_change_outside_transaction(self):
        from scripts.export_transaction import VaultMutationJournal
        from scripts.vault_git import (
            commit_transaction,
            initialize_vault_git,
            preflight_vault_git,
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            _git(vault, "init", "-b", "main")
            _configure_identity(vault)
            first = vault / "first.md"
            second = vault / "second.md"
            first.write_text("before", encoding="utf-8")
            second.write_text("before", encoding="utf-8")
            initialize_vault_git(vault)
            baseline = preflight_vault_git(vault)
            state_root = vault / ".state" / "yinxiang-notes"
            journal = VaultMutationJournal.begin(
                vault,
                state_root,
                "outside-change-job",
                "selection",
                state_root / "catalog.sqlite3",
            )
            journal.prepare_write(first)
            first.write_text("after", encoding="utf-8")
            journal.record_write(first)
            second.write_text("user edit", encoding="utf-8")
            journal.seal()

            with self.assertRaisesRegex(RuntimeError, "事务外"):
                commit_transaction(
                    vault,
                    journal,
                    baseline,
                    "同步测试导出",
                )


if __name__ == "__main__":
    unittest.main()
