import json
import os
import stat
import unittest
from unittest.mock import patch

from tests.support import workspace_temp_dir


def seed_vault(vault):
    for layer in ("20_知识笔记", "30_精选资料"):
        (vault / layer / "软件工程").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / "20_知识笔记" / "软件工程" / "工程实践.md").write_text(
        "---\ntype: 知识\ndomain: 软件工程\nstatus: 常青\n---\n\n# 工程实践\n",
        encoding="utf-8",
    )
    month = vault / "30_精选资料" / "软件工程" / "2026年08月"
    month.mkdir()
    (month / "容器实践.md").write_text(
        "---\ntype: 资料\ndomain: 软件工程\nuid: container-practice\n"
        "created: '2026-08-01'\n---\n\n# 容器实践\n",
        encoding="utf-8",
    )
    (vault / "00_首页.md").write_text(
        "[[30_精选资料/软件工程/目录索引|软件工程]]\n",
        encoding="utf-8",
    )
    (vault / "保留.md").write_text(
        "---\ntype: 资料\ndomain: AI\n---\n\n软件工程是一种方法，不是路径。\n",
        encoding="utf-8",
    )


class DomainTaxonomyMigrationTests(unittest.TestCase):
    def test_empty_readonly_tree_can_be_removed_for_onedrive_directories(self):
        from scripts.migrate_domain_taxonomy import _remove_empty_tree

        with workspace_temp_dir() as root:
            legacy = root / "软件工程" / "2026年08月"
            legacy.mkdir(parents=True)
            os.chmod(legacy, stat.S_IREAD)
            os.chmod(legacy.parent, stat.S_IREAD)
            _remove_empty_tree(legacy.parent, strict=True)
            self.assertFalse(legacy.parent.exists())

    def test_preview_is_read_only_and_lists_rename_and_missing_domains(self):
        from scripts.migrate_domain_taxonomy import build_plan

        with workspace_temp_dir() as root:
            vault = root / "vault"
            seed_vault(vault)
            before = sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*"))
            plan = build_plan(vault)
            after = sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*"))

            self.assertEqual(before, after)
            self.assertTrue(plan.ok, plan.issues)
            self.assertEqual(len(plan.moves), 2)
            self.assertIn("科技产业", plan.missing_domains["20_知识笔记"])

    def test_conflicting_destination_blocks_before_any_write(self):
        from scripts.migrate_domain_taxonomy import build_plan

        with workspace_temp_dir() as root:
            vault = root / "vault"
            seed_vault(vault)
            target = vault / "20_知识笔记" / "信息技术"
            target.mkdir()
            (target / "工程实践.md").write_text("不同内容\n", encoding="utf-8")

            plan = build_plan(vault)
            self.assertFalse(plan.ok)
            self.assertTrue(any("冲突" in issue for issue in plan.issues))

    def test_apply_renames_only_legacy_domain_and_verify_is_idempotent(self):
        from scripts.domain_taxonomy import MANAGED_DOMAINS
        from scripts.migrate_domain_taxonomy import apply_plan, build_plan, verify_vault

        with workspace_temp_dir() as root:
            vault = root / "vault"
            seed_vault(vault)
            unchanged = (vault / "保留.md").read_bytes()

            result = apply_plan(build_plan(vault), confirm="EXPAND_MANAGED_DOMAINS")
            self.assertTrue(result["ok"], result)
            self.assertEqual((vault / "保留.md").read_bytes(), unchanged)
            self.assertFalse((vault / "20_知识笔记" / "软件工程").exists())
            migrated = vault / "30_精选资料" / "信息技术" / "2026年08月" / "容器实践.md"
            self.assertIn("domain: 信息技术", migrated.read_text(encoding="utf-8"))
            home = (vault / "00_首页.md").read_text(encoding="utf-8")
            self.assertNotIn("30_精选资料/软件工程", home)
            self.assertTrue(all((vault / "30_精选资料" / d / "目录索引.md").is_file() for d in MANAGED_DOMAINS))
            self.assertTrue(verify_vault(vault)["ok"])
            self.assertEqual(build_plan(vault).change_count, 0)

    def test_apply_requires_exact_confirmation(self):
        from scripts.migrate_domain_taxonomy import apply_plan, build_plan

        with workspace_temp_dir() as root:
            vault = root / "vault"
            seed_vault(vault)
            with self.assertRaisesRegex(ValueError, "EXPAND_MANAGED_DOMAINS"):
                apply_plan(build_plan(vault), confirm="yes")

    def test_failure_restores_files_from_incremental_transaction(self):
        from scripts.migrate_domain_taxonomy import apply_plan, build_plan

        with workspace_temp_dir() as root:
            vault = root / "vault"
            seed_vault(vault)
            original = (vault / "20_知识笔记" / "软件工程" / "工程实践.md").read_bytes()
            with patch(
                "scripts.migrate_domain_taxonomy.write_knowledge_base_index",
                side_effect=RuntimeError("模拟索引失败"),
            ):
                with self.assertRaisesRegex(RuntimeError, "模拟索引失败"):
                    apply_plan(build_plan(vault), confirm="EXPAND_MANAGED_DOMAINS")

            restored = vault / "20_知识笔记" / "软件工程" / "工程实践.md"
            self.assertEqual(restored.read_bytes(), original)
            self.assertFalse((vault / "20_知识笔记" / "信息技术" / "工程实践.md").exists())
            self.assertFalse((vault / "30_精选资料" / "信息技术").exists())


class CommandLineTests(unittest.TestCase):
    def test_preview_prints_json(self):
        from scripts.migrate_domain_taxonomy import main

        with workspace_temp_dir() as root:
            vault = root / "vault"
            seed_vault(vault)
            with patch("builtins.print") as mocked:
                self.assertEqual(main(["preview", "--vault", str(vault)]), 0)
            json.loads(mocked.call_args.args[0])
