import json
import subprocess
import sys
import unittest
import zipfile

from tests.support import workspace_temp_dir


def seed_old_vault(vault):
    (vault / ".obsidian").mkdir(parents=True)
    ai = vault / "AI相关知识库"
    (ai / "2026年07月").mkdir(parents=True)
    (ai / "_attachments").mkdir()
    (ai / "目录索引.md").write_text("# 旧索引\n", encoding="utf-8")
    (ai / "2026年07月" / "一张图看懂 AI Agent 全流程.md").write_text(
        "---\ncreated: \"2026-07-21 08:00:00\"\n"
        "updated: \"2026-07-22 08:00:00\"\n"
        "source: \"Evernote\"\nsource_guid: \"agent-guid\"\n"
        "notebook: \"微信\"\ntype: \"webclip\"\n---\n\n"
        "# 一张图看懂 AI Agent 全流程\n\n"
        "![图](../_attachments/agent.png)\n",
        encoding="utf-8",
    )
    (ai / "_attachments" / "agent.png").write_bytes(b"image")

    quant = vault / "Quant相关知识库"
    quant.mkdir()
    (quant / "GPT-6也救不了平庸策略：Vibe Quant 的反思.md").write_text(
        "# [GPT-6也救不了平庸策略：Vibe Quant 的反思]"
        "(https://mp.weixin.qq.com/example)\n\n正文。\n",
        encoding="utf-8",
    )

    personal = vault / "HYXX个人知识库"
    personal.mkdir()
    (personal / ".obsidian").mkdir()
    (personal / "Codex CLI 使用技巧记录.md").write_text(
        "1. 进入翻页模式：CTRL + T\n",
        encoding="utf-8",
    )


class MigrationPlanTests(unittest.TestCase):
    def test_builds_exact_current_to_target_mapping(self):
        from scripts.restructure_obsidian_vault import build_migration_plan

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)

            mappings = {
                item.source.relative_to(vault).as_posix(): item.destination.relative_to(
                    vault
                ).as_posix()
                for item in plan.items
            }

        self.assertEqual(mappings["AI相关知识库"], "30_精选资料/AI")
        self.assertEqual(
            mappings["Quant相关知识库/GPT-6也救不了平庸策略：Vibe Quant 的反思.md"],
            "30_精选资料/Quant/2026年06月/GPT-6也救不了平庸策略：Vibe Quant 的反思.md",
        )
        self.assertEqual(
            mappings["HYXX个人知识库/Codex CLI 使用技巧记录.md"],
            "20_知识笔记/软件工程/Codex CLI 使用技巧记录.md",
        )
        self.assertNotIn("HYXX个人知识库/.obsidian", mappings)

    def test_requires_real_vault_marker(self):
        from scripts.restructure_obsidian_vault import build_migration_plan

        with workspace_temp_dir() as vault:
            with self.assertRaisesRegex(ValueError, r"\.obsidian"):
                build_migration_plan(vault)


class SnapshotTests(unittest.TestCase):
    def test_backup_contains_all_old_directories_and_manifest_has_hashes(self):
        from scripts.restructure_obsidian_vault import (
            build_migration_plan,
            create_backup,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            records_dir = vault / "90_系统" / "迁移记录"
            backup = records_dir / "2026-07-27-迁移前备份.zip"
            manifest = records_dir / "2026-07-27-文件清单.json"
            create_backup(plan, backup)
            write_manifest(plan, manifest)

            with zipfile.ZipFile(backup) as archive:
                names = set(archive.namelist())
            payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertIn("AI相关知识库/2026年07月/一张图看懂 AI Agent 全流程.md", names)
        self.assertIn("HYXX个人知识库/.obsidian/", names)
        self.assertTrue(all(record["sha256"] for record in payload["files"]))


class CommandLineTests(unittest.TestCase):
    def test_default_command_only_prints_plan(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/restructure_obsidian_vault.py",
                    "--vault",
                    str(vault),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("预览模式", result.stdout)
            self.assertFalse((vault / "20_知识笔记").exists())
