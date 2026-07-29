import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests.support import workspace_temp_dir


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

    def test_keyword_union_workflow_is_documented(self):
        migration_contract = (
            "旧目录 `婚姻情感` 迁移前必须先快照；若同路径目标存在且内容不同，"
            "立即中止迁移，不覆盖、删除或替换任一方内容；仅 SHA-256 完全一致时才可去除旧副本。"
        )
        for text in (self.skill, self.readme):
            for phrase in (
                "selection_mode",
                "keyword_union",
                "keyword_analyses",
                "HuggingFace",
                "pulled == total",
                "2026-04-01",
                "2026-01-01-to-2026-04-01-keyword-union.json",
                "两性情感",
                "不得继续创建 `婚姻情感`",
                "旧目录 `婚姻情感`",
                "不保存完整正文",
                "退出码 75",
                "退出码 1",
                "同一命令续跑",
                "禁止把中文 JSON",
                "keyword-union-export-job.json",
                "先快照",
                "无覆盖迁移",
                "重建索引",
                "删除空目录",
            ):
                with self.subTest(document=text[:20], phrase=phrase):
                    self.assertIn(phrase, text)
            with self.subTest(document=text[:20], contract="旧目录无覆盖迁移"):
                self.assertIn(migration_contract, text)

    def test_keyword_union_template_contains_every_requested_keyword(self):
        payload = json.loads(
            (
                REPO_ROOT
                / "templates"
                / "keyword-union-export-job.json"
            ).read_text(encoding="utf-8")
        )
        expected = {
            "软件工程", "项目管理", "AI", "人工智能", "机器学习",
            "深度学习", "强化学习", "大模型", "本体", "ontology",
            "LLM", "GPT", "RAG", "Agent", "MCP", "Skills", "Harness",
            "Anthropic", "OpenAI", "Claude", "Codex", "WorkBuddy",
            "DeepSeek", "Qwen", "千问", "GLM", "Kimi", "MiniMax",
            "HugginFace", "Transformer", "Attention", "RWKV", "RLHF",
            "Engineering", "图文生成", "扩散模型", "量化", "量化交易",
            "Quant", "金融", "理财", "定投", "基金", "贷款", "ETF",
            "区块链", "比特币", "BTC", "以太坊", "ETH", "SOL", "GTD",
            "PKM", "中医", "健康", "医学", "医生", "疾控", "婚姻",
            "幸福", "两性", "情感", "心理",
        }
        actual = {
            keyword
            for settings in payload["domains"].values()
            for keyword in settings["keywords"]
        }

        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 63)
        self.assertEqual(
            list(payload["domains"]),
            ["软件工程", "AI", "Quant", "投资理财", "知识管理", "健康医学", "两性情感"],
        )
        self.assertEqual(payload["since"], "2026-01-01")
        self.assertEqual(payload["until"], "2026-04-01")

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

    def test_documents_full_body_domain_gate_before_any_file_write(self):
        reference = (
            REPO_ROOT / "references" / "obsidian-knowledge-management.md"
        ).read_text(encoding="utf-8")
        combined = self.skill + self.readme + reference

        for phrase in (
            "搜索关键词只用于产生候选",
            "完整正文",
            "正文主旨",
            "不写入 Markdown 或附件",
            "无法确定",
        ):
            self.assertIn(phrase, combined)

        skill_gate = self.skill.split("## 搜索并导出", 1)[1].split(
            "## Obsidian 精选知识管理",
            1,
        )[0]
        fetch_position = skill_gate.index("拉取完整正文")
        assess_position = skill_gate.index("判断正文主旨")
        write_position = skill_gate.index("写入 Markdown 和附件")
        self.assertLess(fetch_position, assess_position)
        self.assertLess(assess_position, write_position)
        self.assertIn("通过正文门禁后再按完全一致标题去重", skill_gate)
        self.assertIn("最后应用 `--limit`", skill_gate)

    def test_large_multi_domain_exports_use_orchestrated_verified_workflow(self):
        combined = self.skill + self.readme
        for phrase in (
            "两个及以上领域",
            "export_multi_domain.py",
            "SQLite",
            "<vault>/.state/yinxiang-notes/export-catalog.sqlite3",
            "GUID + updated + 规则指纹",
            "更改检索关键词",
            "唯一主领域",
            "全局标题去重",
            "body_requests_saved",
            "跨领域重复",
            "完整性验收",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

        self.assertIn(
            "不得用多领域标签代替唯一主领域",
            self.skill,
        )
        self.assertIn(
            "索引、附件、检索范围对账和重复项全部通过",
            self.skill,
        )

        template = json.loads(
            (
                REPO_ROOT
                / "templates"
                / "multi-domain-export-job.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(template["since"], "2026-04-01")
        self.assertEqual(template["until"], "2026-07-01")
        self.assertGreaterEqual(len(template["domains"]), 2)

    def test_device_local_vault_and_synced_state_contract(self):
        design = (
            REPO_ROOT
            / "docs"
            / "superpowers"
            / "specs"
            / "2026-07-28-vault-scoped-runtime-state-design.md"
        ).read_text(encoding="utf-8")
        environment = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        template = json.loads(
            (
                REPO_ROOT
                / "templates"
                / "multi-domain-export-job.json"
            ).read_text(encoding="utf-8")
        )
        combined = self.skill + self.readme + design

        self.assertRegex(
            environment,
            r"(?m)^OBSIDIAN_VAULT_PATH=D:\\OneDrive\\文档\\@_Obsidian$",
        )
        self.assertRegex(
            environment,
            r"(?m)^YINXIANG_SYNC_VAULT_PATH="
            r"D:\\OneDrive\\文档\\@_Obsidian_全量同步暂存$",
        )
        self.assertNotEqual(
            re.search(
                r"(?m)^OBSIDIAN_VAULT_PATH=(.+)$",
                environment,
            ).group(1),
            re.search(
                r"(?m)^YINXIANG_SYNC_VAULT_PATH=(.+)$",
                environment,
            ).group(1),
        )
        self.assertNotIn("vault", template)

        for phrase in (
            "`OBSIDIAN_VAULT_PATH` 是每台设备的正式 Vault 根目录",
            "`YINXIANG_SYNC_VAULT_PATH` 是独立的全量同步暂存目录",
            "<vault>/.state/yinxiang-notes/export-catalog.sqlite3",
            "<vault>/.state/yinxiang-notes/jobs/",
            "<vault>/.state/yinxiang-notes/runs/",
            "<vault>/.state/yinxiang-notes/reports/",
            "<vault>/.state/yinxiang-notes/single-domain/",
            "<vault>/.state/yinxiang-notes/migrations/",
            "<vault>/.state/yinxiang-notes/active-run.lock",
            "任务 JSON 不保存 `vault`",
            "旧字段会被忽略",
            "复制旧状态，不删除旧状态",
            "禁止两台设备同时写入同一个 Vault",
            "等待上一台设备完成 Vault 同步",
            "Token 和 `.env` 不随 Vault 同步",
            '$vault = python -c "from scripts.runtime import load_vault_root; '
            'print(load_vault_root())"',
            '"$vault\\.state\\yinxiang-notes\\jobs\\2026-q2.json"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)

        for stale_phrase in (
            "--catalog \".state\\export-catalog.sqlite3\"",
            "New-Item -ItemType Directory -Force .state\\jobs",
            "SQLite 历史解析目录默认位于 `.state/export-catalog.sqlite3`",
            "限流等待、断点和报告保存在 `.state/`",
        ):
            with self.subTest(stale_phrase=stale_phrase):
                self.assertNotIn(stale_phrase, self.skill + self.readme)

        powershell_examples = "\n".join(
            re.findall(
                r"```powershell\n(.*?)\n```",
                self.skill + self.readme,
                re.DOTALL,
            )
        )
        self.assertNotIn(
            r"D:\OneDrive\文档\@_Obsidian",
            powershell_examples,
        )

    def test_powershell_examples_load_dotenv_through_runtime_contract(self):
        reference = (
            REPO_ROOT / "references" / "obsidian-knowledge-management.md"
        ).read_text(encoding="utf-8")
        legacy_design = (
            REPO_ROOT
            / "docs"
            / "superpowers"
            / "specs"
            / "2026-07-28-large-scale-multi-domain-export-design.md"
        ).read_text(encoding="utf-8")
        legacy_plan = (
            REPO_ROOT
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-07-28-large-scale-multi-domain-export.md"
        ).read_text(encoding="utf-8")
        active_documents = self.skill + self.readme + reference
        runtime_loader = (
            '$vault = python -c "from scripts.runtime import load_vault_root; '
            'print(load_vault_root())"'
        )

        for document_name, document in (
            ("README", self.readme),
            ("SKILL", self.skill),
        ):
            with self.subTest(document=document_name):
                self.assertIn(runtime_loader, document)
                self.assertNotIn("$env:OBSIDIAN_VAULT_PATH", document)
                self.assertNotIn("$env:YINXIANG_SYNC_VAULT_PATH", document)
                self.assertIn(
                    "PowerShell 不会自动把 `.env` 注入 `$env:`",
                    document,
                )

        with workspace_temp_dir() as root:
            (root / "scripts").mkdir()
            shutil.copy2(REPO_ROOT / "scripts" / "runtime.py", root / "scripts")
            vault = root / "formal-vault"
            (vault / ".obsidian").mkdir(parents=True)
            (root / ".env").write_text(
                f"OBSIDIAN_VAULT_PATH={vault}\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.pop("OBSIDIAN_VAULT_PATH", None)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from scripts.runtime import load_vault_root; "
                    "print(load_vault_root())",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), vault.resolve())

        sync_blocks = [
            block
            for document in (self.readme, self.skill)
            for block in re.findall(r"```powershell\n(.*?)\n```", document, re.DOTALL)
            if "scripts/sync_to_obsidian.py" in block
        ]
        self.assertGreaterEqual(len(sync_blocks), 1)
        for block in sync_blocks:
            with self.subTest(block=block):
                self.assertNotIn("--vault", block)
                self.assertNotIn("$syncVault", block)

        self.assertIn(
            "`OBSIDIAN_VAULT_PATH` 是正式 Vault 根目录",
            reference,
        )
        self.assertIn(
            "`YINXIANG_SYNC_VAULT_PATH` 是独立的全量同步暂存目录",
            reference,
        )
        self.assertNotIn(
            "`OBSIDIAN_VAULT_PATH` 应指向独立的全量同步暂存目录",
            active_documents,
        )
        self.assertIn("已废弃", legacy_design[:500])
        self.assertIn("已废弃", legacy_plan[:500])
        self.assertIn(
            "2026-07-28-vault-scoped-runtime-state-design.md",
            legacy_design[:500],
        )
        self.assertIn(
            "2026-07-28-vault-scoped-runtime-state-design.md",
            legacy_plan[:500],
        )

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
            + (
                REPO_ROOT
                / "templates"
                / "multi-domain-export-job.json"
            ).read_text(encoding="utf-8")
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

        self.assertIn("80_系统/知识库治理/", reference)
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
                "80_系统/",
                "90_归档/",
                "99_废纸篓/",
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
        self.assertIn(
            "旧 `90_系统`和`99_归档`由重组脚本自动迁移",
            reference,
        )
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
                "| 预览 vault 重组 | `python scripts/restructure_obsidian_vault.py` | 只读本地 |",
                "| 执行 vault 重组 | `python scripts/restructure_obsidian_vault.py --apply --confirm MIGRATE_OBSIDIAN_VAULT` | 修改本地 vault |",
                "| 验证 vault 结构 | `python scripts/restructure_obsidian_vault.py --verify` | 只读本地 |",
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
                'python scripts/restructure_obsidian_vault.py --vault "$vault"',
                'python scripts/restructure_obsidian_vault.py --vault "$vault" --apply --confirm MIGRATE_OBSIDIAN_VAULT',
                'python scripts/restructure_obsidian_vault.py --vault "$vault" --verify',
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
        self.assertIn(
            '$vault = python -c "from scripts.runtime import load_vault_root; '
            'print(load_vault_root())"',
            export_block,
        )
        self.assertIn('--target "$vault\\30_精选资料\\AI"', export_block)

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
                    '$vault = python -c "from scripts.runtime import load_vault_root; '
                    'print(load_vault_root())"',
                    block,
                )
                self.assertIn(
                    r'--target "$vault\30_精选资料\AI"',
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
        self.assertEqual(vault_path, r"D:\OneDrive\文档\@_Obsidian")
        self.assertNotRegex(vault_path, r"30_精选资料|20_知识笔记|_attachments")
        sync_path = re.search(
            r"(?m)^YINXIANG_SYNC_VAULT_PATH=(.+)$", environment
        ).group(1)
        self.assertEqual(
            sync_path,
            r"D:\OneDrive\文档\@_Obsidian_全量同步暂存",
        )
        self.assertNotEqual(sync_path, vault_path)
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
            "export_multi_domain.py",
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
