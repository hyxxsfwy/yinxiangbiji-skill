import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_frontmatter(markdown: str) -> dict[str, str]:
    """Parse the scalar fields in a Markdown document's YAML frontmatter."""
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", markdown, re.DOTALL)
    if match is None:
        raise ValueError("Markdown document must start with YAML frontmatter")

    fields = {}
    for line in match.group(1).splitlines():
        field = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):(?:\s?(.*))?", line)
        if field is None:
            raise ValueError(f"Unsupported frontmatter line: {line!r}")
        fields[field.group(1)] = (field.group(2) or "").strip()
    return fields


class SkillDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    def test_skill_frontmatter_is_discoverable(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name: yinxiang-notes$")
        self.assertRegex(frontmatter, r"(?m)^description: Use when ")

    def test_referenced_scripts_exist(self):
        references = set(
            re.findall(r"scripts/([a-z_]+\.py)", self.skill + self.readme)
        )
        self.assertGreaterEqual(len(references), 10)
        for script_name in references:
            with self.subTest(script=script_name):
                self.assertTrue((REPO_ROOT / "scripts" / script_name).is_file())

    def test_documents_current_paths_and_safety_flags(self):
        combined = self.skill + self.readme
        self.assertNotIn(r"C:\Users\adun", combined)
        self.assertNotIn("skills/yinxiang-notes", combined)
        self.assertIn("--vault", combined)
        self.assertIn("--max-results", combined)
        self.assertIn("--confirm DELETE_ALL", combined)
        self.assertIn("export_search_results.py", combined)

    def test_examples_do_not_contain_a_real_developer_token(self):
        combined = (
            self.skill
            + self.readme
            + (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
            + (REPO_ROOT / "references" / "obsidian-knowledge-management.md").read_text(
                encoding="utf-8"
            )
            + (REPO_ROOT / "templates" / "obsidian-source-note.md").read_text(
                encoding="utf-8"
            )
            + (REPO_ROOT / "templates" / "obsidian-knowledge-note.md").read_text(
                encoding="utf-8"
            )
            + (REPO_ROOT / "templates" / "obsidian-knowledge-map.md").read_text(
                encoding="utf-8"
            )
        )
        token_pattern = r"S=s[0-9]+:U=[0-9a-f]+:E=[0-9a-f]+:"
        self.assertIsNone(re.search(token_pattern, combined))

    def test_obsidian_knowledge_management_assets_exist(self):
        asset_paths = [
            "references/obsidian-knowledge-management.md",
            "templates/obsidian-source-note.md",
            "templates/obsidian-knowledge-note.md",
            "templates/obsidian-knowledge-map.md",
        ]
        for relative_path in asset_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((REPO_ROOT / relative_path).is_file())

    def test_obsidian_templates_enforce_lifecycle_and_automation_contract(self):
        templates = {
            path: (REPO_ROOT / path).read_text(encoding="utf-8")
            for path in (
                "templates/obsidian-source-note.md",
                "templates/obsidian-knowledge-note.md",
                "templates/obsidian-knowledge-map.md",
            )
        }
        source = parse_frontmatter(templates["templates/obsidian-source-note.md"])
        knowledge = parse_frontmatter(
            templates["templates/obsidian-knowledge-note.md"]
        )
        knowledge_map = parse_frontmatter(
            templates["templates/obsidian-knowledge-map.md"]
        )

        self.assertEqual(
            {
                key: source[key]
                for key in ("type", "status", "review_status", "llm_policy")
            },
            {
                "type": "资料",
                "status": "待提炼",
                "review_status": "pending",
                "llm_policy": "strict",
            },
        )
        self.assertEqual(
            {
                key: knowledge[key]
                for key in ("type", "status", "review_status", "llm_policy")
            },
            {
                "type": "知识",
                "status": "待提炼",
                "review_status": "pending",
                "llm_policy": "standard",
            },
        )
        self.assertFalse(
            knowledge["review_status"] == "pending"
            and knowledge["status"] == "常青",
            "待审知识草稿不得进入常青视图",
        )
        self.assertEqual(
            {
                key: knowledge_map[key]
                for key in ("type", "status", "llm_policy")
            },
            {"type": "索引", "status": "常青", "llm_policy": "standard"},
        )

        map_content = templates["templates/obsidian-knowledge-map.md"]
        auto_start = "<!-- llmwiki:auto:start -->"
        auto_end = "<!-- llmwiki:auto:end -->"
        self.assertEqual(map_content.count(auto_start), 1)
        self.assertEqual(map_content.count(auto_end), 1)
        self.assertLess(map_content.index(auto_start), map_content.index(auto_end))

    def test_knowledge_management_reference_documents_approval_contract(self):
        reference = (
            REPO_ROOT / "references/obsidian-knowledge-management.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "待审知识草稿默认 `status: 待提炼`，只有人工确认后才可提升为 `status: 常青`",
            reference,
        )
        for condition in (
            "操作在人工规则白名单中",
            "存在可定位的证据",
            "只使用已有主题词表",
            "目标链接唯一且无同名歧义",
            "生成器与独立审核模型结论一致",
            "格式、路径、链接和 Properties 校验通过",
            "变更可回滚且写入日志",
            "目标笔记不是 `strict` 或 `off`",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, reference)

        for human_review_operation in (
            "创建永久标签",
            "修改人工结论",
            "合并、移动、重命名、删除、提升常青状态",
            "修改人工精选区必须人工审批",
        ):
            with self.subTest(operation=human_review_operation):
                self.assertIn(human_review_operation, reference)

        self.assertIn("90_系统/知识库治理/", reference)
        for asset in (
            "管理规则.md",
            "主题词表.md",
            "别名词典.md",
            "审核队列/",
            "审核日志/",
            "变更快照/",
        ):
            with self.subTest(asset=asset):
                self.assertIn(asset, reference)

    def test_skill_documents_curated_obsidian_and_llm_wiki_rules(self):
        required_phrases = [
            "历史剪藏继续保留在印象笔记",
            "按需迁移",
            "至少两项",
            "`type`、`domain`、`status`、`tags`",
            "每篇笔记最多 3 个标签",
            "受控主题词表",
            "LLM Wiki",
            "`llm_policy: off`",
            "自动审批",
            "同名或多候选链接存在歧义时不得自动审批，进入人工队列",
            "人工审批",
            "references/obsidian-knowledge-management.md",
            "templates/obsidian-source-note.md",
            "templates/obsidian-knowledge-note.md",
            "templates/obsidian-knowledge-map.md",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_documents_final_vault_structure_and_migration_command(self):
        reference = (
            REPO_ROOT / "references" / "obsidian-knowledge-management.md"
        ).read_text(encoding="utf-8")
        tree = re.search(
            r"## 最终目录\n\n```text\n(.*?)\n```", reference, re.DOTALL
        ).group(1)
        top_level = re.findall(r"(?m)^[├└]── ([^\n]+)$", tree)
        self.assertEqual(
            top_level,
            [
                "00_首页.md",
                "01_收件箱/",
                "10_项目/",
                "20_知识笔记/",
                "30_精选资料/",
                "90_系统/",
                "99_归档/",
            ],
        )

        project_tree = tree.split("├── 10_项目/", 1)[1].split(
            "├── 20_知识笔记/", 1
        )[0]
        self.assertEqual(
            re.findall(r"(?m)^│   └── ([^\n]+)$", project_tree), ["目录索引.md"]
        )
        self.assertIn("暂不预建领域目录", reference)

        knowledge_tree = tree.split("├── 20_知识笔记/", 1)[1].split(
            "├── 30_精选资料/", 1
        )[0]
        knowledge_root_files = re.findall(
            r"(?m)^│   [├└]── ([^/\n]+\.md)$", knowledge_tree
        )
        self.assertEqual(knowledge_root_files, ["目录索引.md", "知识地图.md"])

        self.assertIn("整个 vault 是 LLM Wiki", reference)
        self.assertNotIn("10_知识库", reference)
        self.assertNotIn("20_项目", reference)
        self.assertNotIn("90_系统/LLM Wiki/", reference)

        self.assertEqual(
            [
                line
                for line in self.skill.splitlines()
                if "scripts/restructure_obsidian_vault.py" in line
            ],
            [
                '| 预览 vault 重组 | `python scripts/restructure_obsidian_vault.py --vault "D:\\OneDrive\\文档\\@_Obsidian"` | 只读本地 |',
                '| 执行 vault 重组 | `python scripts/restructure_obsidian_vault.py --vault "D:\\OneDrive\\文档\\@_Obsidian" --apply --confirm MIGRATE_OBSIDIAN_VAULT` | 修改本地 vault |',
                '| 验证 vault 结构 | `python scripts/restructure_obsidian_vault.py --vault "D:\\OneDrive\\文档\\@_Obsidian" --verify` | 只读本地 |',
            ],
        )

        migration_commands = [
            line.strip()
            for block in re.findall(
                r"```powershell\n(.*?)\n```",
                self.readme,
                re.DOTALL,
            )
            for line in block.splitlines()
            if "restructure_obsidian_vault.py" in line
        ]
        self.assertEqual(
            migration_commands,
            [
                'python scripts/restructure_obsidian_vault.py --vault "D:\\OneDrive\\文档\\@_Obsidian"',
                'python scripts/restructure_obsidian_vault.py --vault "D:\\OneDrive\\文档\\@_Obsidian" --apply --confirm MIGRATE_OBSIDIAN_VAULT',
                'python scripts/restructure_obsidian_vault.py --vault "D:\\OneDrive\\文档\\@_Obsidian" --verify',
            ],
        )
        preview, apply, verify = migration_commands
        self.assertNotIn("--apply", preview)
        self.assertNotIn("--confirm", preview)
        self.assertIn("--verify", verify)
        self.assertNotIn("--apply", verify)
        self.assertIn("--apply --confirm MIGRATE_OBSIDIAN_VAULT", apply)
        self.assertIn("预览和验证均只读本地 vault", reference)
        self.assertIn(
            "预览只输出路径映射，不生成清单或链接报告",
            reference,
        )

        export_block = next(
            block
            for block in re.findall(r"```powershell\n(.*?)\n```", self.readme, re.DOTALL)
            if "scripts/export_search_results.py" in block and "--domain AI" in block
        )
        self.assertIn('--target "D:\\OneDrive\\文档\\@_Obsidian\\30_精选资料\\AI"', export_block)

    def test_documents_distinct_catalog_map_and_source_index_rules(self):
        reference = (
            REPO_ROOT / "references" / "obsidian-knowledge-management.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "按 `domain` 分组",
            "可由脚本或 AI 完整重建",
            "不保存人工评语",
            "人工维护核心概念",
            "仅关键词相同不足以建立关系",
            "每个领域保留一份独立的 `目录索引.md`",
        ):
            self.assertIn(phrase, reference)

    def test_every_curated_export_example_targets_the_ai_domain_directory(self):
        export_blocks = [
            block
            for document in (self.readme, self.skill)
            for block in re.findall(r"```powershell\n(.*?)\n```", document, re.DOTALL)
            if "scripts/export_search_results.py" in block
        ]

        self.assertGreaterEqual(len(export_blocks), 3)
        for block in export_blocks:
            with self.subTest(block=block):
                self.assertIn("--domain AI", block)
                self.assertIn(
                    r'--target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"',
                    block,
                )
                self.assertNotIn(r"\AI相关知识库", block)

    def test_documents_vault_environment_and_image_safety_contract(self):
        reference = (
            REPO_ROOT / "references" / "obsidian-knowledge-management.md"
        ).read_text(encoding="utf-8")
        environment = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

        vault_path = re.search(
            r"(?m)^OBSIDIAN_VAULT_PATH=(.+)$", environment
        ).group(1)
        self.assertEqual(vault_path, r"D:\OneDrive\文档\@_Obsidian_全量同步暂存")
        self.assertNotRegex(vault_path, r"30_精选资料|20_知识笔记|_attachments")
        self.assertNotEqual(vault_path, r"D:\OneDrive\文档\@_Obsidian")
        self.assertIn("全量同步不得写入统一 LLM Wiki 根目录", reference)

        migration_section = reference.split("## 迁移与验证", 1)[1].split(
            "## 双层内容与 Properties", 1
        )[0]
        self.assertIn("30_精选资料/AI/_attachments", migration_section)
        self.assertIn("文章对图片的相对引用布局", migration_section)
        self.assertIn("验证阶段会检查这些图片引用可解析", migration_section)

        type_contract = re.search(
            r"`type` 可为 ([^。]+)。",
            reference,
        ).group(1)
        self.assertEqual(
            type_contract,
            "`资料`、`知识`、`索引` 或 `模板`",
        )

    def test_every_user_command_has_non_mutating_help(self):
        command_scripts = [
            "create_note.py",
            "delete_note.py",
            "empty_trash.py",
            "export_search_results.py",
            "get_note_enml.py",
            "list_notebooks.py",
            "list_tags.py",
            "list_trash.py",
            "search_notes.py",
            "sync_to_obsidian.py",
            "update_note.py",
        ]
        for script_name in command_scripts:
            with self.subTest(script=script_name):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts" / script_name),
                        "--help",
                    ],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(result.returncode, 0)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
