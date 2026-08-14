# LLM Wiki 自维护技能优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不写入正式 Obsidian Vault、不访问真实印象笔记账号的前提下，为 `yinxiang-notes` 技能增加工具中立 Schema、Ingest/Query/Lint 操作契约和只读确定性 Lint。

**Architecture:** `SKILL.md` 只承担触发、路由和安全门禁，详细操作放入一级 reference，Vault 行为 Schema 由可部署的 `templates/obsidian-agents.md` 表达。Lint 复用现有 Vault 根目录验证、Frontmatter、Wikilink 和固定受管领域能力，输出稳定文本或 JSON 报告，不提供任何修复或写回参数。

**Tech Stack:** Python 3.12、标准库 `argparse/dataclasses/datetime/json/pathlib/re`、`unittest`、Markdown、Obsidian Wikilink、PowerShell、Git。

## Global Constraints

- 设计依据固定为 `docs/superpowers/specs/2026-08-14-llm-wiki-self-maintenance-skill-design.md`。
- 保留现有生命周期目录：`01_收件箱`、`10_项目`、`20_知识笔记`、`30_精选资料`、`80_系统`、`90_归档`、`99_废纸篓`。
- 保留固定受管十二领域：AI、Quant、信息技术、投资理财、知识管理、健康医学、中医、两性情感、个人成长、科技产业、自然科学、文史社政。
- 不创建或要求迁移到 `raw/`、`wiki/` 目录。
- 不访问真实印象笔记账号，不运行需要 Developer Token 的命令。
- 不写正式 Obsidian Vault；所有 Lint 行为测试只使用 `tests/.tmp-*` 临时 Vault。
- 原始资料正文只读；知识草稿默认 `status: 待提炼`、`review_status: pending`。
- Lint 只读：不提供 `--apply`、`--fix`、`--write-report` 或等价写回参数。
- 判断性问题只报告为 `manual_review`，不由脚本自动裁决。
- 每个任务遵循 RED-GREEN-REFACTOR；没有观察到预期失败前不得写实现。
- Git Commit 消息使用简体中文；每个任务独立提交。

---

## 文件职责与变更图

| 文件 | 责任 | 变更方式 |
| --- | --- | --- |
| `SKILL.md` | 技能发现、任务路由、安全门禁、Lint 快速命令 | 修改 |
| `references/llm-wiki-operations.md` | 三层映射与 Ingest/Query/Lint 完整操作契约 | 新建 |
| `references/obsidian-knowledge-management.md` | 现有目录、Properties、权限和审批规则的权威说明 | 修改 |
| `templates/obsidian-agents.md` | 可部署到 Vault 根目录的工具中立 Schema | 新建 |
| `templates/obsidian-comparison-note.md` | 多来源对比知识模板 | 新建 |
| `templates/obsidian-knowledge-note.md` | 普通知识笔记来源字段与待审约束 | 修改 |
| `README.md` | 面向人的三个操作入口和只读 Lint 命令 | 修改 |
| `scripts/restructure_obsidian_vault.py` | 暴露现有 Wikilink 唯一解析函数供 Lint 复用 | 小幅修改 |
| `scripts/lint_llm_wiki.py` | 只读扫描、稳定问题代码、文本/JSON CLI | 新建 |
| `tests/test_skill_documentation.py` | 文档、模板、路由和安全契约 | 修改 |
| `tests/test_vault_restructure.py` | 公共 Wikilink 解析函数的回归契约 | 修改 |
| `tests/test_llm_wiki_lint.py` | 临时 Vault 上的 Lint 行为和只读性 | 新建 |
| `docs/superpowers/skill-tests/2026-08-14-llm-wiki-baseline.md` | 未加载新规则时的失败基线 | 新建 |
| `docs/superpowers/skill-tests/2026-08-14-llm-wiki-verification.md` | 加载新技能后的前向验证证据 | 新建 |

---

### Task 1: 建立技能行为失败基线

**Files:**
- Create: `docs/superpowers/skill-tests/2026-08-14-llm-wiki-baseline.md`

**Interfaces:**
- Consumes: 当前提交 `fbd2427` 上尚未增加三大操作契约的 `SKILL.md`、现有三个 Obsidian 模板和参考文档。
- Produces: 三组无新技能指导的原始回答、逐项评分和已经观察到的失败模式；后续 Task 2、3 只能针对这些实证失败增加行为约束。

- [ ] **Step 1: 记录基线前仓库状态**

运行：

```powershell
git status --short
git rev-parse HEAD
```

预期：工作区只有本实施计划文件；HEAD 为设计提交或包含本计划的后续提交。把实际 HEAD 写入基线报告。

- [ ] **Step 2: 对 Ingest 提示运行 5 次无指导微测试**

每次使用全新上下文，不提供本仓库 `SKILL.md`、设计文档、预期答案或失败诊断，只发送下面的提示：

```text
你正在维护一个 Obsidian 知识库。用户说：“处理 30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md。”请给出你会读取哪些文件、创建或修改哪些文件、完成后如何判断成功。不要假设存在额外脚本。
```

逐次保存完整回答，按以下布尔项评分：

```text
reads_schema
reads_index_before_writing
preserves_source_body
uses_page_threshold
keeps_new_notes_pending
reports_read_and_write_sets
```

预期 RED：至少一个样本遗漏一项；如果 5 次全部满足，则删除对应拟议规则，不为不存在的失败增加约束。

- [ ] **Step 3: 对 Query 提示运行 5 次无指导微测试**

使用全新上下文发送：

