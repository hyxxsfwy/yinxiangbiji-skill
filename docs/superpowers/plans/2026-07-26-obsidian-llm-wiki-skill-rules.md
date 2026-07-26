# Obsidian 精选知识库与 LLM Wiki Skill 规则实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已经确认的 Obsidian 精选迁移、双层知识结构、轻量 Properties、受控主题标签和 LLM Wiki 半自动审核规则写入当前 `yinxiang-notes` Skill，并提供可直接使用的模板。

**Architecture:** `SKILL.md` 只保留执行时必须遵守的决策规则和安全边界；详细目录、迁移、维护和 LLM Wiki 说明放入独立参考文档；三个 Markdown 模板分别承载精选资料、知识笔记和知识地图的固定结构。现有文档测试扩展为资产与规则契约测试，不修改印象笔记 API、导出器或真实 Obsidian vault。

**Tech Stack:** Markdown、Obsidian Properties、Obsidian 内部链接与 Bases 约定、Python 3.12 `unittest`、Git。

## Global Constraints

- 使用简体中文编写文档和 Git Commit 消息。
- 历史剪藏继续留在印象笔记；禁止把 49,259 篇历史笔记全量复刻到 Obsidian。
- Obsidian 只按需迁移值得继续使用的内容；满足五项迁移条件中的至少两项才迁移。
- 精选资料和知识笔记必须分层；当前真实知识库位置和现有导出目标保持不变。
- 人工核心字段固定为 `type`、`domain`、`status`、`tags`。
- `type` 允许 `资料`、`知识`、`索引`、`模板`；`status` 允许 `待处理`、`待提炼`、`常青`、`归档`。
- 标签只表达主题，每篇最多 3 个；默认结构为 `主题/<主题名>`，至少预计 3 篇复用后才创建永久标签。
- 原始资料正文只读；AI 不得自动删除、移动、重命名、合并或改写人工结论。
- LLM Wiki 低风险自动审批必须经过白名单、证据、受控词表、链接消歧、独立审核、确定性校验、日志和可回滚检查。
- 本计划只修改 `SKILL.md`、`references/`、`templates/` 和 `tests/test_skill_documentation.py`。
- 保留并不提交现有 `.gitignore`、`scripts/sync_to_obsidian.py`、`tests/test_export_search_results.py` 等无关工作区改动。
- 不创建或修改真实 Obsidian 目录，不调用真实账户写 API。

---

### Task 1: 建立 Obsidian 参考文档和模板契约

**Files:**
- Create: `references/obsidian-knowledge-management.md`
- Create: `templates/obsidian-source-note.md`
- Create: `templates/obsidian-knowledge-note.md`
- Create: `templates/obsidian-knowledge-map.md`
- Modify: `tests/test_skill_documentation.py`
- Reference: `docs/superpowers/specs/2026-07-26-obsidian-llm-wiki-knowledge-management-design.md`

**Interfaces:**
- Consumes: 已批准设计中的目录、Properties、标签、迁移和 LLM Wiki 审核规则。
- Produces: 三个可直接用于 Obsidian 的模板，以及供 `SKILL.md` 引用的详细知识管理参考。

- [ ] **Step 1: 为新增资产写失败测试**

在 `SkillDocumentationTests` 中增加：

```python
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
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_obsidian_knowledge_management_assets_exist -v
```

Expected: FAIL，指出 `references/obsidian-knowledge-management.md` 或模板文件不存在。

- [ ] **Step 3: 创建精选资料模板**

创建 `templates/obsidian-source-note.md`，完整内容为：

```markdown
---
type: 资料
domain:
status: 待提炼
created: {{date}}
source:
source_guid:
source_url:
tags: []
review_status: pending
llm_policy: strict
---

# {{title}}

> [!summary] 保留价值
> 用一两句话说明为什么值得保留。

## 摘要

## 关键内容

## 关联知识

## 原始来源
```

- [ ] **Step 4: 创建知识笔记模板**

创建 `templates/obsidian-knowledge-note.md`，完整内容为：

