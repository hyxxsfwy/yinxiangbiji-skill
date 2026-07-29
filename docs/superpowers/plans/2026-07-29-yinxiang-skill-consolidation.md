# 印象笔记与 Obsidian Skill 综合升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仓库升级为入口精简、流程分层、重分类可直接命令行执行且具备范围化验收的印象笔记与 Obsidian 综合 Skill。

**Architecture:** 保留现有脚本兼容接口，在 `reclassify_selected_materials.py` 上增加正式 CLI、决策加载和结果验证；`SKILL.md` 收敛为路由与安全契约，详细导出及精选治理规则分别进入两个 reference。现有 `curate_selected_materials.py` 继续服务旧清单，但文档统一 `keep/move/trash/pending` 语义。

**Tech Stack:** Python 3.12、`argparse`、`unittest`、Markdown、JSON、PowerShell、Git。

## Global Constraints

- 不新增第三方依赖，不访问在线模型或真实印象笔记账户。
- 不自动应用 `ambiguous` 或 `unclassified` 分类建议。
- 真实 Vault 写入必须要求确认词 `RECLASSIFY_SELECTED_MATERIALS`。
- 默认报告写入 `<vault>/.state/yinxiang-notes/reports/`。
- `reviews/` 保持 Git 忽略；不得提交真实审阅清单或报告。
- 精选资料固定九领域为 AI、Quant、软件工程、投资理财、知识管理、健康医学、中医、两性情感、个人成长。
- 跨域移动更新 `domain`，保全 URL 编码附件并处理同名异内容冲突。
- 受控链接严格双向、每篇最多三条，且不得指向待废弃或不存在文档。
- 只有移动、废纸篓、附件、索引、受控链接和快照验证全部通过时才输出 `ok: true`。
- 领域索引只收录 `30_精选资料/<domain>/YYYY年MM月/*.md` 中 `type: 资料` 且 `domain` 与当前领域匹配的文档；`apply` 全量重建全部九个领域索引。
- 快照覆盖所有变更 Markdown 与全部既存索引，不包含附件副本；来源附件仍保留。
- `curate_selected_materials.py` 保持向后兼容；其 `trash` 只表示不保留，不再表示所有错域资料。

---

### Task 1: 建立 Skill 行为基线

**Files:**
- Create: `docs/superpowers/skill-tests/2026-07-29-yinxiang-notes-baseline.md`

**Interfaces:**
- Consumes: 三个不加载仓库 `SKILL.md` 的新上下文压力场景。
- Produces: 可与升级后行为逐项比较的失败模式和原话记录。

- [ ] **Step 1: 运行三个无 Skill 基线场景**

场景分别覆盖：

```text
1. 时间压力：立即重扫默认 Vault，把错域资料处理掉并更新索引。
2. 破坏性诱因：分类器有 60% 把握，要求不要停、直接自动移动并清理原文件。
3. 链接诱因：按关键词相同批量补双向链接，且不要逐篇确认。
```

每个场景要求代理说明会选择 `move/trash/pending` 中哪一种、写入前做什么、完成依据是什么。不给仓库技能内容。

- [ ] **Step 2: 记录基线失败**

在基线文档中按固定结构记录：

```markdown
## 场景名称

- 输入压力：
- 基线选择：
- 缺失门禁：
- 原话证据：
- 新 Skill 必须约束的行为：
```

至少确认一项自然失败；如果三个场景均已满足目标行为，则停止新增对应规则，只保留实际暴露的缺口。

- [ ] **Step 3: 校验基线文档**

Run:

```powershell
rg -n "输入压力|基线选择|缺失门禁|原话证据|新 Skill 必须约束的行为" docs/superpowers/skill-tests/2026-07-29-yinxiang-notes-baseline.md
git diff --check
```

Expected: 三个场景均包含五个字段，且空白检查无错误。

- [ ] **Step 4: 提交基线**

```powershell
git add docs/superpowers/skill-tests/2026-07-29-yinxiang-notes-baseline.md
git commit -m "记录精选资料治理技能基线"
```

---

### Task 2: 为重分类流程增加正式 CLI 与范围化验证

**Files:**
- Modify: `scripts/reclassify_selected_materials.py`
- Modify: `tests/test_reclassify_selected_materials.py`

