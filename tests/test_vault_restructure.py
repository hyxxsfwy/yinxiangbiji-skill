import json
import os
import stat
import subprocess
import sys
import unittest
import zipfile
from unittest.mock import patch

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


def apply_fixture_vault(vault):
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
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return vault / "80_系统" / "迁移记录"


def prepare_cleanup_fixture(vault):
    from scripts.restructure_obsidian_vault import (
        apply_copy_phase,
        build_migration_plan,
        create_backup,
        validate_migration,
        write_link_report,
        write_manifest,
    )

    seed_old_vault(vault)
    plan = build_migration_plan(vault)
    records = vault / "80_系统" / "迁移记录"
    backup = records / "2026-07-27-迁移前备份.zip"
    manifest = records / "2026-07-27-文件清单.json"
    create_backup(plan, backup)
    write_manifest(plan, manifest)
    apply_copy_phase(plan)
    report = validate_migration(vault, manifest)
    write_link_report(report, records / "2026-07-27-链接检查.md")
    if not report.passed:
        raise AssertionError(report.issues)
    return plan, records, manifest, report


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

    def test_plan_includes_existing_lifecycle_directories(self):
        from scripts.restructure_obsidian_vault import build_migration_plan

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "90_系统" / "模板").mkdir(parents=True)
            (vault / "90_系统" / "模板" / "旧模板.md").write_text(
                "# 旧模板\n",
                encoding="utf-8",
            )
            (vault / "99_归档" / "旧项目").mkdir(parents=True)
            (vault / "99_归档" / "旧项目" / "结项.md").write_text(
                "# 结项\n",
                encoding="utf-8",
            )

            plan = build_migration_plan(vault)
            mappings = {
                item.source.relative_to(vault).as_posix():
                item.destination.relative_to(vault).as_posix()
                for item in plan.items
            }

        self.assertEqual(mappings["90_系统"], "80_系统")
        self.assertEqual(mappings["99_归档"], "90_归档")

    def test_preflight_accepts_same_content_but_rejects_different_content(self):
        from scripts.restructure_obsidian_vault import (
            build_migration_plan,
            find_migration_conflicts,
        )

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = vault / "90_系统" / "模板" / "模板.md"
            destination = vault / "80_系统" / "模板" / "模板.md"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_text("# 相同\n", encoding="utf-8")
            destination.write_text("# 相同\n", encoding="utf-8")
            plan = build_migration_plan(vault)

            self.assertEqual(find_migration_conflicts(plan), ())

            destination.write_text("# 冲突\n", encoding="utf-8")
            conflicts = find_migration_conflicts(plan)

        self.assertEqual(len(conflicts), 1)
        self.assertIn("80_系统/模板/模板.md", conflicts[0])

    def test_lifecycle_only_vault_does_not_require_retired_content_directories(self):
        from scripts.restructure_obsidian_vault import build_migration_plan

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "90_系统").mkdir()
            (vault / "99_归档").mkdir()

            plan = build_migration_plan(vault)

        self.assertEqual(
            tuple(path.name for path in plan.old_directories),
            ("90_系统", "99_归档"),
        )


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
            records_dir = vault / "80_系统" / "迁移记录"
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
            backup = vault / "80_系统" / "迁移记录" / "backup.zip"
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
    def test_knowledge_catalog_uses_explicit_markdown_suffix(self):
        from scripts.restructure_obsidian_vault import (
            DOMAINS,
            render_knowledge_catalog,
        )

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            for domain in DOMAINS:
                (
                    vault
                    / "20_知识笔记"
                    / domain
                ).mkdir(parents=True)
            note = (
                vault
                / "20_知识笔记"
                / "软件工程"
                / "Codex 5.6.md"
            )
            note.write_text(
                "---\n"
                "type: 知识\n"
                "domain: 软件工程\n"
                "status: 常青\n"
                "updated: 2026-07-27\n"
                "---\n\n"
                "# Codex 5.6\n\n"
                "正文介绍 Codex 的版本差异与实践方法。\n",
                encoding="utf-8",
            )

            catalog = render_knowledge_catalog(vault)

        self.assertIn(
            "[[软件工程/Codex 5.6.md|Codex 5.6]]",
            catalog,
        )

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
                "80_系统/知识库治理/管理规则.md",
                "80_系统/知识库治理/主题词表.md",
                "80_系统/知识库治理/别名词典.md",
                "90_归档",
                "99_废纸篓",
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

            home = (vault / "00_首页.md").read_text(encoding="utf-8")
            project_index = (
                vault / "10_项目" / "目录索引.md"
            ).read_text(encoding="utf-8")
            self.assertIn("[[80_系统/知识库治理/管理规则", home)
            self.assertNotIn("[[90_系统/", home)
            self.assertIn("进入 `90_归档`", project_index)
            self.assertNotIn("进入 `99_归档`", project_index)


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

    def test_scans_wikilinks_and_reports_a_missing_target(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "存在.md").write_text("# 存在\n", encoding="utf-8")
            (vault / "index.md").write_text(
                "[[存在|别名]]\n[[缺失笔记#章节]]\n",
                encoding="utf-8",
            )

            issues = scan_local_links(vault)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].target, "缺失笔记#章节")
        self.assertEqual(issues[0].reason, "目标不存在")

    def test_ignores_links_inside_indented_and_fenced_code_blocks(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "note.md").write_text(
                "    [参考](references/REFERENCE.md)\n"
                "    [[实体/Karpathy]]\n\n"
                "```markdown\n"
                "[示例](missing.md)\n"
                "[[概念/LLM Wiki]]\n"
                "```\n",
                encoding="utf-8",
            )

            self.assertEqual(scan_local_links(vault), ())

    def test_does_not_treat_double_bracket_external_link_labels_as_wikilinks(
        self,
    ):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "note.md").write_text(
                "[[1]](https://example.com/article)\n",
                encoding="utf-8",
            )

            self.assertEqual(scan_local_links(vault), ())

    def test_supports_angle_destination_optional_title_and_nested_parentheses(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            docs = vault / "docs"
            docs.mkdir()
            (docs / "a(b).md").write_text("# 目标\n", encoding="utf-8")
            (vault / "index.md").write_text(
                '[目标](<docs/a(b).md> "可选标题")\n',
                encoding="utf-8",
            )

            self.assertEqual(scan_local_links(vault), ())

    def test_image_target_must_be_a_regular_file(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "assets").mkdir()
            (vault / "index.md").write_text(
                "![错误图片](assets)\n",
                encoding="utf-8",
            )

            issues = scan_local_links(vault)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].reason, "目标不是普通文件")

    def test_ignores_anchors_obsidian_config_and_legacy_directories(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / ".obsidian" / "插件说明.md").write_text(
                "[缺失](missing-plugin.md)\n",
                encoding="utf-8",
            )
            legacy = vault / "AI相关知识库"
            legacy.mkdir()
            (legacy / "旧文章.md").write_text(
                "[缺失](missing-legacy.md)\n",
                encoding="utf-8",
            )
            (vault / "index.md").write_text(
                "[页内锚点](#章节)\n[[#Wiki章节]]\n",
                encoding="utf-8",
            )

            self.assertEqual(scan_local_links(vault), ())