```markdown
---
type: 知识
domain:
status: 常青
created: {{date}}
updated: {{date}}
tags: []
uid:
summary:
aliases: []
review_status: pending
reviewed_by:
reviewed_at:
llm_policy: standard
---

# {{title}}

## 核心结论

## 依据与推导

## 相关知识

- 前置知识：
- 相关方法：
- 使用示例：
- 对比观点：

## 参考资料
```

- [ ] **Step 5: 创建知识地图模板**

创建 `templates/obsidian-knowledge-map.md`，完整内容为：

```markdown
---
type: 索引
domain:
status: 常青
created: {{date}}
updated: {{date}}
tags: []
review_status: pending
llm_policy: strict
---

# {{title}}

## 人工精选

### 核心概念

### 实践方法

### 工具与平台

### 待继续研究

<!-- llmwiki:auto:start -->

## AI 自动维护

### 最近形成的主题

### 推荐关联

<!-- llmwiki:auto:end -->
```

- [ ] **Step 6: 创建详细参考文档**

创建 `references/obsidian-knowledge-management.md`，按以下顺序写入完整规则：

1. “适用场景与核心原则”：历史剪藏留在印象笔记，Obsidian 只存持续有用内容。
2. “目标目录”：列出 `00_首页.md`、`01_收件箱`、`10_知识库`、`20_项目`、`30_精选资料`、`90_系统`、`99_归档`。
3. “双层内容”：定义精选资料、知识笔记和项目内容的边界。
4. “迁移判定”：列出五项条件，明确至少满足两项，每周最多迁移 5 至 10 篇。
5. “Properties”：列出四个人工字段和 LLM Wiki 管理字段的允许值及状态转换。
6. “标签”：只使用受控主题标签、每篇最多 3 个、三篇复用规则、旧标签映射。
7. “首页、书签、Bases 与知识地图”：列出三个书签组、三个 Bases 和知识地图职责。
8. “维护流程”：捕获四选一、每周处理、每月维护。
9. “LLM Wiki”：原文只读、人工保护区、AI 自动区、双模型审核、风险分级、3 至 7 个高价值链接、审核资产。
10. “安全边界”：不自动删除、移动、重命名、合并、创建永久标签、改写人工结论或提升常青状态。

参考文档必须包含以下精确路径和字段，以便人工与自动化共同读取：

```text
90_系统/LLM Wiki/
├─ 审核规则.md
├─ 主题词表.md
├─ 别名词典.md
├─ 审核队列/
├─ 审核日志/
└─ 变更快照/
```

```yaml
uid:
summary:
aliases: []
review_status: pending
reviewed_by:
reviewed_at:
llm_policy: standard
```

- [ ] **Step 7: 运行资产测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_obsidian_knowledge_management_assets_exist tests.test_skill_documentation.SkillDocumentationTests.test_obsidian_templates_expose_manual_and_llm_contract -v
```

Expected: 2 tests PASS。

- [ ] **Step 8: 提交 Task 1**

```powershell
git add -- tests/test_skill_documentation.py references/obsidian-knowledge-management.md templates/obsidian-source-note.md templates/obsidian-knowledge-note.md templates/obsidian-knowledge-map.md
git diff --cached --check
git commit -m "增加 Obsidian 知识管理参考与模板"
```

### Task 2: 把精选迁移与 LLM Wiki 决策规则写入 Skill

**Files:**
- Modify: `SKILL.md`
- Modify: `tests/test_skill_documentation.py`
- Read: `references/obsidian-knowledge-management.md`

**Interfaces:**
- Consumes: Task 1 的参考文档和三个模板路径。
- Produces: 未来代理在迁移、整理或自动链接时必须遵守的紧凑 Skill 决策规则。

- [ ] **Step 1: 为 Skill 决策规则写失败测试**

在 `SkillDocumentationTests` 中增加：

```python
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
            "人工审批",
            "references/obsidian-knowledge-management.md",
            "templates/obsidian-source-note.md",
            "templates/obsidian-knowledge-note.md",
            "templates/obsidian-knowledge-map.md",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_skill_documents_curated_obsidian_and_llm_wiki_rules -v