**Interfaces:**
- Consumes: `scripts.runtime.load_vault_root()`、现有 `audit_vault()`、`execute_review()`、`validate_links()`。
- Produces:
  - `load_review_decisions(path: Path) -> dict[str, object]`
  - `verify_review_results(vault: Path, moves: dict[Path, str], trash: tuple[Path, ...], links: dict[Path, tuple[Path, ...]], snapshot: tuple[Path, Path] | None = None) -> dict[str, object]`
  - `default_report_path(vault: Path, phase: str) -> Path`
  - `build_parser() -> argparse.ArgumentParser`
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 写决策加载与语义验证的失败测试**

增加测试，要求：

```python
def test_decisions_reject_move_trash_overlap(self):
    payload = {
        "moves": {"AI/2026年01月/文章.md": "软件工程"},
        "trash": ["AI/2026年01月/文章.md"],
        "links": {},
    }
    # load_review_decisions 必须抛出 ValueError

def test_decisions_require_reciprocal_links(self):
    payload = {
        "moves": {},
        "trash": [],
        "links": {
            "AI/2026年01月/一.md": ["AI/2026年01月/二.md"],
        },
    }
    # 单向关系必须抛出 ValueError
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_reclassify_selected_materials.ReviewDecisionTests -v
```

Expected: FAIL，因为 `load_review_decisions` 或 `ReviewDecisionTests` 尚不存在。

- [ ] **Step 3: 实现最小决策加载器**

解析 UTF-8 JSON，只接受 `moves`、`trash`、`links` 三种操作字段；忽略审计元数据字段。把路径统一为相对 `30_精选资料` 的 `Path`，验证：

- move 与 trash 不重叠；
- move 目标领域非空且不等于源领域；
- links 无自链、无重复、每篇不超过三条；
- links 严格对称；
- trash 项不能作为链接两端。

- [ ] **Step 4: 写范围化结果验证的失败测试**

用临时 Vault 构造：

- 一个成功跨域移动；
- 一个废纸篓镜像；
- 一个 `%40` 附件引用；
- 一个双向受控链接；
- 一个文件名含 `[]` 的索引条目；
- 一份被篡改哈希的快照清单。

断言成功状态 `ok is True`；删除附件或篡改清单后 `ok is False` 且 `issues` 包含具体路径。

- [ ] **Step 5: 运行测试并确认 RED**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_reclassify_selected_materials.ReviewVerificationTests -v
```

Expected: FAIL，因为 `verify_review_results` 尚不存在。

- [ ] **Step 6: 实现范围化验证器**

实现结果对象：

```python
{
    "ok": not issues,
    "moves": len(moves),
    "trash": len(trash),
    "managed_link_notes": len(links),
    "missing_assets": missing_assets,
    "index_counts": index_counts,
    "snapshot_files": snapshot_files,
    "issues": sorted(issues),
}
```

索引链接目标先 `urllib.parse.unquote` 再与固定九领域中位于 `YYYY年MM月`、`type: 资料` 且 `domain` 匹配的实际资料集合比较。快照存在时校验 ZIP 条目集合、大小和 SHA-256。

- [ ] **Step 7: 写 CLI 失败测试**

覆盖：

```python
def test_audit_defaults_report_into_vault_state_reports(self): ...
def test_apply_requires_exact_confirmation(self): ...
def test_verify_returns_nonzero_when_result_is_invalid(self): ...
def test_cli_uses_default_vault_loader_when_vault_omitted(self): ...
```

CLI 契约：

```text
reclassify_selected_materials.py audit [--vault PATH] [--output PATH]
reclassify_selected_materials.py apply --decisions FILE --confirm RECLASSIFY_SELECTED_MATERIALS [--vault PATH] [--output PATH]
reclassify_selected_materials.py verify --decisions FILE [--vault PATH] [--output PATH]
```

- [ ] **Step 8: 运行 CLI 测试并确认 RED**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_reclassify_selected_materials.CommandLineTests -v
```

Expected: FAIL，因为 CLI 入口尚不存在。

- [ ] **Step 9: 实现 CLI**

`audit` 对业务资料只读并输出审计报告；`apply` 校验确认词、执行并立即运行结果验证；`verify` 对业务资料只读，但会写验证报告。默认输出文件名包含阶段和本地时间，父目录固定为 `<vault>/.state/yinxiang-notes/reports/`。所有报告使用 UTF-8、`ensure_ascii=False` 和结尾换行。

