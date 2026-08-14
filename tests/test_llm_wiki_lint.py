import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.lint_llm_wiki import lint_vault, main
from tests.support import create_directory_link_or_skip, workspace_temp_dir


FIXED_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed_minimal_vault(root: Path) -> Path:
    (root / ".obsidian").mkdir(parents=True)
    (root / "10_项目").mkdir()
    (root / "90_归档").mkdir()
    (root / "99_废纸篓").mkdir()
    write(root / "AGENTS.md", "# LLM Wiki 维护规则\n")
    index_frontmatter = (
        "---\ntype: 索引\ndomain: 知识管理\nstatus: 常青\n"
        "review_status: human-approved\nllm_policy: standard\n---\n"
    )
    write(
        root / "30_精选资料/知识管理/目录索引.md",
        index_frontmatter
        + "\n# 目录索引\n\n- [[2026年08月/来源一]]\n"
        "- [[2026年08月/来源二]]\n",
    )
    source_frontmatter = (
        "---\ntype: 资料\ndomain: 知识管理\nstatus: 待提炼\n"
        "review_status: pending\nllm_policy: strict\n---\n"
    )
    write(
        root / "30_精选资料/知识管理/2026年08月/来源一.md",
        source_frontmatter + "\n# 来源一\n",
    )
    write(
        root / "30_精选资料/知识管理/2026年08月/来源二.md",
        source_frontmatter + "\n# 来源二\n",
    )
    write(
        root / "20_知识笔记/目录索引.md",
        "---\ntype: 索引\ndomain: \nstatus: 常青\n"
        "review_status: human-approved\nllm_policy: standard\n---\n\n"
        "# 目录索引\n\n- [[知识管理/复利知识]]\n",
    )
    write(
        root / "20_知识笔记/知识地图.md",
        "---\ntype: 索引\ndomain: \nstatus: 常青\nreview_status: human-approved\n"
        "llm_policy: standard\n---\n\n# 知识地图\n\n"
        "<!-- llmwiki:auto:start -->\n[[知识管理/复利知识]]\n"
        "<!-- llmwiki:auto:end -->\n",
    )
    write(
        root / "20_知识笔记/知识管理/复利知识.md",
        "---\ntype: 知识\ndomain: 知识管理\nstatus: 待提炼\n"
        "review_status: pending\nllm_policy: standard\n"
        "sources: [\"[[30_精选资料/知识管理/2026年08月/来源一]]\"]\n"
        "---\n\n# 复利知识\n",
    )
    write(
        root / "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md",
        "# LLM Wiki 操作日志\n\n"
        "## [2026-08-14T16:00:00+08:00] ingest\n"
        "- input: [[30_精选资料/知识管理/2026年08月/来源一]]\n"
        "- read_scope: 1 source, 2 indexes\n"
        "- proposed_writes: [复利知识]\n"
        "- actual_writes: []\n"
        "- review_status: pending\n"
        "- issues: 0\n",
    )
    return root


