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

    def test_backup_reuses_matching_archive_but_rejects_changed_sources(self):
        from scripts.restructure_obsidian_vault import (
            build_migration_plan,
            create_backup,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            backup = vault / "90_系统" / "迁移记录" / "backup.zip"
            create_backup(plan, backup)
            original_backup = backup.read_bytes()

            self.assertEqual(create_backup(plan, backup), backup)
            self.assertEqual(backup.read_bytes(), original_backup)

            (vault / "AI相关知识库" / "_attachments" / "agent.png").write_bytes(
                b"changed-image"
            )
            with self.assertRaisesRegex(FileExistsError, "不匹配"):
                create_backup(plan, backup)


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
            source.write_bytes(
                (
                    "---\r\n"
                    'created: "2026-07-21 08:00:00"\r\n'
                    'updated: "2026-07-22 08:00:00"\r\n'
                    'source: "Evernote"\r\n'
                    'source_guid: "agent-guid"\r\n'
                    'notebook: "微信"\r\n'
                    'type: "webclip"\r\n'
                    "---\r\n\r\n\r\n"
                    "# 一张图看懂 AI Agent 全流程\r\n\r\n"
                    "![图](../_attachments/agent.png)\r\n"
                ).encode("utf-8")
            )
            with source.open("r", encoding="utf-8", newline="") as stream:
                _, original_body = split_frontmatter(stream.read())
            apply_copy_phase(build_migration_plan(vault))
            destination = (
                vault
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / source.name
            )
            with destination.open("r", encoding="utf-8", newline="") as stream:
                _, copied_body = split_frontmatter(stream.read())
            copied_attachment = (
                vault / "30_精选资料" / "AI" / "_attachments" / "agent.png"
            )
            copied_attachment_bytes = copied_attachment.read_bytes()

        self.assertEqual(copied_body, original_body)
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

    def test_merge_frontmatter_preserves_exact_suffix_after_closing_marker(self):
        from scripts.restructure_obsidian_vault import merge_frontmatter

        cases = (
            (
                "---\r\ntype: old\r\n---BODY",
                '---\ntype: "知识"\n---BODY',
            ),
            (
                "---\ntype: old\n---\nBODY",
                '---\ntype: "知识"\n---\nBODY',
            ),
            (
                "---\r\ntype: old\r\n---\r\n\r\nBODY\r\n",
                '---\ntype: "知识"\n---\r\n\r\nBODY\r\n',
            ),
            (
                "---\ntype: old\n---\n\n\nBODY\n",
                '---\ntype: "知识"\n---\n\n\nBODY\n',
            ),
        )

        for markdown, expected in cases:
            with self.subTest(markdown=repr(markdown)):
                self.assertEqual(
                    merge_frontmatter(markdown, {"type": "知识"}),
                    expected,
                )


class LinkValidationTests(unittest.TestCase):
    def test_reports_missing_local_target_and_ignores_http(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            note = vault / "note.md"
            note.write_text(
                "![缺图](assets/missing.png)\n"
                "[外部](https://example.com)\n",
                encoding="utf-8",
            )
            issues = scan_local_links(vault)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].source.name, "note.md")
        self.assertEqual(issues[0].target, "assets/missing.png")
        self.assertEqual(issues[0].reason, "目标不存在")

    def test_rejects_link_resolving_outside_vault(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "note.md").write_text(
                "[越界](../../secret.txt)\n",
                encoding="utf-8",
            )
            issues = scan_local_links(vault)

        self.assertEqual(issues[0].reason, "目标越出 vault")

    def test_decodes_percent_encoded_local_paths(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "2026年07月").mkdir()
            (vault / "2026年07月" / "文章.md").write_text(
                "# 正文\n",
                encoding="utf-8",
            )
            (vault / "index.md").write_text(
                "[文章](2026%E5%B9%B407%E6%9C%88/%E6%96%87%E7%AB%A0.md)\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_local_links(vault), ())


class CleanupGateTests(unittest.TestCase):
    def test_validation_failure_keeps_all_old_directories(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            cleanup_old_directories,
            create_backup,
            validate_migration,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            manifest = (
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            create_backup(
                plan,
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-迁移前备份.zip",
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            (
                vault / "30_精选资料" / "AI" / "_attachments" / "agent.png"
            ).unlink()
            report = validate_migration(vault, manifest)
            with self.assertRaisesRegex(RuntimeError, "验证未通过"):
                cleanup_old_directories(plan, report)
            self.assertTrue((vault / "AI相关知识库").exists())
            self.assertTrue((vault / "Quant相关知识库").exists())
            self.assertTrue((vault / "HYXX个人知识库").exists())

    def test_successful_validation_removes_only_three_old_directories(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            cleanup_old_directories,
            create_backup,
            validate_migration,
            write_link_report,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            keep = vault / "用户目录"
            keep.mkdir()
            plan = build_migration_plan(vault)
            manifest = (
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            create_backup(
                plan,
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-迁移前备份.zip",
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            report = validate_migration(vault, manifest)
            write_link_report(
                report,
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-链接检查.md",
            )
            self.assertTrue(report.passed, report.issues)
            cleanup_old_directories(plan, report)

            self.assertFalse((vault / "AI相关知识库").exists())
            self.assertFalse((vault / "Quant相关知识库").exists())
            self.assertFalse((vault / "HYXX个人知识库").exists())
            self.assertTrue(keep.exists())


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

    def test_confirmed_apply_creates_records_and_removes_old_directories(self):
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
            records = vault / "90_系统" / "迁移记录"
            for record in (
                "2026-07-27-迁移前备份.zip",
                "2026-07-27-文件清单.json",
                "2026-07-27-链接检查.md",
                "2026-07-27-迁移说明.md",
            ):
                self.assertTrue((records / record).is_file(), record)
            for old_directory in (
                "AI相关知识库",
                "Quant相关知识库",
                "HYXX个人知识库",
            ):
                self.assertFalse((vault / old_directory).exists())
            self.assertTrue((vault / "30_精选资料" / "AI").exists())
            self.assertIn(
                "- 结果：通过",
                (records / "2026-07-27-链接检查.md").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertIn(
                "- 旧目录已清理：是",
                (records / "2026-07-27-迁移说明.md").read_text(
                    encoding="utf-8"
                ),
            )

    def test_verify_supports_completed_vault_without_modifying_files(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            applied = subprocess.run(
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
            self.assertEqual(applied.returncode, 0, applied.stderr)
            before = {
                path.relative_to(vault): (path.stat().st_mtime_ns, path.read_bytes())
                for path in vault.rglob("*")
                if path.is_file()
            }

            verified = subprocess.run(
                [
                    sys.executable,
                    "scripts/restructure_obsidian_vault.py",
                    "--vault",
                    str(vault),
                    "--verify",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            after = {
                path.relative_to(vault): (path.stat().st_mtime_ns, path.read_bytes())
                for path in vault.rglob("*")
                if path.is_file()
            }

            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(after, before)

    def test_failed_validation_keeps_old_directories_and_writes_link_report(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            (vault / "AI相关知识库" / "_attachments" / "agent.png").unlink()

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

            self.assertEqual(result.returncode, 1, result.stderr)
            for old_directory in (
                "AI相关知识库",
                "Quant相关知识库",
                "HYXX个人知识库",
            ):
                self.assertTrue((vault / old_directory).exists())
            records = vault / "90_系统" / "迁移记录"
            self.assertIn(
                "- 结果：失败",
                (records / "2026-07-27-链接检查.md").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertFalse((records / "2026-07-27-迁移说明.md").exists())

    def test_apply_can_retry_after_late_conflict_without_rewriting_snapshot(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            conflicting_template = (
                vault / "90_系统" / "模板" / "精选资料模板.md"
            )
            conflicting_template.parent.mkdir(parents=True)
            conflicting_template.write_text("用户内容\n", encoding="utf-8")
            command = [
                sys.executable,
                "scripts/restructure_obsidian_vault.py",
                "--vault",
                str(vault),
                "--apply",
                "--confirm",
                "MIGRATE_OBSIDIAN_VAULT",
            ]

            first = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(first.returncode, 0)
            records = vault / "90_系统" / "迁移记录"
            backup = records / "2026-07-27-迁移前备份.zip"
            manifest = records / "2026-07-27-文件清单.json"
            original_backup = backup.read_bytes()
            original_manifest = manifest.read_bytes()

            conflicting_template.unlink()
            second = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(backup.read_bytes(), original_backup)
            self.assertEqual(manifest.read_bytes(), original_manifest)