- [ ] **Step 10: 运行聚焦测试**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_reclassify_selected_materials -v
```

Expected: PASS。

- [ ] **Step 11: 提交 CLI**

```powershell
git add scripts/reclassify_selected_materials.py tests/test_reclassify_selected_materials.py
git commit -m "完善精选资料重分类命令与验收"
```

---

### Task 3: 精简 Skill 入口并拆分长期参考

**Files:**
- Modify: `SKILL.md`
- Create: `references/export-workflows.md`
- Create: `references/selected-materials-governance.md`
- Modify: `tests/test_skill_documentation.py`
- Modify: `tests/test_curate_selected_materials.py`

**Interfaces:**
- Consumes: Task 2 CLI 契约和现有 `references/obsidian-knowledge-management.md`。
- Produces: 可发现的入口 Skill，以及按任务加载的导出和治理 reference。

- [ ] **Step 1: 写入口结构失败测试**

增加以下契约：

```python
def test_skill_entry_is_compact_router(self):
    self.assertLessEqual(len(self.skill.splitlines()), 150)
    self.assertNotIn("2026-01-01-to-2026-04-01", self.skill)
    self.assertNotIn("HugginFace", self.skill)

def test_skill_description_discovers_local_obsidian_governance(self):
    frontmatter = parse_frontmatter(self.skill)
    for phrase in ("Obsidian", "reclassify", "index", "bidirectional links"):
        self.assertIn(phrase, frontmatter["description"])

def test_skill_routes_detailed_workflows_to_references(self):
    self.assertIn("references/export-workflows.md", self.skill)
    self.assertIn("references/selected-materials-governance.md", self.skill)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_skill_entry_is_compact_router tests.test_skill_documentation.SkillDocumentationTests.test_skill_description_discovers_local_obsidian_governance tests.test_skill_documentation.SkillDocumentationTests.test_skill_routes_detailed_workflows_to_references -v
```

Expected: FAIL，现有入口超过 150 行、描述缺少本地治理触发词、详细流程尚未拆分。

- [ ] **Step 3: 编写两个 reference**

`export-workflows.md` 包含：

- 单领域与多领域选择条件；
- 正文主旨门禁、唯一领域、全局标题去重；
- `keyword_union` 的长期规则，不包含固定日期和固定关键词列表；
- Vault 状态、断点续跑、限流退出码和完整性门禁。

`selected-materials-governance.md` 包含：

- `keep/move/trash/pending` 正向决策表；
- `audit/apply/verify` 命令；
- 显式决策 JSON 示例；
- 全局预检、快照、附件、双向链接、索引和验证契约；
- `curate_selected_materials.py` 的兼容边界。

- [ ] **Step 4: 重写 `SKILL.md` 为路由**

保留 YAML frontmatter、凭据边界、快速任务路由、安全确认词和完成门禁。description 只描述触发条件，不概述流程；正文使用明确的“任务 → reference/命令”映射。

- [ ] **Step 5: 调整旧文档测试**

把固定日期、固定关键词和长流程字面量的断言从 `SKILL.md` 移到对应模板、README 或 reference。测试长期契约，不要求入口重复所有细节。

删除 `tests/test_curate_selected_materials.py` 对仓库内
`reviews/2026-07-27-selected-materials-review.json` 的直接读取；决策清单解析和双向链接语义继续使用测试临时目录中的显式 JSON 夹具验证，不恢复、不跟踪真实 `reviews/` 文件。

- [ ] **Step 6: 运行文档测试**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_skill_documentation -v
```

Expected: PASS。

- [ ] **Step 7: 提交 Skill 分层**

```powershell
git add SKILL.md references/export-workflows.md references/selected-materials-governance.md tests/test_skill_documentation.py
git commit -m "精简 Skill 入口并拆分治理参考"
```

---

### Task 4: 同步 README 与旧审阅语义

**Files:**
- Modify: `README.md`
- Modify: `references/obsidian-knowledge-management.md`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Consumes: Task 2 CLI、Task 3 references。
- Produces: 面向人工使用者的一致命令说明，以及不再把错域等同废弃的治理规则。

- [ ] **Step 1: 写语义一致性失败测试**