class LintCoreTests(unittest.TestCase):
    def test_minimal_vault_has_no_basic_structure_errors(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertTrue(report.ok)
        self.assertEqual(
            report.to_dict()["checked_at"],
            "2026-08-14T08:00:00+00:00",
        )

    def test_missing_schema_and_invalid_properties_have_stable_codes(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            (vault / "AGENTS.md").unlink()
            note = vault / "20_知识笔记/知识管理/复利知识.md"
            note.write_text(
                note.read_text(encoding="utf-8").replace(
                    "domain: 知识管理",
                    "domain: 未知领域",
                ),
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertFalse(report.ok)
        self.assertEqual(
            {issue.code for issue in report.issues},
            {"MISSING_SCHEMA", "INVALID_PROPERTY_VALUE"},
        )

    def test_missing_governance_directory_has_stable_code(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            governance = vault / "80_系统/知识库治理"
            governance.rename(vault / "80_系统/知识库治理-缺失")
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertIn(
            "MISSING_REQUIRED_DIRECTORY",
            {issue.code for issue in report.issues},
        )

    def test_invalid_frontmatter_does_not_stop_remaining_scan(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            write(
                vault / "20_知识笔记/知识管理/损坏.md",
                "---\ninvalid yaml line\n---\n# 损坏\n",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertIn(
            "INVALID_FRONTMATTER",
            {item.code for item in report.issues},
        )
        self.assertGreater(report.checked_files, 1)

    def test_array_property_has_stable_code_and_scan_continues(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            frontmatter = (
                "---\ntype: 知识\ndomain: [\"知识管理\"]\nstatus: 待提炼\n"
                "review_status: pending\nllm_policy: standard\n---\n"
            )
            write(
                vault / "20_知识笔记/知识管理/00-array.md",
                frontmatter + "\n# 数组属性\n",
            )
            write(
                vault / "20_知识笔记/知识管理/99-after.md",
                frontmatter.replace(
                    'domain: ["知识管理"]',
                    "domain: 未知领域",
                )
                + "\n# 后续文件\n",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertEqual(
            [(item.path, item.code) for item in report.issues],
            [
                (
                    "20_知识笔记/知识管理/00-array.md",
                    "INVALID_PROPERTY_VALUE",
                ),
                (
                    "20_知识笔记/知识管理/99-after.md",
                    "INVALID_PROPERTY_VALUE",
                ),
            ],
        )

    def test_directory_link_cannot_escape_vault(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root / "vault")
            outside = root / "outside"
            outside.mkdir()
            write(outside / "escaped.md", "# escaped\n")
            link = vault / "20_知识笔记/逃逸目录"
            create_directory_link_or_skip(self, link, outside)
            with self.assertRaisesRegex(ValueError, "Vault"):
                lint_vault(vault, checked_at=FIXED_TIME)

    def test_json_cli_returns_one_for_errors_and_two_for_bad_vault(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            (vault / "AGENTS.md").unlink()
            self.assertEqual(
                main(["--vault", str(vault), "--format", "json"]),
                1,
            )
            self.assertEqual(main(["--vault", str(vault / "missing")]), 2)


class LintLinkGraphTests(unittest.TestCase):
    def test_reports_missing_source_broken_link_orphan_and_comparison_threshold(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            knowledge = vault / "20_知识笔记/知识管理/复利知识.md"
            content = knowledge.read_text(encoding="utf-8")
            content = content.replace(
                'sources: ["[[30_精选资料/知识管理/2026年08月/来源一]]"]',
                "sources: []",
            )
            content += "\n[[不存在的目标]]\n"
            knowledge.write_text(content, encoding="utf-8")
            write(
                vault / "20_知识笔记/知识管理/孤儿.md",
                "---\ntype: 知识\ndomain: 知识管理\nstatus: 待提炼\n"
                "review_status: pending\nllm_policy: standard\n"
                "sources: [\"[[30_精选资料/知识管理/2026年08月/来源一]]\"]\n"
                "---\n\n# 孤儿\n",
            )
            write(
                vault / "20_知识笔记/知识管理/单源对比.md",
                "---\ntype: 知识\nknowledge_kind: 对比\ndomain: 知识管理\n"
                "status: 待提炼\nreview_status: pending\nllm_policy: standard\n"
                "sources: [\"[[30_精选资料/知识管理/2026年08月/来源一]]\"]\n"
                "---\n\n# 单源对比\n",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        codes = {item.code for item in report.issues}
        self.assertTrue(
            {
                "MISSING_SOURCE",
                "BROKEN_WIKILINK",
                "ORPHAN_KNOWLEDGE_NOTE",
                "INSUFFICIENT_COMPARISON_SOURCES",
            }.issubset(codes)
        )

    def test_duplicate_stem_is_reported_as_ambiguous(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            write(vault / "20_知识笔记/AI/重名.md", "# 重名一\n")
            write(vault / "20_知识笔记/Quant/重名.md", "# 重名二\n")
            note = vault / "20_知识笔记/知识管理/复利知识.md"
            note.write_text(
                note.read_text(encoding="utf-8") + "\n[[重名]]\n",
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertIn("AMBIGUOUS_WIKILINK", {item.code for item in report.issues})
