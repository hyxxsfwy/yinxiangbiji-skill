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


class ScaffoldTests(unittest.TestCase):
    def test_creates_exact_lifecycle_tree_and_index_contracts(self):
        from scripts.restructure_obsidian_vault import (
            build_migration_plan,
            ensure_target_structure,
            write_vault_documents,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            ensure_target_structure(plan)
            write_vault_documents(plan)

            expected = (
                "00_首页.md",
                "10_项目/目录索引.md",
                "20_知识笔记/目录索引.md",
                "20_知识笔记/知识地图.md",
                "20_知识笔记/AI",
                "20_知识笔记/Quant",
                "20_知识笔记/软件工程",
                "20_知识笔记/投资理财",
                "20_知识笔记/个人成长",
                "30_精选资料/AI/目录索引.md",
                "30_精选资料/Quant/目录索引.md",
                "30_精选资料/软件工程/目录索引.md",
                "30_精选资料/投资理财/目录索引.md",
                "30_精选资料/个人成长/目录索引.md",
                "90_系统/知识库治理/管理规则.md",
                "90_系统/知识库治理/主题词表.md",
                "90_系统/知识库治理/别名词典.md",
            )
            for relative in expected:
                self.assertTrue(vault.joinpath(relative).exists(), relative)

            self.assertFalse((vault / "10_项目" / "AI").exists())
            self.assertFalse(
                (vault / "20_知识笔记" / "AI" / "目录索引.md").exists()
            )

            catalog = (
                vault / "20_知识笔记" / "目录索引.md"
            ).read_text(encoding="utf-8")
            knowledge_map = (
                vault / "20_知识笔记" / "知识地图.md"
            ).read_text(encoding="utf-8")
            self.assertIn("> [!info] 功能", catalog)
            self.assertIn("> [!info] 构建规则", catalog)
            self.assertIn("可由脚本或 AI 完整重建", catalog)
            self.assertIn("<!-- llmwiki:auto:start -->", knowledge_map)
            self.assertIn("<!-- llmwiki:auto:end -->", knowledge_map)


class CopyAndMetadataTests(unittest.TestCase):
    def test_copies_content_with_required_properties_and_preserves_body(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            original_body = (
                vault
                / "AI相关知识库"
                / "2026年07月"
                / "一张图看懂 AI Agent 全流程.md"
            ).read_text(encoding="utf-8").split("---", 2)[2]
            apply_copy_phase(plan)

            agent = (
                vault
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / "一张图看懂 AI Agent 全流程.md"
            ).read_text(encoding="utf-8")
            codex = (
                vault
                / "20_知识笔记"
                / "软件工程"
                / "Codex CLI 使用技巧记录.md"
            ).read_text(encoding="utf-8")

        self.assertIn('type: "资料"', agent)
        self.assertIn('domain: "AI"', agent)
        self.assertIn('status: "待提炼"', agent)
        self.assertIn("主题/Agent", agent)
        self.assertIn(original_body.strip(), agent)
        self.assertIn('type: "知识"', codex)
        self.assertIn('domain: "软件工程"', codex)
        self.assertIn('status: "常青"', codex)
        self.assertIn('review_status: "human-approved"', codex)

    def test_preserves_ai_body_attachment_layout_and_reference(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            split_frontmatter,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            source = (
                vault
                / "AI相关知识库"
                / "2026年07月"
                / "一张图看懂 AI Agent 全流程.md"
            )
            _, original_body = split_frontmatter(source.read_text(encoding="utf-8"))
            apply_copy_phase(build_migration_plan(vault))
            destination = (
                vault
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / source.name
            )
            _, copied_body = split_frontmatter(
                destination.read_text(encoding="utf-8")
            )
            copied_attachment = (
                vault / "30_精选资料" / "AI" / "_attachments" / "agent.png"
            )
            copied_attachment_bytes = copied_attachment.read_bytes()

        self.assertEqual(
            copied_body.lstrip("\r\n"),
            original_body.lstrip("\r\n"),
        )
        self.assertIn("![图](../_attachments/agent.png)", copied_body)
        self.assertEqual(copied_attachment_bytes, b"image")

    def test_does_not_copy_nested_personal_obsidian_config(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            apply_copy_phase(build_migration_plan(vault))
            self.assertFalse(
                (vault / "20_知识笔记" / "软件工程" / ".obsidian").exists()
            )

    def test_merge_frontmatter_overrides_required_fields_in_fixed_order(self):
        from scripts.restructure_obsidian_vault import merge_frontmatter

        markdown = (
            "---\n"
            'updated: "2026-07-22"\n'
            'type: "webclip"\n'
            'created: "2026-07-21"\n'
            'custom: "保留"\n'
            "---\n\n"
            "# 原标题\n\n正文。\n"
        )

        merged = merge_frontmatter(
            markdown,
            {
                "type": "资料",
                "domain": "AI",
                "status": "待提炼",
                "tags": ["主题/Agent"],
            },
        )

        self.assertEqual(
            merged,
            "---\n"
            'type: "资料"\n'
            'domain: "AI"\n'
            'status: "待提炼"\n'
            'created: "2026-07-21"\n'
            'updated: "2026-07-22"\n'
            'tags: ["主题/Agent"]\n'
            'custom: "保留"\n'
            "---\n\n"
            "# 原标题\n\n正文。\n",
        )


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

    def test_apply_requires_exact_confirmation(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/restructure_obsidian_vault.py",
                    "--vault",
                    str(vault),
                    "--apply",
                    "--confirm",
                    "WRONG",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MIGRATE_OBSIDIAN_VAULT", result.stderr)
            self.assertFalse((vault / "20_知识笔记").exists())

    def test_confirmed_apply_creates_snapshot_and_keeps_old_directories(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/restructure_obsidian_vault.py",
                    "--vault",
                    str(vault),
                    "--apply",
                    "--confirm",
                    "MIGRATE_OBSIDIAN_VAULT",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (
                    vault
                    / "90_系统"
                    / "迁移记录"
                    / "2026-07-27-迁移前备份.zip"
                ).is_file()
            )
            for old_directory in (
                "AI相关知识库",
                "Quant相关知识库",
                "HYXX个人知识库",
            ):
                self.assertTrue((vault / old_directory).exists())
            self.assertTrue((vault / "30_精选资料" / "AI").exists())