```text
你正在维护一个 Obsidian 知识库。用户问：“RAG 与 LLM Wiki 的核心区别是什么？如果回答有价值就保存到知识库。”请说明读取顺序、回答如何引用证据、什么情况下保存、保存成什么状态。
```

评分项：

```text
reads_index_first
returns_to_sources_when_needed
separates_fact_view_inference_unknown
archives_only_novel_reusable_insight
requires_two_sources_or_source_plus_practice
keeps_archived_note_pending
```

预期 RED：至少一个样本无条件归档、缺少沉淀门槛或把归档内容直接标为常青。

- [ ] **Step 4: 对 Lint 提示运行 5 次无指导微测试**

使用全新上下文发送：

```text
你正在维护一个 Obsidian 知识库。用户说：“检查整个 Wiki。”请列出检查项，区分可以确定的问题和需要人工判断的问题，并说明命令是否会修改文件。
```

评分项：

```text
read_only_by_default
checks_schema_properties_sources_links_indexes
separates_deterministic_and_manual_review
does_not_auto_fix
reports_stable_issue_categories
```

预期 RED：至少一个样本混淆确定性错误与内容判断，或默认提出自动修复。

- [ ] **Step 5: 编写基线报告**

报告必须使用以下固定结构，并粘贴全部 15 个原始回答，不只写总结：

```markdown
# LLM Wiki 技能优化失败基线

## 环境

- commit: Step 1 输出的完整 40 位提交哈希
- 新规则加载状态：未加载
- 样本数：Ingest 5、Query 5、Lint 5

## Ingest

### 原始回答 1

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |

## Query

## Lint

## 观察到的失败模式

## 不需要新增规则的项目
```

`commit` 字段必须填写 Step 1 得到的真实值；表格填入 `通过` 或 `失败`。

- [ ] **Step 6: 检查报告未泄漏生产信息**

运行：

```powershell
rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" docs/superpowers/skill-tests/2026-08-14-llm-wiki-baseline.md
```

预期：无输出，`rg` 返回 1 表示未找到秘密模式。

- [ ] **Step 7: 提交失败基线**

```powershell
git add docs/superpowers/skill-tests/2026-08-14-llm-wiki-baseline.md
git diff --cached --check
git commit -m "记录 LLM Wiki 技能失败基线"
```

---

### Task 2: 用契约测试建立 Schema、操作说明和页面模板

**Files:**
- Create: `references/llm-wiki-operations.md`
- Create: `templates/obsidian-agents.md`
- Create: `templates/obsidian-comparison-note.md`
- Modify: `templates/obsidian-knowledge-note.md:1-29`
- Modify: `tests/test_skill_documentation.py:31-850`

**Interfaces:**
- Consumes: Task 1 已观察到的 Ingest/Query/Lint 失败项；`scripts/domain_taxonomy.MANAGED_DOMAINS` 的十二领域顺序；现有模板状态词。
- Produces: `self.llm_wiki_operations: str` 测试夹具、工具中立 Schema、三大操作权威 reference、带 `sources` 的知识模板和 `knowledge_kind: 对比` 模板。

- [ ] **Step 1: 在文档测试夹具中声明新 reference**

在 `SkillDocumentationTests.setUp` 的 `self.knowledge_reference` 后加入：

```python
        self.llm_wiki_operations = (
            REPO_ROOT / "references" / "llm-wiki-operations.md"
        ).read_text(encoding="utf-8")
```

- [ ] **Step 2: 写 Schema 和模板的失败测试**

在 `test_obsidian_knowledge_management_assets_exist` 的资产列表中加入：

```python
            "references/llm-wiki-operations.md",
            "templates/obsidian-agents.md",
            "templates/obsidian-comparison-note.md",
```

并新增测试：

```python
    def test_llm_wiki_schema_maps_existing_layers_and_operations(self):
        schema = (REPO_ROOT / "templates/obsidian-agents.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "30_精选资料",
            "20_知识笔记",
            "80_系统/知识库治理",
            "Ingest",
            "Query",
            "Lint",
            "一次只处理一篇",
            "原始资料正文只读",
            "status: 待提炼",
            "review_status: pending",
            "llm_policy: strict",
            "llm_policy: off",
            "人工审批",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, schema)
        self.assertNotIn("迁移到 `raw/`", schema)
        self.assertNotIn("迁移到 `wiki/`", schema)
        self.assertNotRegex(schema, r"[A-Z]:\\")

    def test_llm_wiki_operations_define_inputs_writes_and_completion(self):
        for operation in ("Ingest", "Query", "Lint"):
            with self.subTest(operation=operation):
                block = re.search(
                    rf"## {operation}\b(.*?)(?=\n## |\Z)",
                    self.llm_wiki_operations,
                    re.DOTALL,
                )
                self.assertIsNotNone(block)
                for heading in ("输入", "读取顺序", "允许产物", "禁止项", "完成条件"):
                    self.assertIn(heading, block.group(1))
        self.assertIn("manual_review", self.llm_wiki_operations)
        self.assertIn("默认只读", self.llm_wiki_operations)
        self.assertIn("不提供自动修复参数", self.llm_wiki_operations)

    def test_knowledge_and_comparison_templates_require_sources(self):
        knowledge_text = (
            REPO_ROOT / "templates/obsidian-knowledge-note.md"
        ).read_text(encoding="utf-8")
        comparison_text = (
            REPO_ROOT / "templates/obsidian-comparison-note.md"
        ).read_text(encoding="utf-8")
        knowledge = parse_frontmatter(knowledge_text)
        comparison = parse_frontmatter(comparison_text)
        self.assertEqual(knowledge["sources"], "[]")
        self.assertEqual(comparison["type"], "知识")
        self.assertEqual(comparison["knowledge_kind"], "对比")
        self.assertEqual(comparison["status"], "待提炼")
        self.assertEqual(comparison["review_status"], "pending")
        self.assertEqual(comparison["sources"], "[]")
        for heading in ("共同点", "差异与冲突", "适用条件", "待验证项"):
            self.assertIn(f"## {heading}", comparison_text)
```