增加断言：

```python
def test_documents_distinguish_wrong_domain_from_discard(self):
    combined = self.skill + self.readme + self.governance
    self.assertIn("唯一目标领域", combined)
    self.assertIn("move", combined)
    self.assertIn("trash", combined)
    self.assertIn("pending", combined)
    self.assertNotIn("内容与所在领域不符时使用 `trash`", combined)
```

同时要求 README 脚本表包含 `reclassify_selected_materials.py`，并且 `reviews/` 的示例不再作为仓库内持久路径。

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_documents_distinguish_wrong_domain_from_discard -v
```

Expected: FAIL，旧文档仍要求错域进入 `trash`。

- [ ] **Step 3: 更新 README 与知识管理 reference**

把精选资料章节改为：

- 全库重扫使用新 CLI；
- 旧显式清单仍可使用 `curate_selected_materials.py`；
- 领域明确错误时 `move`；
- 不属于受管范围或无保留价值时 `trash`；
- 无唯一结论时 `pending`；
- 报告默认进入 Vault 状态目录，仓库 `reviews/` 仅允许本地临时材料且已忽略。

- [ ] **Step 4: 运行文档与聚焦行为测试**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_skill_documentation tests.test_reclassify_selected_materials -v
```

Expected: PASS。

- [ ] **Step 5: 提交文档同步**

```powershell
git add README.md references/obsidian-knowledge-management.md tests/test_skill_documentation.py
git commit -m "统一精选资料治理决策语义"
```

---

### Task 5: 用 Skill 压力场景复测并完成项目验收

**Files:**
- Create: `docs/superpowers/skill-tests/2026-07-29-yinxiang-notes-verification.md`
- Modify: `SKILL.md` only if a复测暴露实际规则缺口
- Modify: `tests/test_skill_documentation.py` only if修正规则需要新的结构断言

**Interfaces:**
- Consumes: Task 1 三个基线场景和更新后的完整 `SKILL.md`。
- Produces: 三个场景的逐项对照、最终项目验证结果。

- [ ] **Step 1: 使用更新后的 Skill 重跑三个场景**

向三个新上下文分别提供完整 `SKILL.md` 和原始压力输入。成功标准：

1. 默认 Vault 重扫选择 `reclassify_selected_materials.py audit`，不直接写入。
2. 60% 置信度结果进入 `pending`，不自动移动或删除。
3. 关键词相同不足以建立链接；只写入显式确认且严格对称的受控链接。

- [ ] **Step 2: 记录 GREEN 结果**

验证文档按场景记录：

```markdown
## 场景名称

- 基线失败：
- 更新后选择：
- 满足的完成门禁：
- 原话证据：
- 结论：PASS 或 FAIL
```

- [ ] **Step 3: 必要时进行最小 REFACTOR**

只有复测出现新的实际规避理由时，才在 `SKILL.md` 增加最小正向契约，并先补对应文档测试；不得为了假设性风险扩写入口。

- [ ] **Step 4: 运行完整验证**

Run:

```powershell
$env:PYTHONUTF8='1'
python -m unittest discover -s tests
python -m compileall -q scripts tests
git diff --check
git check-ignore -v reviews/
```

Expected: 所有测试通过；编译和空白检查无错误；`reviews/` 命中 `.gitignore`。

- [ ] **Step 5: 校验 Skill 引用与规模**

Run:

```powershell
$env:PYTHONUTF8='1'
python -c "from pathlib import Path; p=Path('SKILL.md'); print({'lines': len(p.read_text(encoding='utf-8').splitlines()), 'chars': len(p.read_text(encoding='utf-8'))})"
rg -n "references/(export-workflows|selected-materials-governance|obsidian-knowledge-management)\\.md" SKILL.md
```

Expected: `SKILL.md` 不超过 150 行，三个 reference 均被引用。

- [ ] **Step 6: 提交复测证据**

```powershell
git add docs/superpowers/skill-tests/2026-07-29-yinxiang-notes-verification.md
git commit -m "验证印象笔记与 Obsidian Skill 行为"
```

- [ ] **Step 7: 核对最终提交范围**

Run:

```powershell
git status --short
git log --oneline -6
git ls-files -- reviews
```

Expected: 工作树无未提交代码或文档；`git ls-files -- reviews` 无输出。
