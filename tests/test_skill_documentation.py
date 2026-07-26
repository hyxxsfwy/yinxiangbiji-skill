import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


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

    def test_obsidian_templates_expose_manual_and_llm_contract(self):
        source = (
            REPO_ROOT / "templates/obsidian-source-note.md"
        ).read_text(encoding="utf-8")
        knowledge = (
            REPO_ROOT / "templates/obsidian-knowledge-note.md"
        ).read_text(encoding="utf-8")
        knowledge_map = (
            REPO_ROOT / "templates/obsidian-knowledge-map.md"
        ).read_text(encoding="utf-8")

        for field in ("type: 资料", "status: 待提炼", "source_guid:",
                      "llm_policy: strict"):
            self.assertIn(field, source)
        for field in ("type: 知识", "status: 常青", "summary:",
                      "review_status: pending", "llm_policy: standard"):
            self.assertIn(field, knowledge)
        self.assertIn("type: 索引", knowledge_map)
        self.assertIn("<!-- llmwiki:auto:start -->", knowledge_map)
        self.assertIn("<!-- llmwiki:auto:end -->", knowledge_map)

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