- [ ] **Step 3: 运行测试并确认缺少资产导致失败**

运行：

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_obsidian_knowledge_management_assets_exist tests.test_skill_documentation.SkillDocumentationTests.test_llm_wiki_schema_maps_existing_layers_and_operations tests.test_skill_documentation.SkillDocumentationTests.test_llm_wiki_operations_define_inputs_writes_and_completion tests.test_skill_documentation.SkillDocumentationTests.test_knowledge_and_comparison_templates_require_sources -v
```

预期：FAIL 或 ERROR，明确指出 `llm-wiki-operations.md`、`obsidian-agents.md`、`obsidian-comparison-note.md` 不存在或 `sources` 缺失。

- [ ] **Step 4: 创建工具中立 Schema 模板**

`templates/obsidian-agents.md` 使用以下完整章节骨架；每节填入设计文档中的确定规则，不加入设备路径：

```markdown
# LLM Wiki 维护规则

## 目标与分工

用户负责资料选择、探索方向、提问和高风险审批。LLM 负责摘要、证据定位、交叉引用、索引建议和一致性检查。

## 目录职责

- `30_精选资料`：事实来源层，原始资料正文只读。
- `20_知识笔记`：受控知识层，新笔记保持 `status: 待提炼` 与 `review_status: pending`。
- `80_系统/知识库治理`：规则、审核队列、审核日志和审计报告。

## Ingest

一次只处理一篇明确资料。先读本文件、完整原文、对应索引和相关知识，再提出待审产物。

## Query

先读索引和知识地图，沿链接核对知识页，必要时回到原始资料。只有新增、可复用且有充分证据的洞察才建议沉淀。

## Lint

默认只读。确定性结构问题与 `manual_review` 内容判断分开报告，不自动修复。

## Properties 与建页门槛

概念至少需要两个独立来源；对比至少需要两个来源。新知识不得直接提升为常青。

## 权限矩阵

`llm_policy: strict` 只允许提出建议；`llm_policy: off` 禁止 AI 处理。人工保护区只能人工修改。

## 日志与审核

记录输入、读取范围、建议写集、实际写集、审核状态和问题数量。

## 禁止操作

未经人工审批，不删除、移动、重命名、合并文件，不创建永久标签，不改写人工结论。

## 完成门禁

所有结论可追溯，链接目标唯一，待审状态正确，变更清单明确，未修改原始正文和人工保护区。
```

- [ ] **Step 5: 创建三大操作 reference**

`references/llm-wiki-operations.md` 必须按以下顺序编写：

```markdown
# LLM Wiki 三层架构与操作契约

## 职责映射

## Ingest

### 输入
### 读取顺序
### 建页门槛
### 允许产物
### 禁止项
### 完成条件

## Query

### 输入
### 读取顺序
### 回答契约
### 沉淀门槛
### 允许产物
### 禁止项
### 完成条件

## Lint

### 输入
### 读取顺序
### 确定性检查
### manual_review
### 允许产物
### 禁止项
### 完成条件

## 操作日志

## 常见错误
```

内容逐项复制设计文档第 4、6、7、8 节已经批准的规则。Lint 的禁止项必须逐字包含“默认只读”和“不提供自动修复参数”。

- [ ] **Step 6: 更新知识模板并创建对比模板**

在 `templates/obsidian-knowledge-note.md` 的 `aliases` 后加入：

```yaml
sources: []
```

创建 `templates/obsidian-comparison-note.md`：

```markdown
---
type: 知识
knowledge_kind: 对比
domain:
status: 待提炼
created: {{date}}
updated: {{date}}
tags: []
uid:
summary:
aliases: []
sources: []
review_status: pending
reviewed_by:
reviewed_at:
llm_policy: standard
---

# {{title}}

## 比较问题

## 共同点

## 差异与冲突

## 适用条件

## 待验证项

## 参考资料
```

- [ ] **Step 7: 运行文档契约测试并确认通过**

运行 Step 3 的同一命令。

预期：4 项测试全部 PASS。

- [ ] **Step 8: 提交 Schema、reference 和模板**

```powershell
git add tests/test_skill_documentation.py references/llm-wiki-operations.md templates/obsidian-agents.md templates/obsidian-comparison-note.md templates/obsidian-knowledge-note.md
git diff --cached --check
git commit -m "建立 LLM Wiki Schema 与操作契约"
```

---

### Task 3: 把三大操作接入技能路由和知识管理规则

**Files:**
- Modify: `SKILL.md:1-20,45-80`
- Modify: `references/obsidian-knowledge-management.md:1-12,115-146`
- Modify: `README.md:182-230`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Consumes: Task 2 的 `references/llm-wiki-operations.md` 和两个新增模板。
- Produces: 可通过自然语言触发 Ingest/Query/Lint 的技能入口、现有治理 reference 中的 Schema 部署边界、README 人工入口。

- [ ] **Step 1: 写路由和安全边界的失败测试**

在 `tests/test_skill_documentation.py` 新增：

```python
    def test_skill_routes_llm_wiki_operations_and_read_only_lint(self):
        for phrase in (
            "Ingest",
            "Query",
            "Lint",
            "references/llm-wiki-operations.md",
            "templates/obsidian-agents.md",
            "python scripts/lint_llm_wiki.py --vault",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)
        self.assertIn("Lint 只读", self.skill)
        self.assertNotIn("lint_llm_wiki.py --apply", self.skill)
        self.assertNotIn("lint_llm_wiki.py --fix", self.skill)

    def test_knowledge_reference_preserves_production_deployment_gate(self):
        for phrase in (
            "Vault 根目录 `AGENTS.md`",
            "templates/obsidian-agents.md",
            "部署到正式 Vault 前必须获得明确授权",
            "原始资料正文只读",
            "知识草稿保持待审",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.knowledge_reference)