```

Expected: FAIL，第一项缺少的规则为“历史剪藏继续保留在印象笔记”。

- [ ] **Step 3: 在 `SKILL.md` 增加精选知识管理规则**

在“搜索并导出”和“安全边界”之间增加 `## Obsidian 精选知识管理`，内容必须覆盖：

- 默认采用精选迁移，不复刻印象笔记的笔记本组、年份归档和自动采集目录；
- 历史剪藏继续保留在印象笔记；
- 五项迁移条件中至少满足两项才按需迁移；
- 精选资料进入资料层，消化后的内容进入知识层，项目材料进入项目层；
- 人工字段固定为 `type`、`domain`、`status`、`tags`；
- 标签只表达主题，每篇最多 3 个，只能使用受控主题词表；
- `_Apps` 转来源属性，任务标签转状态属性，个人状态不进入知识库；
- 详细规则和三个模板的相对路径。

使用紧凑的快速参考表，避免把完整参考文档复制进 `SKILL.md`。

- [ ] **Step 4: 在 `SKILL.md` 增加 LLM Wiki 安全边界**

紧接精选知识管理规则增加 `### LLM Wiki 半自动审核`，明确：

- 原始资料正文只读；
- AI 只能直接维护知识地图的自动区域；
- `llm_policy: strict` 只允许建议，`llm_policy: off` 禁止处理；
- 自动审批必须经过白名单、证据、受控词表、消歧、独立审核、确定性校验、日志和可回滚检查；
- 新永久标签、人工结论、合并、移动、重命名、删除和提升常青状态必须人工审批；
- 每篇知识笔记只保留 3 至 7 个有明确语义的高价值链接。

- [ ] **Step 5: 运行 Skill 规则测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_skill_documents_curated_obsidian_and_llm_wiki_rules -v
```

Expected: 1 test PASS。

- [ ] **Step 6: 运行 Skill 文档完整测试**

Run:

```powershell
python -m unittest tests.test_skill_documentation -v
```

Expected: 所有 `SkillDocumentationTests` PASS，且命令帮助测试继续返回 0。

- [ ] **Step 7: 提交 Task 2**

```powershell
git add -- SKILL.md tests/test_skill_documentation.py
git diff --cached --check
git commit -m "记录精选迁移与 LLM Wiki 审核规则"
```

### Task 3: 全量验证与范围审计

**Files:**
- Verify only: `SKILL.md`
- Verify only: `references/obsidian-knowledge-management.md`
- Verify only: `templates/obsidian-source-note.md`
- Verify only: `templates/obsidian-knowledge-note.md`
- Verify only: `templates/obsidian-knowledge-map.md`
- Verify only: `tests/test_skill_documentation.py`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的完整提交。
- Produces: 可交付的 Skill 文档、模板和验证证据；不产生新的业务行为。

- [ ] **Step 1: 运行完整测试套件**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: 全部测试 PASS。

- [ ] **Step 2: 运行 Python 编译检查**

Run:

```powershell
python -m compileall -q scripts tests
```

Expected: exit code 0。

- [ ] **Step 3: 检查 Markdown 和暂存范围**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- `git diff --check` 无输出；
- 本计划产生的文件无未提交改动；
- 只保留进入计划前已经存在的无关工作区改动；
- 不出现真实 Token、Obsidian vault 文件或导出内容。

- [ ] **Step 4: 检查设计覆盖**

Run:

```powershell
rg -n "按需迁移|每篇笔记最多 3 个标签|LLM Wiki|llm_policy|自动审批|人工审批" SKILL.md references/obsidian-knowledge-management.md
rg -n "type:|domain:|status:|tags:|llmwiki:auto" templates
```

Expected: 每项规则至少在 `SKILL.md` 或详细参考中出现，三个模板包含其适用的固定字段和自动区域标记。

- [ ] **Step 5: 报告结果**

报告：

- 新增和修改的文件；
- 测试总数与结果；
- 两个实现提交；
- 保留的无关工作区改动；
- 本阶段没有修改真实 Obsidian vault、印象笔记账户或导出目标。
