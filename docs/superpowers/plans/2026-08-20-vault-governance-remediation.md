# Obsidian Vault 治理问题整改 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复正式 Obsidian Vault 的真实治理缺口，并使 LLM Wiki、当前结构、历史迁移证据和索引完整性校验各自遵循正确边界。

**Architecture:** 共享 Markdown 引用解析器负责代码区域和 WikiLink 语法；结构验证只扫描当前内容区，历史 manifest 通过唯一文件重定位与旧 domain 别名兼容后核验。Vault 内容使用配置路径、边界检查、活动锁和 Git 基线门禁后做最小写入。

**Tech Stack:** Python 3.12、`unittest`、Obsidian Markdown、PowerShell、Git、SQLite。

**Spec:** `docs/superpowers/specs/2026-08-20-vault-governance-remediation.md`

## Global Constraints

- 使用简体中文回答、文档和 Git 提交消息。
- 不自动批量移动旧资料，不清空废纸篓，不修改 `.state/quarantine`。
- 正式 Vault 写入限定为规格列出的治理文件和链接块。
- 源码采用 TDD；先失败、再最小实现、再全量回归。

---

### Task 1: Markdown 引用解析与当前内容扫描边界

**Files:**
- Modify: `tests/test_vault_restructure.py`
- Modify: `tests/test_llm_wiki_lint.py`
- Modify: `scripts/restructure_obsidian_vault.py`
- Modify: `scripts/lint_llm_wiki.py`

**Interfaces:**
- Consumes: `iter_markdown_references(markdown)`、`scan_local_links(vault)`。
- Produces: `_normalized_wikilink_target(raw)` 对 `.md` 文件名中的 `#` 保持原义；当前 Markdown 迭代排除 `.state`/`.git`。

- [ ] **Step 1: 写失败测试**

  覆盖行内代码 `` `[[示例]]` ``、POSIX `[[:space:]]`、Python `df[['a', 'b']]`、文件名 `标题#标签.md`、`.state/quarantine` 和精选资料普通教程链接。

- [ ] **Step 2: 运行红灯测试**

  Run: `python -m unittest tests.test_vault_restructure.LinkValidationTests tests.test_llm_wiki_lint -v`

  Expected: 新测试分别暴露伪 WikiLink、`#` 截断和 `.state` 扫描问题。

- [ ] **Step 3: 最小实现**

  在共享解析器中移除行内代码并过滤明确代码式双括号；在目标归一化时只把 `.md` 之后的 `#` 当锚点；当前内容迭代入口排除 `.state`/`.git`，精选资料只严格校验图片与 WikiLink。

- [ ] **Step 4: 运行绿灯测试**

  Run: `python -m unittest tests.test_vault_restructure.LinkValidationTests tests.test_llm_wiki_lint -v`

  Expected: PASS。

### Task 2: 历史迁移记录与当前 Vault 演进解耦

**Files:**
- Modify: `tests/test_vault_restructure.py`
- Modify: `scripts/restructure_obsidian_vault.py`

**Interfaces:**
- Consumes: `load_manifest_strict(...)`、`validate_migration(...)`、`verify_completed_vault(...)`。
- Produces: 唯一 Markdown 重定位解析、`LEGACY_DOMAIN_ALIASES` 归一化、基于 manifest `link_check_result` 的历史报告核验。

- [ ] **Step 1: 写失败测试**

  覆盖旧 `软件工程` 目标、唯一同名文件跨 domain/月迁移可接受、无候选或多候选仍失败、历史链接报告继续可检测篡改。

- [ ] **Step 2: 运行红灯测试**

  Run: `python -m unittest tests.test_vault_restructure.ValidationRobustnessTests -v`

  Expected: 合法后续迁移用例 FAIL，删除/歧义保护用例保持有效。

- [ ] **Step 3: 最小实现**

  只对 Markdown manifest 目标尝试受管根目录下唯一文件名重定位；domain 旧别名统一映射；历史报告按 manifest 保存的通过状态与计数重建后比对，当前结构报告独立要求通过。