```

- [ ] **Step 2: 运行测试并确认路由缺失**

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_skill_routes_llm_wiki_operations_and_read_only_lint tests.test_skill_documentation.SkillDocumentationTests.test_knowledge_reference_preserves_production_deployment_gate -v
```

预期：FAIL，缺少操作路由、Lint 命令和 AGENTS 部署门禁。

- [ ] **Step 3: 更新 SKILL.md 触发描述与 reference 路由**

将 frontmatter 的 description 改为只描述触发条件、不概述操作步骤：

```yaml
description: Use when a user needs 印象笔记中国版 note operations or local Obsidian governance, including export or sync, reclassify vault content, rebuild indexes, maintain links, ingest sources, query durable knowledge, or lint an LLM Wiki.
```

在详细规则列表加入：

```markdown
- LLM Wiki 三层职责、Ingest、Query、Lint 与操作日志：`references/llm-wiki-operations.md`
- 部署到 Vault 根目录的工具中立 Schema：`templates/obsidian-agents.md`
```

在快速任务路由表加入：

```markdown
| 逐篇摄取精选资料 | `references/llm-wiki-operations.md` → Ingest | 默认只读资料；知识产物保持待审 |
| 基于 Wiki 查询并选择性沉淀 | `references/llm-wiki-operations.md` → Query | 默认只读；沉淀需满足门槛并获写入授权 |
| 检查 LLM Wiki | `python scripts/lint_llm_wiki.py --vault "$env:OBSIDIAN_VAULT_PATH"` | Lint 只读本地 |
```

在写入确认区增加：

```markdown
- Ingest 和 Query 的读取、分析与写入建议不构成生产写入授权；实际写正式 Vault 前仍需用户明确授权。
- Lint 只读，不得把检查请求解释为修复授权。
```

- [ ] **Step 4: 更新知识管理 reference**

在核心原则后新增“Schema 与操作层”，明确：

```markdown
## Schema 与操作层

Vault 根目录 `AGENTS.md` 是工具中立的行为 Schema，仓库权威模板为 `templates/obsidian-agents.md`。它映射现有生命周期目录，不创建第二套 `raw/` 或 `wiki/`。部署到正式 Vault 前必须获得明确授权。

日常维护使用 Ingest、Query、Lint 三个操作，完整输入、读取顺序、产物、禁止项和完成条件见 `references/llm-wiki-operations.md`。原始资料正文只读；知识草稿保持待审；Lint 默认只读。
```

在“索引、链接与审核”中加入操作日志固定位置与字段：