class ValidationRobustnessTests(unittest.TestCase):
    def test_lifecycle_names_in_plain_prose_are_not_structure_residue(self):
        from scripts.restructure_obsidian_vault import (
            validate_migration,
        )

        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            note = vault / "20_知识笔记" / "AI" / "历史说明.md"
            note.write_text(
                "旧目录曾名为 `90_系统` 和 `99_归档`。\n",
                encoding="utf-8",
            )

            report = validate_migration(
                vault,
                records / "2026-07-27-文件清单.json",
            )

        self.assertTrue(report.passed, report.issues)

    def test_completed_verify_accepts_legacy_summary_after_manual_renumbering(self):
        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            summary = records / "2026-07-27-迁移说明.md"
            legacy_lines = [
                line
                for line in summary.read_text(encoding="utf-8").splitlines()
                if not line.startswith("- `90_系统` →")
                and not line.startswith("- `99_归档` →")
            ]
            summary.write_text(
                "\n".join(legacy_lines) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
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

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_required_markdown_directory_is_reported_as_missing_file(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            validate_migration,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            manifest = (
                vault
                / "80_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            required_markdown = vault / "00_首页.md"
            required_markdown.unlink()
            required_markdown.mkdir()

            report = validate_migration(vault, manifest)

        self.assertFalse(report.passed)
        self.assertIn(f"缺少必需路径: {required_markdown}", report.issues)

    def test_arbitrary_markdown_directory_is_skipped_and_issue_is_reported(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            validate_migration,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            manifest = (
                vault
                / "80_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            (vault / "A.md").mkdir()
            (vault / "z-broken.md").write_text(
                "[缺失](missing.txt)\n",
                encoding="utf-8",
            )

            report = validate_migration(vault, manifest)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(
                "missing.txt: 目标不存在" in issue
                for issue in report.issues
            ),
            report.issues,
        )

    def test_completed_verify_requires_all_four_records_as_regular_files(self):
        from scripts.restructure_obsidian_vault import verify_completed_vault

        for record_name in (
            "2026-07-27-迁移前备份.zip",
            "2026-07-27-链接检查.md",
            "2026-07-27-迁移说明.md",
        ):
            with self.subTest(record=record_name), workspace_temp_dir() as vault:
                records = apply_fixture_vault(vault)
                record = records / record_name
                record.unlink()
                record.mkdir()

                report = verify_completed_vault(vault)

                self.assertFalse(report.passed, report.issues)
                self.assertTrue(
                    any(record_name in issue for issue in report.issues),
                    report.issues,
                )

    def test_completed_verify_reports_manifest_directory_without_traceback(self):
        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            manifest = records / "2026-07-27-文件清单.json"
            manifest.unlink()
            manifest.mkdir()

            result = subprocess.run(
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

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_completed_verify_rejects_truncated_manifest_and_deleted_target(self):
        from scripts.restructure_obsidian_vault import verify_completed_vault

        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            manifest = records / "2026-07-27-文件清单.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            removed = next(
                record
                for record in payload["files"]
                if record["source"].endswith("Codex CLI 使用技巧记录.md")
            )
            payload["files"].remove(removed)
            manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (vault / removed["destination"]).unlink()

            report = verify_completed_vault(vault)

        self.assertFalse(report.passed, report.issues)
        self.assertTrue(
            any("ZIP" in issue or "完整" in issue for issue in report.issues),
            report.issues,
        )

    def test_completed_verify_rejects_duplicate_and_out_of_bounds_records(self):
        from scripts.restructure_obsidian_vault import verify_completed_vault

        mutations = {
            "duplicate": lambda payload: payload["files"].append(
                dict(payload["files"][0])
            ),
            "outside": lambda payload: payload["files"].append(
                {
                    "source": "../vault之外.md",
                    "destination": None,
                    "size": 1,
                    "sha256": "0" * 64,
                    "preserve_hash": False,
                }
            ),
            "outside-destination": lambda payload: payload["files"][0].update(
                {"destination": "../vault之外.md"}
            ),
            "duplicate-destination": lambda payload: payload["files"][1].update(
                {"destination": payload["files"][0]["destination"]}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name), workspace_temp_dir() as vault:
                records = apply_fixture_vault(vault)
                manifest = records / "2026-07-27-文件清单.json"
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                mutate(payload)
                manifest.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

                report = verify_completed_vault(vault)

                self.assertFalse(report.passed, report.issues)

    def test_completed_verify_rejects_wrong_manifest_vault_and_corrupted_zip(self):
        from scripts.restructure_obsidian_vault import verify_completed_vault

        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            manifest = records / "2026-07-27-文件清单.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["vault"] = str(vault / "其它目录")
            manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            wrong_vault_report = verify_completed_vault(vault)

        self.assertFalse(wrong_vault_report.passed, wrong_vault_report.issues)

        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            backup = records / "2026-07-27-迁移前备份.zip"
            backup.write_bytes(backup.read_bytes()[:128] + b"corrupted")

            corrupted_zip_report = verify_completed_vault(vault)

        self.assertFalse(corrupted_zip_report.passed, corrupted_zip_report.issues)

    def test_completed_verify_recomputes_and_validates_reports(self):
        from scripts.restructure_obsidian_vault import verify_completed_vault

        mutations = {
            "link-report": (
                "2026-07-27-链接检查.md",
                lambda text: text.replace("- 结果：通过", "- 结果：失败"),
            ),
            "summary": (
                "2026-07-27-迁移说明.md",
                lambda text: text.replace("- 旧目录已清理：是", "- 旧目录已清理：否"),
            ),
        }
        for name, (record_name, mutate) in mutations.items():
            with self.subTest(record=name), workspace_temp_dir() as vault:
                records = apply_fixture_vault(vault)
                record = records / record_name
                record.write_text(
                    mutate(record.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )

                report = verify_completed_vault(vault)

                self.assertFalse(report.passed, report.issues)

    def test_new_apply_manifest_records_migration_and_link_results(self):
        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            payload = json.loads(
                (records / "2026-07-27-文件清单.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(payload.get("schema_version"), 2)
        self.assertEqual(payload.get("migration_result"), "completed")
        link_result = payload.get("link_check_result", {})
        self.assertEqual(link_result.get("result"), "passed")
        self.assertEqual(link_result.get("issues"), 0)


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
                / "80_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            create_backup(
                plan,
                vault
                / "80_系统"
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
                / "80_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            create_backup(
                plan,
                vault
                / "80_系统"
                / "迁移记录"
                / "2026-07-27-迁移前备份.zip",
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            report = validate_migration(vault, manifest)
            write_link_report(
                report,
                vault
                / "80_系统"
                / "迁移记录"
                / "2026-07-27-链接检查.md",
            )
            self.assertTrue(report.passed, report.issues)
            cleanup_old_directories(plan, report)

            self.assertFalse((vault / "AI相关知识库").exists())
            self.assertFalse((vault / "Quant相关知识库").exists())
            self.assertFalse((vault / "HYXX个人知识库").exists())
            self.assertTrue(keep.exists())

    def test_source_changes_after_snapshot_block_cleanup(self):
        mutations = {
            "mapped-markdown": lambda vault: (
                vault
                / "AI相关知识库"
                / "2026年07月"
                / "一张图看懂 AI Agent 全流程.md"
            ).write_text("快照后新内容\n", encoding="utf-8"),
            "binary": lambda vault: (
                vault / "AI相关知识库" / "_attachments" / "agent.png"
            ).write_bytes(b"changed-after-snapshot"),
            "unmapped-file": lambda vault: (
                vault / "HYXX个人知识库" / "快照后新增.txt"
            ).write_text("新增内容\n", encoding="utf-8"),
        }

        for name, mutate in mutations.items():
            with self.subTest(mutation=name), workspace_temp_dir() as vault:
                from scripts.restructure_obsidian_vault import (
                    cleanup_old_directories,
                )

                plan, _, _, report = prepare_cleanup_fixture(vault)
                mutate(vault)

                with self.assertRaisesRegex(RuntimeError, "源|快照|ZIP|清单"):
                    cleanup_old_directories(plan, report)

                for old_directory in plan.old_directories:
                    self.assertTrue(old_directory.is_dir())

    def test_cleanup_failure_on_second_directory_restores_all_sources(self):
        import scripts.restructure_obsidian_vault as migration

        with workspace_temp_dir() as vault:
            plan, _, manifest, report = prepare_cleanup_fixture(vault)
            original_rmtree = migration.shutil.rmtree
            call_count = 0

            def fail_on_second_directory(path, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return original_rmtree(path, *args, **kwargs)
                raise OSError("第二个目录删除失败")

            with patch(
                "scripts.restructure_obsidian_vault.shutil.rmtree",
                side_effect=fail_on_second_directory,
            ):
                with self.assertRaisesRegex(OSError, "第二个目录删除失败"):
                    migration.cleanup_old_directories(plan, report)

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            for record in payload["files"]:
                source = vault / record["source"]
                self.assertTrue(source.is_file(), record["source"])
                self.assertEqual(source.stat().st_size, record["size"])
                self.assertEqual(migration.sha256_file(source), record["sha256"])

    def test_cleanup_failure_after_nested_file_removal_restores_all_sources(self):
        import scripts.restructure_obsidian_vault as migration

        with workspace_temp_dir() as vault:
            plan, _, manifest, report = prepare_cleanup_fixture(vault)

            def fail_after_nested_file_removal(path, *args, **kwargs):
                victim = (
                    path
                    / "2026年07月"
                    / "一张图看懂 AI Agent 全流程.md"
                )
                victim.unlink()
                raise OSError("嵌套文件删除失败")

            with patch(
                "scripts.restructure_obsidian_vault.shutil.rmtree",
                side_effect=fail_after_nested_file_removal,
            ):
                with self.assertRaisesRegex(OSError, "嵌套文件删除失败"):
                    migration.cleanup_old_directories(plan, report)

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            for record in payload["files"]:
                source = vault / record["source"]
                self.assertTrue(source.is_file(), record["source"])
                self.assertEqual(source.stat().st_size, record["size"])
                self.assertEqual(migration.sha256_file(source), record["sha256"])

    def test_cleanup_failure_restores_lifecycle_sources(self):
        import scripts.restructure_obsidian_vault as migration

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            system_file = vault / "90_系统" / "模板" / "旧模板.md"
            archive_file = vault / "99_归档" / "旧项目" / "结项.md"
            system_file.parent.mkdir(parents=True)
            archive_file.parent.mkdir(parents=True)
            system_file.write_text("# 旧模板\n", encoding="utf-8")
            archive_file.write_text("# 结项\n", encoding="utf-8")
            plan = migration.build_migration_plan(vault)
            record_paths = migration.migration_record_paths(vault, plan)
            backup = record_paths["backup"]
            manifest = record_paths["manifest"]
            link_report = record_paths["link_report"]
            migration.create_backup(plan, backup)
            migration.write_manifest(plan, manifest)
            report = migration.ValidationReport(True, (), 2, 0, 0)
            migration.write_link_report(report, link_report)
            original_rmtree = migration.shutil.rmtree
            call_count = 0

            def fail_on_second_directory(path, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return original_rmtree(path, *args, **kwargs)
                raise OSError("生命周期目录删除失败")

            with patch(
                "scripts.restructure_obsidian_vault.shutil.rmtree",
                side_effect=fail_on_second_directory,
            ):
                with self.assertRaisesRegex(OSError, "生命周期目录删除失败"):
                    migration.cleanup_old_directories(plan, report)

            self.assertEqual(system_file.read_text(encoding="utf-8"), "# 旧模板\n")
            self.assertEqual(archive_file.read_text(encoding="utf-8"), "# 结项\n")

    @unittest.skipUnless(
        sys.platform == "win32",
        "Windows ReadOnly 目录行为回归",
    )
    def test_cleanup_removes_readonly_old_directories_and_nested_directories(self):
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
            plan = build_migration_plan(vault)
            records = vault / "80_系统" / "迁移记录"
            manifest = records / "2026-07-27-文件清单.json"
            create_backup(plan, records / "2026-07-27-迁移前备份.zip")
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            report = validate_migration(vault, manifest)
            write_link_report(report, records / "2026-07-27-链接检查.md")
            self.assertTrue(report.passed, report.issues)
            readonly_directories = tuple(
                directory
                for old_directory in plan.old_directories
                for directory in (old_directory, *old_directory.rglob("*"))
                if directory.is_dir()
            )
            old_files = tuple(
                path
                for old_directory in plan.old_directories
                for path in old_directory.rglob("*")
                if path.is_file()
            )
            for directory in readonly_directories:
                directory.chmod(stat.S_IREAD)

            failure = None
            try:
                cleanup_old_directories(plan, report)
            except PermissionError as exc:
                failure = exc
            finally:
                remaining = tuple(
                    path
                    for path in readonly_directories
                    if path.exists()
                )
                deleted_files = tuple(
                    path for path in old_files if not path.exists()
                )
                for directory in remaining:
                    directory.chmod(stat.S_IWRITE)

            if failure is not None:
                self.assertTrue(deleted_files)
            self.assertIsNone(
                failure,
                f"只读目录清理失败，已删文件: {deleted_files}，"
                f"仍存目录: {remaining}",
            )
            self.assertEqual(remaining, ())


class CommandLineTests(unittest.TestCase):
    def test_active_vault_lock_blocks_migration_and_restructure_writes(self):
        from scripts import restructure_obsidian_vault
        from scripts.vault_state import (
            StateLockConflict,
            VaultStatePaths,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            seed_old_vault(vault)
            legacy_root = temp_dir / "repo" / ".state"
            legacy_root.mkdir(parents=True)
            legacy_source = legacy_root / "export-AI-legacy.json"
            legacy_source.write_text('{"legacy": true}\n', encoding="utf-8")
            paths = VaultStatePaths.for_vault(vault)

            with (
                runtime_write_lock(paths, "active-task"),
                patch.object(
                    restructure_obsidian_vault,
                    "REPO_ROOT",
                    legacy_root.parent,
                ),
            ):
                business_before = {
                    path.relative_to(vault): path.read_bytes()
                    for path in vault.rglob("*")
                    if path.is_file() and ".state" not in path.parts
                }
                manifests_before = tuple(paths.migrations.glob("migration-*.json"))
                with self.assertRaises(StateLockConflict):
                    restructure_obsidian_vault.main(
                        [
                            "--vault",
                            str(vault),
                            "--apply",
                            "--confirm",
                            "MIGRATE_OBSIDIAN_VAULT",
                        ]
                    )

                business_after = {
                    path.relative_to(vault): path.read_bytes()
                    for path in vault.rglob("*")
                    if path.is_file() and ".state" not in path.parts
                }
                self.assertFalse(
                    (paths.single_domain / legacy_source.name).exists()
                )
                self.assertEqual(
                    tuple(paths.migrations.glob("migration-*.json")),
                    manifests_before,
                )
                self.assertEqual(business_after, business_before)

    def test_global_vault_is_used_when_vault_argument_is_omitted(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            environment = os.environ.copy()
            environment["OBSIDIAN_VAULT_PATH"] = str(vault)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/restructure_obsidian_vault.py",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("预览模式", result.stdout)
            self.assertFalse((vault / "20_知识笔记").exists())

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

    def test_apply_moves_old_lifecycle_files_and_creates_trash(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            system_file = vault / "90_系统" / "模板" / "旧模板.md"
            archive_file = vault / "99_归档" / "旧项目" / "结项.md"
            system_file.parent.mkdir(parents=True)
            archive_file.parent.mkdir(parents=True)
            system_file.write_text("# 旧模板\n", encoding="utf-8")
            archive_file.write_text("# 结项\n", encoding="utf-8")

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
            self.assertTrue((vault / "80_系统" / "模板" / "旧模板.md").is_file())
            self.assertTrue((vault / "90_归档" / "旧项目" / "结项.md").is_file())
            self.assertTrue((vault / "99_废纸篓").is_dir())
            self.assertFalse((vault / "90_系统").exists())
            self.assertFalse((vault / "99_归档").exists())

    def test_apply_merges_identical_lifecycle_file(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = vault / "90_系统" / "模板" / "相同.md"
            destination = vault / "80_系统" / "模板" / "相同.md"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_text("# 相同\n", encoding="utf-8")
            destination.write_text("# 相同\n", encoding="utf-8")

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
            self.assertEqual(destination.read_text(encoding="utf-8"), "# 相同\n")
            self.assertFalse((vault / "90_系统").exists())

    def test_apply_rewrites_lifecycle_paths_inside_markdown(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            system_note = vault / "90_系统" / "说明.md"
            archive_note = vault / "99_归档" / "旧项目.md"
            system_note.parent.mkdir(parents=True)
            archive_note.parent.mkdir(parents=True)
            system_note.write_text(
                "[[90_系统/模板/知识笔记模板|模板]]\n",
                encoding="utf-8",
            )
            archive_note.write_text(
                "[归档](../99_归档/旧项目.md)\n",
                encoding="utf-8",
            )

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
            migrated_system = (
                vault / "80_系统" / "说明.md"
            ).read_text(encoding="utf-8")
            migrated_archive = (
                vault / "90_归档" / "旧项目.md"
            ).read_text(encoding="utf-8")
            self.assertIn("[[80_系统/模板/知识笔记模板|模板]]", migrated_system)
            self.assertIn("[归档](../90_归档/旧项目.md)", migrated_archive)
            self.assertNotIn("90_系统/", migrated_system)
            self.assertNotIn("99_归档/", migrated_archive)

    def test_apply_stops_before_snapshot_when_lifecycle_file_conflicts(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = vault / "90_系统" / "模板" / "冲突.md"
            destination = vault / "80_系统" / "模板" / "冲突.md"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_text("# 旧内容\n", encoding="utf-8")
            destination.write_text("# 新内容\n", encoding="utf-8")

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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("80_系统/模板/冲突.md", result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), "# 旧内容\n")
            self.assertEqual(destination.read_text(encoding="utf-8"), "# 新内容\n")
            self.assertEqual(tuple(vault.rglob("*迁移前备份.zip")), ())

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
            records = vault / "80_系统" / "迁移记录"
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

    def test_reapplying_completed_vault_is_idempotent(self):
        with workspace_temp_dir() as vault:
            apply_fixture_vault(vault)
            before = {
                path.relative_to(vault): path.read_bytes()
                for path in vault.rglob("*")
                if path.is_file()
            }

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
            after = {
                path.relative_to(vault): path.read_bytes()
                for path in vault.rglob("*")
                if path.is_file()
            }

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(after, before)

    def test_verify_rejects_missing_canonical_lifecycle_directory(self):
        with workspace_temp_dir() as vault:
            records = apply_fixture_vault(vault)
            (vault / "99_废纸篓").rmdir()

            result = subprocess.run(
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("99_废纸篓", result.stderr)
            self.assertTrue(records.is_dir())

    def test_verify_rejects_remaining_legacy_lifecycle_directories(self):
        with workspace_temp_dir() as vault:
            apply_fixture_vault(vault)
            (vault / "90_系统").mkdir()
            (vault / "99_归档").mkdir()

            result = subprocess.run(
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

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("90_系统", result.stderr)
            self.assertIn("99_归档", result.stderr)

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
            records = vault / "80_系统" / "迁移记录"
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
                vault / "80_系统" / "模板" / "精选资料模板.md"
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
            records = vault / "80_系统" / "迁移记录"
            backup = records / "2026-07-27-迁移前备份.zip"
            manifest = records / "2026-07-27-文件清单.json"
            original_backup = backup.read_bytes()
            original_manifest = json.loads(
                manifest.read_text(encoding="utf-8")
            )

            conflicting_template.unlink()
            second = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(backup.read_bytes(), original_backup)
            completed_manifest = json.loads(
                manifest.read_text(encoding="utf-8")
            )
            self.assertEqual(
                completed_manifest["created_at"],
                original_manifest["created_at"],
            )
            self.assertEqual(
                completed_manifest["files"],
                original_manifest["files"],
            )
            self.assertEqual(
                completed_manifest["migration_result"],
                "completed",
            )