- [ ] **Step 4: 运行绿灯测试**

  Run: `python -m unittest tests.test_vault_restructure.ValidationRobustnessTests -v`

  Expected: PASS。

### Task 3: 分类审计误报收敛

**Files:**
- Modify: `tests/test_reclassify_selected_materials.py`
- Modify: `scripts/reclassify_selected_materials.py`

**Interfaces:**
- Consumes: `classify_document(title, body, current_domain)`、生产分类审计报告。
- Produces: AI 主体正文优先于“辞职/涨薪”引流标题，保留真正的职业成长迁移能力。

- [ ] **Step 1: 写失败测试并复核生产候选**

  覆盖 AI 大模型训练营、AI 项目、MCP/Skills 为主体而标题包含辞职涨薪的资料；确认旧规则产生错误候选。

- [ ] **Step 2: 最小实现与分类回归**

  仅在 AI 正文包含至少三类核心证据、正文 AI 得分显著高于个人成长正文得分且标题未命中特定领域强制规则时保留 AI；提升分类策略版本。

- [ ] **Step 3: 最终生产审计**

  Run: `python scripts/reclassify_selected_materials.py audit --vault <vault>`

  Expected: `move: 0`，原候选为 `keep: AI`。

### Task 4: 正式 Vault 最小治理写入

**Files:**
- Create: `D:\OneDrive\文档\@_Obsidian\AGENTS.md`
- Create: `D:\OneDrive\文档\@_Obsidian\80_系统\知识库治理\审核日志\LLM Wiki 操作日志.md`
- Modify: `D:\OneDrive\文档\@_Obsidian\20_知识笔记\信息技术\Codex CLI 使用技巧记录.md`
- Modify: `D:\OneDrive\文档\@_Obsidian\30_精选资料\Quant\2026年06月\GPT-6也救不了平庸策略：Vibe Quant 的反思.md`
- Modify: `D:\OneDrive\文档\@_Obsidian\30_精选资料\Quant\2026年08月\百万因子背后的工程：如何搭建生产级量化研究 Agent.md`

**Interfaces:**
- Consumes: `templates/obsidian-agents.md`、LLM Wiki frontmatter/日志/自动链接契约。
- Produces: 完整 Schema、有效 source、对称 Quant 链接、可审计治理日志。

- [ ] **Step 1: 生产写入预检**

  确认 `load_vault_root()` 等于目标路径、`.obsidian` 存在、无 `active-run.lock`、Vault Git 干净且五个目标均在允许边界内。

- [ ] **Step 2: 执行最小写入**

  安装 Schema；为知识笔记增加 Codex 精选资料 source；把 Quant 链接从 `2026年07月` 更新为 `2026年08月` 并补回链；创建一条包含六个必需字段的治理日志。

- [ ] **Step 3: 核对实际差异**

  Run: `git -c safe.directory='D:/OneDrive/文档/@_Obsidian' -C <vault> diff --check`

  Expected: 仅列出的五个 Markdown 文件有预期差异，另新增 `AGENTS.md` 和操作日志。

### Task 5: 全量验收与可恢复记录

**Files:**
- Verify only: source repository and production Vault。

**Interfaces:**
- Consumes: 前三项输出。
- Produces: 全绿验收证据与 Vault Git 本地恢复点。

- [ ] **Step 1: 运行源码定向与全量测试**

  Run: `python -m unittest discover -s tests -p "test_*.py" -v`

  Expected: 全部 PASS。

- [ ] **Step 2: 运行正式 Vault 验收**

  依次执行 LLM Wiki Lint、结构 verify、domain preview/verify、`scan_export_integrity`、分类 audit、SQLite `integrity_check` 和 Vault Git verify。

  Expected: 所有确定性 error/warning 为 0；重复项为 0；domain/index/附件为 0 问题。

- [ ] **Step 3: 创建 Vault Git 恢复点**

  仅暂存验收过的 Markdown 治理变更，提交消息使用 `修复 LLM Wiki 治理与链接问题`；不配置远端、不推送。

- [ ] **Step 4: 最终复核**

  确认 Vault Git 干净；源码仓库仅保留本任务代码、测试、规格和计划差异；执行 `git diff --check`。