```markdown
操作日志固定为 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`，只追加时间、操作类型、输入、读取范围、建议写集、实际写集、审核状态和问题数量。
```

- [ ] **Step 5: 更新 README 人工入口**

在“统一 LLM Wiki 结构”后增加：

````markdown
### LLM Wiki 三大操作

- Ingest：一次处理一篇 `30_精选资料`，产出保持待审。
- Query：先读索引和知识地图，只有新增且可复用的洞察才建议沉淀。
- Lint：只读检查 Schema、Properties、来源、链接、孤儿页、索引、自动区和日志。

```powershell
python scripts/lint_llm_wiki.py --vault "D:\OneDrive\文档\@_Obsidian"
python scripts/lint_llm_wiki.py --vault "D:\OneDrive\文档\@_Obsidian" --format json
```

命令只读，不自动修复；正式 Vault 的 Ingest、Query 或 Schema 部署仍需明确写入授权。
````

- [ ] **Step 6: 运行路由测试和完整文档测试**

```powershell
python -m unittest tests.test_skill_documentation -v
```

预期：全部 PASS；不得出现旧目录、模板或十二领域契约回归。

- [ ] **Step 7: 提交技能路由**

```powershell
git add SKILL.md references/obsidian-knowledge-management.md README.md tests/test_skill_documentation.py
git diff --cached --check
git commit -m "接入 LLM Wiki 三大操作路由"
```

---

### Task 4: 实现只读 Lint 报告核心和基础结构检查

**Files:**
- Create: `scripts/lint_llm_wiki.py`
- Create: `tests/test_llm_wiki_lint.py`

**Interfaces:**
- Consumes: `scripts.runtime.load_vault_root(explicit=None, env_path=None) -> Path`、`scripts.domain_taxonomy.MANAGED_DOMAINS`、`scripts.restructure_obsidian_vault.split_frontmatter(markdown) -> tuple[dict[str, object], str]`。
- Produces: `LintIssue`、`LintReport`、`lint_vault(vault: Path, *, checked_at: datetime | None = None) -> LintReport`、`main(argv: list[str] | None = None) -> int`。

- [ ] **Step 1: 创建合法临时 Vault 测试夹具**

在 `tests/test_llm_wiki_lint.py` 写入导入和帮助函数：

```python
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
```

- [ ] **Step 2: 写基础报告和结构检查的失败测试**

```python
class LintCoreTests(unittest.TestCase):
    def test_minimal_vault_has_no_basic_structure_errors(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            report = lint_vault(vault, checked_at=FIXED_TIME)
        self.assertTrue(report.ok)
        self.assertEqual(report.to_dict()["checked_at"], "2026-08-14T08:00:00+00:00")

    def test_missing_schema_and_invalid_properties_have_stable_codes(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            (vault / "AGENTS.md").unlink()
            note = vault / "20_知识笔记/知识管理/复利知识.md"
            note.write_text(
                note.read_text(encoding="utf-8").replace(
                    "domain: 知识管理", "domain: 未知领域"
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
        self.assertIn("INVALID_FRONTMATTER", {item.code for item in report.issues})
        self.assertGreater(report.checked_files, 1)

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
```

- [ ] **Step 3: 运行测试并确认模块不存在**

```powershell
python -m unittest tests.test_llm_wiki_lint.LintCoreTests -v
```

预期：ERROR，`ModuleNotFoundError: No module named 'scripts.lint_llm_wiki'`。

- [ ] **Step 4: 实现报告类型、允许值和基础扫描**

创建 `scripts/lint_llm_wiki.py`，先实现以下最小骨架：

```python
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scripts.domain_taxonomy import MANAGED_DOMAINS
from scripts.restructure_obsidian_vault import split_frontmatter
from scripts.runtime import load_vault_root
from scripts.vault_state import require_path_within_vault


REQUIRED_PATHS = (
    Path("AGENTS.md"),
    Path("20_知识笔记"),
    Path("30_精选资料"),
    Path("80_系统/知识库治理"),
)
ALLOWED_TYPES = {"资料", "知识", "索引", "模板"}
ALLOWED_STATUS = {"待提炼", "常青"}
ALLOWED_REVIEW_STATUS = {"pending", "human-approved"}
ALLOWED_LLM_POLICY = {"standard", "strict", "off"}


@dataclass(frozen=True)
class LintIssue:
    code: str
    severity: str
    path: str
    detail: str
    fixable: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "detail": self.detail,
            "fixable": self.fixable,
        }


@dataclass(frozen=True)
class LintReport:
    vault: Path
    checked_at: datetime
    checked_files: int
    issues: tuple[LintIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.issues)

    def to_dict(self) -> dict[str, object]:
        counts = {"error": 0, "warning": 0, "manual_review": 0}
        for item in self.issues:
            counts[item.severity] += 1
        return {
            "ok": self.ok,
            "vault": str(self.vault),
            "checked_at": self.checked_at.isoformat(),
            "checked_files": self.checked_files,
            "summary": counts,
            "issues": [item.to_dict() for item in self.issues],
        }


def _relative(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def _managed_documents(vault: Path) -> tuple[Path, ...]:
    roots = (vault / "20_知识笔记", vault / "30_精选资料")
    documents = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            resolved = require_path_within_vault(
                path,
                vault,
                "Lint 扫描文件",
                allowed_root=root,
            )
            if resolved.is_file():
                documents.append(resolved)
    return tuple(sorted(set(documents)))


def lint_vault(
    vault: Path,
    *,
    checked_at: datetime | None = None,
) -> LintReport:
    vault = load_vault_root(explicit=vault)
    issues: list[LintIssue] = []
    for required in REQUIRED_PATHS:
        target = vault / required
        is_schema = required == Path("AGENTS.md")
        valid = target.is_file() if is_schema else target.is_dir()
        if not valid:
            code = "MISSING_SCHEMA" if is_schema else "MISSING_REQUIRED_DIRECTORY"
            issues.append(LintIssue(code, "error", required.as_posix(), "必需路径不存在"))
    documents = _managed_documents(vault)
    allowed_values = {
        "type": ALLOWED_TYPES,
        "domain": set(MANAGED_DOMAINS),
        "status": ALLOWED_STATUS,
        "review_status": ALLOWED_REVIEW_STATUS,
        "llm_policy": ALLOWED_LLM_POLICY,
    }
    for path in documents:
        try:
            fields, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            if not fields:
                raise ValueError("缺少 Frontmatter")
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(
                LintIssue("INVALID_FRONTMATTER", "error", _relative(vault, path), str(exc))
            )
            continue
        for name, values in allowed_values.items():
            value = fields.get(name, "")
            if name == "domain" and fields.get("type") == "索引" and not value:
                continue
            if value not in values:
                issues.append(
                    LintIssue(
                        "INVALID_PROPERTY_VALUE",
                        "error",
                        _relative(vault, path),
                        f"{name}={value!r} 不在允许值中",
                    )
                )
    return LintReport(
        vault=vault,
        checked_at=checked_at or datetime.now(timezone.utc),
        checked_files=len(documents),
        issues=tuple(issues),
    )
```

为避免一行过长，把 `code = ...` 在实际文件中拆成普通 `if/else`，确保 `git diff --check` 和代码可读性。

- [ ] **Step 5: 运行核心测试并修正最小实现**

```powershell
python -m unittest tests.test_llm_wiki_lint.LintCoreTests -v
```

预期：5 项 PASS。若合法夹具因后续尚未实现的检查失败，不得提前加入那些检查。

- [ ] **Step 6: 增加 CLI 参数和退出码失败测试**

```python
    def test_json_cli_returns_one_for_errors_and_two_for_bad_vault(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            (vault / "AGENTS.md").unlink()
            self.assertEqual(main(["--vault", str(vault), "--format", "json"]), 1)
            self.assertEqual(main(["--vault", str(vault / "missing")]), 2)
```

先运行该测试，预期 FAIL，`main` 尚未定义或不接受参数。

- [ ] **Step 7: 实现 CLI**

在 `scripts/lint_llm_wiki.py` 末尾加入：

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读检查 Obsidian LLM Wiki")
    parser.add_argument("--vault")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def _render_text(report: LintReport) -> str:
    lines = [
        f"ok: {str(report.ok).lower()}",
        f"checked_files: {report.checked_files}",
    ]
    lines.extend(
        f"[{item.severity}] {item.code} {item.path}: {item.detail}"
        for item in report.issues
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = lint_vault(load_vault_root(explicit=args.vault))
    except (OSError, ValueError) as exc:
        print(f"配置错误: {exc}")
        return 2
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: 运行 Task 4 测试并提交**

```powershell
python -m unittest tests.test_llm_wiki_lint.LintCoreTests -v
git add scripts/lint_llm_wiki.py tests/test_llm_wiki_lint.py
git diff --cached --check
git commit -m "实现 LLM Wiki 只读检查核心"
```

---

### Task 5: 复用 Wikilink 解析并检查来源、断链、歧义、孤儿和对比门槛

**Files:**
- Modify: `scripts/restructure_obsidian_vault.py:275-339`
- Modify: `tests/test_vault_restructure.py:516-663`
- Modify: `scripts/lint_llm_wiki.py`
- Modify: `tests/test_llm_wiki_lint.py`

**Interfaces:**
- Consumes: Task 4 的 `LintReport` 和基础文档扫描。
- Produces: `resolve_wikilink(vault: Path, source: Path, target: str) -> tuple[Path | None, str | None]` 公共纯函数；Lint 问题代码 `MISSING_SOURCE`、`BROKEN_WIKILINK`、`AMBIGUOUS_WIKILINK`、`ORPHAN_KNOWLEDGE_NOTE`、`INSUFFICIENT_COMPARISON_SOURCES`。

- [ ] **Step 1: 为公共解析函数写回归测试**

在 `tests/test_vault_restructure.py` 的 `LinkValidationTests` 中新增：

```python
    def test_public_resolver_returns_unique_target_and_ambiguity(self):
        from scripts.restructure_obsidian_vault import resolve_wikilink

        with workspace_temp_dir() as root:
            vault = root / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            source = vault / "20_知识笔记/AI/入口.md"
            source.parent.mkdir(parents=True)
            source.write_text("# 入口\n", encoding="utf-8")
            unique = vault / "30_精选资料/AI/唯一.md"
            unique.parent.mkdir(parents=True)
            unique.write_text("# 唯一\n", encoding="utf-8")
            resolved, reason = resolve_wikilink(vault, source, "唯一")
            self.assertEqual(resolved, unique)
            self.assertIsNone(reason)
            duplicate = vault / "20_知识笔记/Quant/唯一.md"
            duplicate.parent.mkdir(parents=True)
            duplicate.write_text(
                "# 重名\n",
                encoding="utf-8",
            )
            resolved, reason = resolve_wikilink(vault, source, "唯一")
            self.assertIsNone(resolved)
            self.assertEqual(reason, "目标不唯一")
```

沿用该测试文件在测试方法内部导入被测函数的现有风格。

- [ ] **Step 2: 运行解析测试并确认公开函数缺失**

```powershell
python -m unittest tests.test_vault_restructure.LinkValidationTests.test_public_resolver_returns_unique_target_and_ambiguity -v
```

预期：FAIL，模块没有 `resolve_wikilink`。

- [ ] **Step 3: 将私有解析函数提升为公共纯函数**

在 `scripts/restructure_obsidian_vault.py`：

```python
def resolve_wikilink(
    vault: Path,
    source: Path,
    target: str,
) -> tuple[Path | None, str | None]:
```

函数体保持原 `_resolve_wikilink` 完全一致；把 `scan_local_links` 的调用从 `_resolve_wikilink` 改为 `resolve_wikilink`。运行现有 `LinkValidationTests`，确认所有边界、代码块、URL 编码和歧义行为不变。

- [ ] **Step 4: 写 Lint 链接图失败测试**

在 `tests/test_llm_wiki_lint.py` 新增：

```python
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
```

- [ ] **Step 5: 运行 Lint 链接测试并确认问题代码缺失**

```powershell
python -m unittest tests.test_llm_wiki_lint.LintLinkGraphTests -v
```

预期：FAIL，报告尚未包含上述代码。

- [ ] **Step 6: 实现来源和链接图扫描**

在 `scripts/lint_llm_wiki.py` 导入：

```python
from scripts.restructure_obsidian_vault import (
    iter_markdown_references,
    resolve_wikilink,
    split_frontmatter,
)
```

增加以下帮助函数：

```python
def _frontmatter_source_targets(fields: dict[str, object]) -> tuple[str, ...]:
    value = fields.get("sources", [])
    if not isinstance(value, list):
        return ()
    targets = []
    for item in value:
        if not isinstance(item, str):
            continue
        match = re.fullmatch(r"\[\[(.+?)\]\]", item.strip())
        if match:
            targets.append(match.group(1))
    return tuple(targets)


def _body_wikilink_targets(markdown: str) -> tuple[str, ...]:
    return tuple(
        reference.target
        for reference in iter_markdown_references(markdown)
        if reference.is_wikilink and not reference.is_image
    )


def _normalized_wikilink_target(raw: str) -> str:
    without_alias = raw.split("|", 1)[0].strip()
    return re.split(r"[#^]", without_alias, maxsplit=1)[0].strip()
```

在 `lint_vault` 中缓存每个文档的 `(fields, markdown)`，解析 frontmatter `sources` 和正文 Wikilink。调用 `resolve_wikilink`：

- `reason == "目标不唯一"` 生成 `AMBIGUOUS_WIKILINK/error`；
- 其他 `reason` 生成 `BROKEN_WIKILINK/error`；
- 知识笔记无有效且位于 `30_精选资料` 的 source 生成 `MISSING_SOURCE/error`；
- `knowledge_kind: 对比` 的唯一有效来源少于 2 生成 `INSUFFICIENT_COMPARISON_SOURCES/error`；
- 将所有成功解析的正文链接目标加入 `inbound_paths`；非索引、非知识地图的知识笔记不在 `inbound_paths` 时生成 `ORPHAN_KNOWLEDGE_NOTE/warning`。

为 `re` 增加标准库导入。不要把 frontmatter `sources` 算作知识页的入链；它表达证据，不表达其他页面对该知识页的引用。

- [ ] **Step 7: 运行链接和现有重组测试**

```powershell
python -m unittest tests.test_llm_wiki_lint.LintLinkGraphTests tests.test_vault_restructure.LinkValidationTests -v
```

预期：全部 PASS。

- [ ] **Step 8: 提交链接与来源检查**

```powershell
git add scripts/restructure_obsidian_vault.py scripts/lint_llm_wiki.py tests/test_vault_restructure.py tests/test_llm_wiki_lint.py
git diff --cached --check
git commit -m "检查 LLM Wiki 来源与链接图"
```

---

### Task 6: 检查自动区、索引和操作日志，并证明 CLI 只读

**Files:**
- Modify: `scripts/lint_llm_wiki.py`
- Modify: `tests/test_llm_wiki_lint.py`

**Interfaces:**
- Consumes: Task 5 的解析缓存、成功解析链接集合和 `LintReport`。
- Produces: `INVALID_AUTO_REGION`、`INDEX_DRIFT`、`INVALID_LOG_ENTRY`，完整文本/JSON 输出和文件哈希不变证明。

- [ ] **Step 1: 写自动区、索引和日志失败测试**

```python
class LintConsistencyTests(unittest.TestCase):
    def test_reports_auto_region_index_drift_and_invalid_log(self):
        with workspace_temp_dir() as root:
            vault = seed_minimal_vault(root)
            knowledge_map = vault / "20_知识笔记/知识地图.md"
            knowledge_map.write_text(
                knowledge_map.read_text(encoding="utf-8").replace(
                    "<!-- llmwiki:auto:end -->", ""
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
            {"INVALID_AUTO_REGION", "INDEX_DRIFT", "INVALID_LOG_ENTRY"}.issubset(codes)
        )
```

- [ ] **Step 2: 写只读性和 JSON 输出测试**

```python
def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
```

- [ ] **Step 3: 运行测试并确认三个检查尚未实现**

```powershell
python -m unittest tests.test_llm_wiki_lint.LintConsistencyTests tests.test_llm_wiki_lint.LintReadOnlyTests -v
```

预期：一致性测试 FAIL；只读性和 JSON 测试应 PASS。若只读性失败，先删除意外写入逻辑，再继续。

- [ ] **Step 4: 实现自动区检查**

增加常量和函数：

```python
AUTO_START = "<!-- llmwiki:auto:start -->"
AUTO_END = "<!-- llmwiki:auto:end -->"


def _auto_region_valid(markdown: str) -> bool:
    return (
        markdown.count(AUTO_START) == 1
        and markdown.count(AUTO_END) == 1
        and markdown.index(AUTO_START) < markdown.index(AUTO_END)
    )
```

只对 `20_知识笔记/知识地图.md` 执行；失败生成 `INVALID_AUTO_REGION/error`。

- [ ] **Step 5: 实现索引漂移检查**

实现：

```python
def _indexed_targets(
    vault: Path,
    index_path: Path,
    markdown: str,
) -> set[Path]:
    targets = set()
    for raw in _body_wikilink_targets(markdown):
        target, reason = resolve_wikilink(
            vault,
            index_path,
            _normalized_wikilink_target(raw),
        )
        if target is not None and reason is None:
            targets.add(target)
    return targets
```

比较范围：

- `20_知识笔记/目录索引.md` 应完整收录 `20_知识笔记` 下所有 `type: 知识` 文件；
- `30_精选资料/<领域>/目录索引.md` 应完整收录该领域目录下所有 `type: 资料` 文件；
- 索引遗漏或收录错误层级文件均生成 `INDEX_DRIFT/error`，detail 列出排序后的相对路径；
- `知识地图.md` 是选择性入口，不参与完整性比较。

- [ ] **Step 6: 实现日志格式检查**

增加：

```python
LOG_ENTRY_RE = re.compile(
    r"(?m)^## \[(?P<timestamp>[^\]]+)\] (?P<operation>ingest|query|lint)$"
)
LOG_REQUIRED_FIELDS = (
    "input",
    "read_scope",
    "proposed_writes",
    "actual_writes",
    "review_status",
    "issues",
)
```

扫描固定日志路径：

1. 缺少日志文件生成 `INVALID_LOG_ENTRY/warning`；
2. 每个二级标题必须匹配 `LOG_ENTRY_RE`；
3. 标题到下一个标题之间必须包含全部 `- <field>:`；
4. 时间戳必须可由 `datetime.fromisoformat` 解析；
5. 条目按文件顺序不得倒序；
6. 任一失败生成 `INVALID_LOG_ENTRY/warning`，不修改日志。

- [ ] **Step 7: 运行 Lint 全部测试**

```powershell
python -m unittest tests.test_llm_wiki_lint -v
```

预期：全部 PASS，合法临时 Vault `summary.error == 0`，运行前后文件哈希一致。

- [ ] **Step 8: 验证 CLI 帮助中不存在写回参数**

```powershell
python scripts/lint_llm_wiki.py --help
python scripts/lint_llm_wiki.py --help | Select-String -Pattern '--apply|--fix|--write'
```

预期：第一条仅显示 `--vault` 和 `--format`；第二条无输出。

- [ ] **Step 9: 提交完整 Lint**

```powershell
git add scripts/lint_llm_wiki.py tests/test_llm_wiki_lint.py
git diff --cached --check
git commit -m "完善 LLM Wiki 一致性检查"
```

---

### Task 7: 前向验证技能行为并完成全量验收

**Files:**
- Create: `docs/superpowers/skill-tests/2026-08-14-llm-wiki-verification.md`
- Modify only if validation exposes an observed defect: `SKILL.md`, `references/llm-wiki-operations.md`, `templates/obsidian-agents.md`, `scripts/lint_llm_wiki.py`, related tests

**Interfaces:**
- Consumes: Task 1 的 15 个基线样本和评分表；Task 2-6 的已实现技能资产。
- Produces: 同提示、同评分项的 15 个加载技能样本，基线与新版本对照，完整测试与技能格式验证证据。

- [ ] **Step 1: 使用新技能重跑 Ingest 5 次**

每个新上下文仅提供：

```text
Use $yinxiang-notes at D:\_WenChao\Dev\yinxiang-notes to solve this request:
处理 30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md。请给出你会读取哪些文件、创建或修改哪些文件、完成后如何判断成功。不要执行真实 Vault 写入。
```

使用 Task 1 完全相同的 6 个评分项。每个样本必须全部通过；失败时记录原文，只针对真实失败修改最小规则，并先补契约测试。

- [ ] **Step 2: 使用新技能重跑 Query 5 次**

```text
Use $yinxiang-notes at D:\_WenChao\Dev\yinxiang-notes to solve this request:
基于知识库回答“RAG 与 LLM Wiki 的核心区别是什么？如果回答有价值就保存到知识库。”请说明读取顺序、回答如何引用证据、什么情况下保存、保存成什么状态。不要执行真实 Vault 写入。
```

使用 Task 1 完全相同的 6 个评分项；每个样本必须全部通过。

- [ ] **Step 3: 使用新技能重跑 Lint 5 次**

```text
Use $yinxiang-notes at D:\_WenChao\Dev\yinxiang-notes to solve this request:
检查整个 Wiki。请列出检查项，区分可以确定的问题和需要人工判断的问题，并说明命令是否会修改文件。不要访问真实 Vault，只说明执行方案。
```

使用 Task 1 完全相同的 5 个评分项；每个样本必须全部通过。

- [ ] **Step 4: 编写前向验证报告**

使用与基线报告相同的章节，增加：

```markdown
## 基线与新版本对照

| 操作 | 基线通过率 | 新版本通过率 | 结论 |
| --- | ---: | ---: | --- |
| Ingest | 实际值 | 实际值 | 通过或失败 |
| Query | 实际值 | 实际值 | 通过或失败 |
| Lint | 实际值 | 实际值 | 通过或失败 |

## 新出现的失败与最小修正

## 未泄漏的上下文

- 未向测试代理提供预期答案。
- 未提供基线诊断或设计结论。
- 每次运行使用全新上下文。
```

粘贴 15 个完整新回答和逐项评分，不只保留汇总。

- [ ] **Step 5: 运行针对性测试**

```powershell
python -m unittest tests.test_skill_documentation tests.test_llm_wiki_lint tests.test_vault_restructure.LinkValidationTests -v
```

预期：全部 PASS。

- [ ] **Step 6: 运行完整测试套件**

```powershell
python -m unittest discover -s tests -v
```

预期：全部 PASS，无 ERROR、FAIL 或意外跳过。

- [ ] **Step 7: 验证技能格式**

```powershell
$env:PYTHONUTF8='1'
python "C:\Users\HYXX\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .
```

预期：技能 frontmatter、名称和目录结构验证通过。

- [ ] **Step 8: 运行秘密模式和差异检查**

```powershell
rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" SKILL.md README.md references templates docs/superpowers/skill-tests scripts/lint_llm_wiki.py
git diff --check
git status --short
```

预期：秘密模式无匹配；`git diff --check` 无输出；`git status --short` 只显示本任务尚未提交的验证报告或最小修正。

- [ ] **Step 9: 提交前向验证和最小修正**

```powershell
git add SKILL.md README.md references templates scripts/lint_llm_wiki.py tests docs/superpowers/skill-tests/2026-08-14-llm-wiki-verification.md
git diff --cached --check
git commit -m "验证 LLM Wiki 自维护技能"
```

- [ ] **Step 10: 最终只读验收**

```powershell
git status --short
git log -8 --oneline --decorate
```

预期：工作区干净；日志包含七个中文任务提交；没有运行生产 Vault Lint、真实账号命令或任何生产写入。
