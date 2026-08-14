import hashlib
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from scripts.lint_llm_wiki import LintReport, lint_vault, main
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


def issue_facts(
    report: LintReport,
    codes: set[str],
) -> list[tuple[str, str, str]]:
    return [
        (item.path, item.code, item.severity)
        for item in report.issues
        if item.code in codes
    ]


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
                vault / "20_知识笔记/知识管理/00-损坏.md",
                "---\ninvalid yaml line\n---\n# 损坏\n",
            )
            write(
                vault / "20_知识笔记/知识管理/99-后续问题.md",
                "---\ntype: 知识\ndomain: 未知领域\nstatus: 待提炼\n"
                "review_status: pending\nllm_policy: standard\n---\n\n# 后续问题\n",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertIn(
            ("20_知识笔记/知识管理/00-损坏.md", "INVALID_FRONTMATTER"),
            [(item.path, item.code) for item in report.issues],
        )
        self.assertIn(
            (
                "20_知识笔记/知识管理/99-后续问题.md",
                "INVALID_PROPERTY_VALUE",
            ),
            [(item.path, item.code) for item in report.issues],
        )

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
            index = vault / "20_知识笔记/目录索引.md"
            index.write_text(
                index.read_text(encoding="utf-8")
                + "\n[[知识管理/00-array]]\n[[知识管理/99-after]]\n",
                encoding="utf-8",
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

    def test_json_main_returns_zero_and_emits_parseable_report_for_valid_vault(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                return_code = main(["--vault", str(vault), "--format", "json"])
        self.assertEqual(return_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["error"], 0)


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
        checked_codes = {
            "MISSING_SOURCE",
            "BROKEN_WIKILINK",
            "ORPHAN_KNOWLEDGE_NOTE",
            "INSUFFICIENT_COMPARISON_SOURCES",
        }
        self.assertEqual(
            sorted(issue_facts(report, checked_codes)),
            sorted(
                [
                    (
                        "20_知识笔记/知识管理/复利知识.md",
                        "MISSING_SOURCE",
                        "error",
                    ),
                    (
                        "20_知识笔记/知识管理/复利知识.md",
                        "BROKEN_WIKILINK",
                        "error",
                    ),
                    (
                        "20_知识笔记/知识管理/孤儿.md",
                        "ORPHAN_KNOWLEDGE_NOTE",
                        "warning",
                    ),
                    (
                        "20_知识笔记/知识管理/单源对比.md",
                        "INSUFFICIENT_COMPARISON_SOURCES",
                        "error",
                    ),
                    (
                        "20_知识笔记/知识管理/单源对比.md",
                        "ORPHAN_KNOWLEDGE_NOTE",
                        "warning",
                    ),
                ]
            ),
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
        self.assertEqual(
            issue_facts(
                report,
                {"AMBIGUOUS_WIKILINK", "BROKEN_WIKILINK"},
            ),
            [
                (
                    "20_知识笔记/知识管理/复利知识.md",
                    "AMBIGUOUS_WIKILINK",
                    "error",
                )
            ],
        )

    def test_duplicate_alias_and_anchor_sources_count_as_one_source(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            note = vault / "20_知识笔记/知识管理/复利知识.md"
            content = note.read_text(encoding="utf-8")
            content = content.replace(
                "type: 知识\n",
                "type: 知识\nknowledge_kind: 对比\n",
            ).replace(
                'sources: ["[[30_精选资料/知识管理/2026年08月/来源一]]"]',
                'sources: ["[[30_精选资料/知识管理/2026年08月/来源一]]", '
                '"[[30_精选资料/知识管理/2026年08月/来源一|别名]]", '
                '"[[30_精选资料/知识管理/2026年08月/来源一#章节]]"]',
            )
            note.write_text(content, encoding="utf-8")
            report = lint_vault(vault, checked_at=FIXED_TIME)
        checked_codes = {
            "MISSING_SOURCE",
            "BROKEN_WIKILINK",
            "AMBIGUOUS_WIKILINK",
            "INSUFFICIENT_COMPARISON_SOURCES",
        }
        self.assertEqual(
            issue_facts(report, checked_codes),
            [
                (
                    "20_知识笔记/知识管理/复利知识.md",
                    "INSUFFICIENT_COMPARISON_SOURCES",
                    "error",
                )
            ],
        )

    def test_knowledge_note_source_is_not_a_valid_selected_source(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            note = vault / "20_知识笔记/知识管理/复利知识.md"
            note.write_text(
                note.read_text(encoding="utf-8").replace(
                    'sources: ["[[30_精选资料/知识管理/2026年08月/来源一]]"]',
                    'sources: ["[[20_知识笔记/知识管理/复利知识]]"]',
                ),
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        checked_codes = {
            "MISSING_SOURCE",
            "BROKEN_WIKILINK",
            "AMBIGUOUS_WIKILINK",
        }
        self.assertEqual(
            issue_facts(report, checked_codes),
            [
                (
                    "20_知识笔记/知识管理/复利知识.md",
                    "MISSING_SOURCE",
                    "error",
                )
            ],
        )

    def test_two_distinct_selected_sources_satisfy_comparison_threshold(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            note = vault / "20_知识笔记/知识管理/复利知识.md"
            content = note.read_text(encoding="utf-8")
            content = content.replace(
                "type: 知识\n",
                "type: 知识\nknowledge_kind: 对比\n",
            ).replace(
                'sources: ["[[30_精选资料/知识管理/2026年08月/来源一]]"]',
                'sources: ["[[30_精选资料/知识管理/2026年08月/来源一]]", '
                '"[[30_精选资料/知识管理/2026年08月/来源二]]"]',
            )
            note.write_text(content, encoding="utf-8")
            report = lint_vault(vault, checked_at=FIXED_TIME)
        checked_codes = {
            "MISSING_SOURCE",
            "BROKEN_WIKILINK",
            "AMBIGUOUS_WIKILINK",
            "INSUFFICIENT_COMPARISON_SOURCES",
        }
        self.assertEqual(
            issue_facts(report, checked_codes),
            [],
        )

    def test_sources_do_not_form_inbound_links_but_body_wikilinks_do(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            target = vault / "20_知识笔记/知识管理/仅来源引用.md"
            write(
                target,
                "---\ntype: 知识\ndomain: 知识管理\nstatus: 待提炼\n"
                "review_status: pending\nllm_policy: standard\n"
                "sources: [\"[[30_精选资料/知识管理/2026年08月/来源一]]\"]\n"
                "---\n\n# 仅来源引用\n",
            )
            index = vault / "20_知识笔记/目录索引.md"
            index.write_text(
                index.read_text(encoding="utf-8").replace(
                    "llm_policy: standard\n---",
                    "llm_policy: standard\n"
                    'sources: ["[[知识管理/仅来源引用]]"]\n---',
                ),
                encoding="utf-8",
            )
            sources_only = lint_vault(vault, checked_at=FIXED_TIME)
            index.write_text(
                index.read_text(encoding="utf-8")
                + "\n[[知识管理/仅来源引用]]\n",
                encoding="utf-8",
            )
            with_body_link = lint_vault(vault, checked_at=FIXED_TIME)
        checked_codes = {
            "BROKEN_WIKILINK",
            "AMBIGUOUS_WIKILINK",
            "ORPHAN_KNOWLEDGE_NOTE",
        }
        self.assertEqual(
            issue_facts(sources_only, checked_codes),
            [
                (
                    "20_知识笔记/知识管理/仅来源引用.md",
                    "ORPHAN_KNOWLEDGE_NOTE",
                    "warning",
                )
            ],
        )
        self.assertEqual(
            issue_facts(with_body_link, checked_codes),
            [],
        )


class LintConsistencyTests(unittest.TestCase):
    def test_reports_auto_region_index_drift_and_invalid_log(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            knowledge_map = vault / "20_知识笔记/知识地图.md"
            knowledge_map.write_text(
                knowledge_map.read_text(encoding="utf-8").replace(
                    "<!-- llmwiki:auto:end -->",
                    "",
                ),
                encoding="utf-8",
            )
            write(
                vault / "20_知识笔记/知识管理/未索引.md",
                "---\ntype: 知识\ndomain: 知识管理\nstatus: 待提炼\n"
                "review_status: pending\nllm_policy: standard\n"
                "sources: [\"[[30_精选资料/知识管理/2026年08月/来源一]]\"]\n"
                "---\n\n# 未索引\n",
            )
            log = vault / "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md"
            log.write_text("# LLM Wiki 操作日志\n\n## 非法条目\n", encoding="utf-8")
            report = lint_vault(vault, checked_at=FIXED_TIME)
        codes = {item.code for item in report.issues}
        self.assertTrue(
            {"INVALID_AUTO_REGION", "INDEX_DRIFT", "INVALID_LOG_ENTRY"}.issubset(
                codes
            )
        )

    def test_auto_region_rejects_duplicate_or_reversed_markers(self):
        malformed_regions = {
            "重复 start": (
                "<!-- llmwiki:auto:start -->\n"
                "<!-- llmwiki:auto:start -->\n"
                "[[知识管理/复利知识]]\n"
                "<!-- llmwiki:auto:end -->\n"
            ),
            "重复 end": (
                "<!-- llmwiki:auto:start -->\n"
                "[[知识管理/复利知识]]\n"
                "<!-- llmwiki:auto:end -->\n"
                "<!-- llmwiki:auto:end -->\n"
            ),
            "end 在 start 之前": (
                "<!-- llmwiki:auto:end -->\n"
                "[[知识管理/复利知识]]\n"
                "<!-- llmwiki:auto:start -->\n"
            ),
        }
        for case, region in malformed_regions.items():
            with self.subTest(case=case), workspace_temp_dir() as root:
                vault = seed_minimal_vault(root)
                knowledge_map = vault / "20_知识笔记/知识地图.md"
                knowledge_map.write_text(
                    "---\ntype: 索引\ndomain: \nstatus: 常青\n"
                    "review_status: human-approved\nllm_policy: standard\n---\n\n"
                    "# 知识地图\n\n"
                    + region,
                    encoding="utf-8",
                )
                report = lint_vault(vault, checked_at=FIXED_TIME)
            self.assertIn(
                "INVALID_AUTO_REGION",
                {item.code for item in report.issues},
            )

    def test_knowledge_index_drift_detail_is_sorted_and_map_is_selective(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            source = vault / "30_精选资料/知识管理/2026年08月/来源一.md"
            for name in ("乙笔记", "甲笔记"):
                write(
                    vault / f"20_知识笔记/知识管理/{name}.md",
                    "---\ntype: 知识\ndomain: 知识管理\nstatus: 待提炼\n"
                    "review_status: pending\nllm_policy: standard\n"
                    "sources: [\"[[30_精选资料/知识管理/2026年08月/来源一]]\"]\n"
                    f"---\n\n# {name}\n",
                )
            index = vault / "20_知识笔记/目录索引.md"
            index.write_text(
                index.read_text(encoding="utf-8")
                + "\n[[30_精选资料/知识管理/2026年08月/来源一]]\n",
                encoding="utf-8",
            )
            knowledge_map = vault / "20_知识笔记/知识地图.md"
            knowledge_map.write_text(
                knowledge_map.read_text(encoding="utf-8").replace(
                    "<!-- llmwiki:auto:end -->",
                    "[[知识管理/甲笔记]]\n<!-- llmwiki:auto:end -->",
                ),
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        drift = [
            item
            for item in report.issues
            if item.code == "INDEX_DRIFT" and item.path == "20_知识笔记/目录索引.md"
        ]
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0].severity, "error")
        self.assertEqual(
            drift[0].detail,
            "遗漏: 20_知识笔记/知识管理/乙笔记.md, 20_知识笔记/知识管理/甲笔记.md; "
            f"越界: {source.relative_to(vault).as_posix()}",
        )

    def test_selected_domain_index_reports_missing_and_wrong_level_targets(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            write(
                vault / "30_精选资料/知识管理/2026年08月/补充来源.md",
                "---\ntype: 资料\ndomain: 知识管理\nstatus: 待提炼\n"
                "review_status: pending\nllm_policy: strict\n---\n\n# 补充来源\n",
            )
            index = vault / "30_精选资料/知识管理/目录索引.md"
            index.write_text(
                index.read_text(encoding="utf-8")
                + "\n[[20_知识笔记/知识管理/复利知识]]\n",
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        drift = [
            item
            for item in report.issues
            if item.code == "INDEX_DRIFT"
            and item.path == "30_精选资料/知识管理/目录索引.md"
        ]
        self.assertEqual(len(drift), 1)
        self.assertEqual(
            drift[0].detail,
            "遗漏: 30_精选资料/知识管理/2026年08月/补充来源.md; "
            "越界: 20_知识笔记/知识管理/复利知识.md",
        )

    def test_missing_log_is_a_warning(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            log = vault / "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md"
            log.unlink()
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertEqual(
            issue_facts(report, {"INVALID_LOG_ENTRY"}),
            [
                (
                    "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md",
                    "INVALID_LOG_ENTRY",
                    "warning",
                )
            ],
        )
        self.assertTrue(report.ok)

    def test_log_format_fields_timestamp_and_order_are_warnings(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            log = vault / "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md"
            log.write_text(
                "# LLM Wiki 操作日志\n\n"
                "##\n"
                "- input: bad title\n\n"
                "## [不是时间] query\n"
                "- input: malformed timestamp\n"
                "- read_scope: all\n"
                "- proposed_writes: []\n"
                "- actual_writes: []\n"
                "- review_status: pending\n"
                "- issues: 1\n\n"
                "## [2026-08-15T08:00:00+00:00] lint\n"
                "- input: first\n"
                "- read_scope: all\n"
                "- proposed_writes: []\n"
                "- actual_writes: []\n"
                "- review_status: pending\n"
                "- issues: 0\n\n"
                "## [2026-08-14T08:00:00+00:00] ingest\n"
                "- input: second\n",
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        warnings = [
            item for item in report.issues if item.code == "INVALID_LOG_ENTRY"
        ]
        self.assertGreaterEqual(len(warnings), 4)
        self.assertEqual({item.severity for item in warnings}, {"warning"})
        details = "\n".join(item.detail for item in warnings)
        for expected in ("标题格式", "时间戳", "缺少字段", "时间顺序"):
            self.assertIn(expected, details)

    def test_log_mixed_timezone_entries_warn_instead_of_aborting(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            log = vault / "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md"
            fields = (
                "- input: sample\n"
                "- read_scope: all\n"
                "- proposed_writes: []\n"
                "- actual_writes: []\n"
                "- review_status: pending\n"
                "- issues: 0\n"
            )
            log.write_text(
                "# LLM Wiki 操作日志\n\n"
                "## [2026-08-14T08:00:00+00:00] lint\n"
                f"{fields}\n"
                "## [2026-08-14T09:00:00] query\n"
                f"{fields}",
                encoding="utf-8",
            )
            try:
                report = lint_vault(vault, checked_at=FIXED_TIME)
            except TypeError as exc:
                self.fail(f"混合时区日志不应中止扫描: {exc}")
        details = "\n".join(
            item.detail
            for item in report.issues
            if item.code == "INVALID_LOG_ENTRY"
        )
        self.assertIn("时区不一致", details)

    def test_log_different_utc_offsets_warn_instead_of_aborting(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            log = vault / "80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md"
            fields = (
                "- input: sample\n"
                "- read_scope: all\n"
                "- proposed_writes: []\n"
                "- actual_writes: []\n"
                "- review_status: pending\n"
                "- issues: 0\n"
            )
            log.write_text(
                "# LLM Wiki 操作日志\n\n"
                "## [2026-08-14T08:00:00+00:00] lint\n"
                f"{fields}\n"
                "## [2026-08-14T17:00:00+08:00] query\n"
                f"{fields}",
                encoding="utf-8",
            )
            report = lint_vault(vault, checked_at=FIXED_TIME)
        warnings = [
            item
            for item in report.issues
            if item.code == "INVALID_LOG_ENTRY"
        ]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "warning")
        self.assertIn("时区不一致", warnings[0].detail)


class LintReadOnlyTests(unittest.TestCase):
    def test_lint_does_not_change_any_vault_file(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            before = tree_hashes(vault)
            lint_vault(vault, checked_at=FIXED_TIME)
            after = tree_hashes(vault)
        self.assertEqual(after, before)

    def test_report_dictionary_is_json_serializable(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            payload = lint_vault(vault, checked_at=FIXED_TIME).to_dict()
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(json.loads(rendered)["summary"]["error"], 0)

    def test_script_help_exposes_only_read_only_options(self):
        repository = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/lint_llm_wiki.py", "--help"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--vault", completed.stdout)
        self.assertIn("--format", completed.stdout)
        for forbidden in ("--apply", "--fix", "--write"):
            self.assertNotIn(forbidden, completed.stdout)
