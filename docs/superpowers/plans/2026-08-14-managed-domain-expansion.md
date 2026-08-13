# Obsidian 固定受管领域精简扩展实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将范围统一为固定受管十二领域，把“软件工程”安全重命名为“信息技术”，并在正式 Obsidian Vault 中完成可回滚迁移和只读审计。

**Architecture:** 新增单一领域注册表，导出、重分类、脚手架和命令行只从该注册表读取领域集合。新增独立的领域迁移命令，以预览、确认写入、独立验证和事务回滚处理正式 Vault；其余旧资料只审计，不自动改域。

**Tech Stack:** Python 3.12、标准库 `argparse/pathlib/json/re/shutil`、现有 Vault 状态锁与事务模块、`unittest`、Markdown/JSON。

## Global Constraints

- 固定受管领域精确为：AI、Quant、信息技术、投资理财、知识管理、健康医学、中医、两性情感、个人成长、科技产业、自然科学、历史与社会。
- “软件工程”只作为迁移别名，不再是有效的新写入领域。
- 仅“软件工程”到“信息技术”允许自动迁移；其余既有资料只读审计，不自动移动、删除或改域。
- `20_知识笔记` 与 `30_精选资料` 必须使用相同领域集合和顺序。
- 新增领域允许为空；不得为填充目录强行迁移资料。
- 所有正式 Vault 写入必须验证路径位于 Vault 内、持有写锁、有可恢复事务，并使用确认词 `EXPAND_MANAGED_DOMAINS`。
- 保留 `SKILL.md` 中用户尚未提交的 Developer Token 预检修改，不能把该既有修改混入本任务提交。

---

## 文件职责

- 新建 `scripts/domain_taxonomy.py`：十二领域、迁移别名、分类证据词和注册表校验的唯一事实源。
- 修改 `scripts/export_search_results.py`：消费统一注册表，保留正文主旨门禁算法。
- 修改 `scripts/reclassify_selected_materials.py`：消费统一注册表，保留审计阈值与标题回退规则。
- 修改 `scripts/restructure_obsidian_vault.py`：脚手架、首页和知识索引使用十二领域。
- 新建 `scripts/migrate_domain_taxonomy.py`：正式 Vault 的预览、应用、回滚与验证。
- 修改 `templates/keyword-union-export-job.json`：按十二领域归组关键词。
- 修改 `SKILL.md`、`references/obsidian-knowledge-management.md`、`references/selected-materials-governance.md`：更新受管领域和执行边界。
- 新建 `tests/test_domain_taxonomy.py`、`tests/test_migrate_domain_taxonomy.py`，并扩展现有导出、重分类、脚手架和文档测试。

### Task 1: 建立单一领域注册表

**Files:**
- Create: `scripts/domain_taxonomy.py`
- Create: `tests/test_domain_taxonomy.py`
- Modify: `scripts/export_search_results.py`
- Modify: `scripts/reclassify_selected_materials.py`
- Modify: `scripts/restructure_obsidian_vault.py`

**Interfaces:**
- Produces: `MANAGED_DOMAINS: tuple[str, ...]`
- Produces: `LEGACY_DOMAIN_ALIASES: dict[str, str]`
- Produces: `DOMAIN_PROFILES: dict[str, dict[str, tuple[str, ...] | int]]`
- Produces: `canonical_domain(name: str, *, allow_legacy: bool = False) -> str`
- Produces: `validate_domain_registry() -> None`

- [ ] **Step 1: 写失败测试，锁定领域集合、顺序和旧名称行为**

```python
class DomainRegistryTests(unittest.TestCase):
    def test_registry_has_exact_twelve_domains(self):
        self.assertEqual(
            MANAGED_DOMAINS,
            (
                "AI", "Quant", "信息技术", "投资理财", "知识管理",
                "健康医学", "中医", "两性情感", "个人成长",
                "科技产业", "自然科学", "历史与社会",
            ),
        )

    def test_legacy_name_requires_explicit_migration_mode(self):
        with self.assertRaisesRegex(ValueError, "不支持的领域"):
            canonical_domain("软件工程")
        self.assertEqual(
            canonical_domain("软件工程", allow_legacy=True),
            "信息技术",
        )

    def test_every_domain_has_core_and_support_terms(self):
        validate_domain_registry()
        self.assertEqual(tuple(DOMAIN_PROFILES), MANAGED_DOMAINS)
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `python -m unittest tests.test_domain_taxonomy -v`

Expected: FAIL，提示 `scripts.domain_taxonomy` 不存在。

- [ ] **Step 3: 实现最小注册表和校验接口**

```python
MANAGED_DOMAINS = (
    "AI", "Quant", "信息技术", "投资理财", "知识管理",
    "健康医学", "中医", "两性情感", "个人成长",
    "科技产业", "自然科学", "历史与社会",
)
LEGACY_DOMAIN_ALIASES = {"软件工程": "信息技术"}

def canonical_domain(name, *, allow_legacy=False):
    if name in MANAGED_DOMAINS:
        return name
    if allow_legacy and name in LEGACY_DOMAIN_ALIASES:
        return LEGACY_DOMAIN_ALIASES[name]
    raise ValueError(f"不支持的领域: {name}")

def validate_domain_registry():
    if tuple(DOMAIN_PROFILES) != MANAGED_DOMAINS:
        raise ValueError("领域词表与受管领域顺序不一致")
    for name, profile in DOMAIN_PROFILES.items():
        if not profile.get("core") or not profile.get("support"):
            raise ValueError(f"领域词表不完整: {name}")
```

将两套现有词表合并进注册表，并补充“信息技术、科技产业、自然科学、历史与社会”的核心和辅助词。“区块链、BTC、ETH、SOL、TRX、USDT”保留在投资理财；网络安全、FreeBuf、数据库、容器和边缘计算并入信息技术。

- [ ] **Step 4: 让三个入口只导入统一注册表**

```python
from scripts.domain_taxonomy import DOMAIN_PROFILES, MANAGED_DOMAINS
```

删除 `export_search_results.py`、`reclassify_selected_materials.py` 和 `restructure_obsidian_vault.py` 中重复的领域集合；命令行 `choices` 改为 `MANAGED_DOMAINS`，脚手架 `DOMAINS` 改为该元组的兼容别名。

- [ ] **Step 5: 运行注册表及受影响分类测试**

Run: `python -m unittest tests.test_domain_taxonomy tests.test_export_search_results tests.test_reclassify_selected_materials tests.test_vault_restructure -v`

Expected: PASS。

- [ ] **Step 6: 提交注册表改造**

```powershell
git add scripts/domain_taxonomy.py scripts/export_search_results.py scripts/reclassify_selected_materials.py scripts/restructure_obsidian_vault.py tests/test_domain_taxonomy.py tests/test_export_search_results.py tests/test_reclassify_selected_materials.py tests/test_vault_restructure.py
git diff --cached --check
git commit -m "统一固定受管领域注册表"
```

### Task 2: 固化新领域的正文判定边界

**Files:**
- Modify: `scripts/domain_taxonomy.py`
- Modify: `scripts/reclassify_selected_materials.py`
- Modify: `tests/test_export_search_results.py`
- Modify: `tests/test_reclassify_selected_materials.py`

**Interfaces:**
- Consumes: `DOMAIN_PROFILES`、`MANAGED_DOMAINS`
- Produces: 四个新边界下稳定的 `assess_primary_domain(...)` 和 `classify_document(...)` 结果

- [ ] **Step 1: 写典型正文和歧义正文的失败测试**

```python
def test_new_domains_have_unique_primary_domain(self):
    cases = {
        "信息技术": "PostgreSQL 数据库采用容器部署，讨论索引、备份和网络安全加固。",
        "科技产业": "分析英伟达 GPU 供需、先进制程、产业链和公司收入。",
        "自然科学": "用微积分和经典力学推导行星轨道，并讨论天文观测。",
        "历史与社会": "比较历史制度、政治结构、社会阶层与公共政策。",
    }
    for expected, body in cases.items():
        result = assess_primary_domain("示例", body, MANAGED_DOMAINS)
        self.assertTrue(result.matched)
        self.assertEqual(result.domain, expected)

def test_ambiguous_single_terms_do_not_override_body_topic(self):
    result = assess_primary_domain(
        "GPU",
        "介绍大模型训练、Transformer 推理、参数量和强化学习。",
        MANAGED_DOMAINS,
    )
    self.assertEqual(result.domain, "AI")
```

另加“存储技术实现归信息技术、存储企业财报归科技产业”“心理沟通归两性情感或个人成长而非历史与社会”的回归样例。

- [ ] **Step 2: 运行目标测试并确认新样例失败**

Run: `python -m unittest tests.test_export_search_results.DomainRelevanceTests tests.test_reclassify_selected_materials.ClassificationTests -v`

Expected: FAIL，至少一个新增领域未通过唯一主领域判断。

- [ ] **Step 3: 调整核心词、辅助词和标题回退规则**

只增加能够表达正文主旨的短语；公司名、`GPU`、`存储`、`心理`等歧义单词只能作为辅助证据。给重分类器增加新领域的有限标题回退，不允许单个宽泛词绕过正文分数门槛。

- [ ] **Step 4: 运行分类回归测试**

Run: `python -m unittest tests.test_domain_taxonomy tests.test_export_search_results tests.test_reclassify_selected_materials -v`

Expected: PASS。

- [ ] **Step 5: 提交分类边界**

```powershell
git add scripts/domain_taxonomy.py scripts/reclassify_selected_materials.py tests/test_export_search_results.py tests/test_reclassify_selected_materials.py
git diff --cached --check
git commit -m "补充十二领域分类边界"
```

### Task 3: 更新脚手架、模板和治理文档

**Files:**
- Modify: `scripts/restructure_obsidian_vault.py`
- Modify: `templates/keyword-union-export-job.json`
- Modify: `SKILL.md`
- Modify: `references/obsidian-knowledge-management.md`
- Modify: `references/selected-materials-governance.md`
- Modify: `tests/test_vault_restructure.py`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Consumes: `MANAGED_DOMAINS`
- Produces: 两层十二领域目录、首页十二领域入口、关键词模板十二领域分组

- [ ] **Step 1: 扩展脚手架和文档契约失败测试**

```python
def test_scaffold_creates_exact_managed_domains(self):
    write_vault_documents(plan)
    for root_name in ("20_知识笔记", "30_精选资料"):
        actual = tuple(
            path.name for path in (vault / root_name).iterdir()
            if path.is_dir()
        )
        self.assertEqual(set(actual), set(MANAGED_DOMAINS))
    home = (vault / "00_首页.md").read_text(encoding="utf-8")
    self.assertIn("30_精选资料/信息技术/目录索引", home)
    self.assertNotIn("30_精选资料/软件工程/", home)
```

文档测试同时断言“固定十二领域”、三个新增名称、`信息技术` 和“其余旧资料只审计不自动移动”。

- [ ] **Step 2: 运行脚手架和文档测试并确认失败**

Run: `python -m unittest tests.test_vault_restructure tests.test_skill_documentation -v`

Expected: FAIL，旧首页或旧文档仍含九领域/软件工程契约。

- [ ] **Step 3: 更新首页、目录树、允许值和关键词模板**

关键词模板按以下领域归组：信息技术、AI、Quant、投资理财、知识管理、健康医学、中医、两性情感、个人成长、科技产业、自然科学、历史与社会；别名仍保留 `HugginFace -> HuggingFace/Hugging Face`。不把宽泛公司名作为唯一正文分类依据。

- [ ] **Step 4: 运行 JSON、脚手架和文档校验**

Run: `python -m json.tool templates/keyword-union-export-job.json > $null`

Run: `python -m unittest tests.test_vault_restructure tests.test_skill_documentation -v`

Expected: PASS。

- [ ] **Step 5: 仅暂存本任务对 SKILL.md 的修改**

先用 `git diff -- SKILL.md` 区分用户已有 Developer Token 预检区块和本任务领域区块。创建只包含领域区块的补丁并运行 `git apply --cached <patch>`；工作树继续保留两类修改，缓存区不得出现 Developer Token 区块。随后运行 `git diff --cached -- SKILL.md` 人工核对。

- [ ] **Step 6: 提交脚手架和文档**

```powershell
git add scripts/restructure_obsidian_vault.py templates/keyword-union-export-job.json references/obsidian-knowledge-management.md references/selected-materials-governance.md tests/test_vault_restructure.py tests/test_skill_documentation.py
git diff --cached --check
git commit -m "更新十二领域目录与治理规则"
```

### Task 4: 实现可回滚的领域迁移命令

**Files:**
- Create: `scripts/migrate_domain_taxonomy.py`
- Create: `tests/test_migrate_domain_taxonomy.py`
- Modify: `scripts/export_transaction.py` only if a small public restore interface is required

**Interfaces:**
- Produces: `build_migration_plan(vault: Path) -> DomainMigrationPlan`
- Produces: `apply_migration(plan: DomainMigrationPlan, *, confirmation: str) -> dict`
- Produces: `verify_migration(vault: Path) -> dict`
- Produces: `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 写预览只读、冲突前置失败和确认词测试**

```python
def test_preview_is_read_only_and_lists_rename_and_missing_domains(self):
    before = snapshot_tree(vault)
    plan = build_migration_plan(vault)
    self.assertEqual(plan.renames[0].source.name, "软件工程")
    self.assertEqual(plan.renames[0].destination.name, "信息技术")
    self.assertIn("科技产业", plan.missing_domains)
    self.assertEqual(snapshot_tree(vault), before)

def test_apply_requires_exact_confirmation(self):
    with self.assertRaisesRegex(ValueError, "EXPAND_MANAGED_DOMAINS"):
        apply_migration(build_migration_plan(vault), confirmation="yes")
```

再覆盖目标同名异内容、错误文件类型、非法 frontmatter 和路径逃逸；这些错误必须发生在事务建立和业务写入前。

- [ ] **Step 2: 运行迁移测试并确认模块不存在**

Run: `python -m unittest tests.test_migrate_domain_taxonomy -v`

Expected: FAIL，提示迁移模块不存在。

- [ ] **Step 3: 实现计划对象和精确文本变换**

```python
@dataclass(frozen=True)
class DomainRename:
    source: Path
    destination: Path

@dataclass(frozen=True)
class DomainMigrationPlan:
    vault: Path
    renames: tuple[DomainRename, ...]
    markdown_updates: tuple[Path, ...]
    missing_directories: tuple[Path, ...]
    issues: tuple[str, ...]
```

frontmatter 只改精确的 `domain: 软件工程`；链接只改 `20_知识笔记/软件工程/` 和 `30_精选资料/软件工程/` 的 Markdown/Wikilink 路径片段。普通正文中的“软件工程”术语保持不变。

- [ ] **Step 4: 实现事务应用、索引重建和失败恢复**

复用 `runtime_write_lock`、`ExportTransaction.begin(...)`、`record_write`、`record_move`、`commit` 和 `rollback`。目录操作前验证源、目标解析后仍在 Vault 内。应用后对每个 `MANAGED_DOMAINS` 调用 `write_knowledge_base_index`，并重写首页和知识笔记总索引。

- [ ] **Step 5: 写并通过应用、附件、回滚和幂等测试**

```python
def test_apply_renames_domains_updates_metadata_links_and_keeps_assets(self):
    result = apply_migration(
        build_migration_plan(vault),
        confirmation="EXPAND_MANAGED_DOMAINS",
    )
    self.assertFalse((vault / "30_精选资料" / "软件工程").exists())
    self.assertTrue((vault / "30_精选资料" / "信息技术" / "_attachments" / "a.png").exists())
    self.assertNotIn("domain: 软件工程", read_all_markdown(vault))
    self.assertNotIn("30_精选资料/软件工程/", read_all_markdown(vault))
    self.assertTrue(result["ok"])

def test_second_preview_is_noop(self):
    apply_migration(build_migration_plan(vault), confirmation="EXPAND_MANAGED_DOMAINS")
    second = build_migration_plan(vault)
    self.assertFalse(second.renames)
    self.assertFalse(second.markdown_updates)
    self.assertFalse(second.missing_directories)
```

Run: `python -m unittest tests.test_migrate_domain_taxonomy tests.test_export_transaction tests.test_export_integrity -v`

Expected: PASS。

- [ ] **Step 6: 提交迁移工具**

```powershell
git add scripts/migrate_domain_taxonomy.py tests/test_migrate_domain_taxonomy.py scripts/export_transaction.py
git diff --cached --check
git commit -m "实现受管领域可回滚迁移"
```

### Task 5: 仓库全量验证

**Files:**
- Modify only files required by failing regression tests

**Interfaces:**
- Consumes: Tasks 1-4 的全部接口
- Produces: 可安全用于正式 Vault 的已验证仓库状态

- [ ] **Step 1: 运行完整测试**

Run: `python -m unittest discover -s tests -v`

Expected: 所有测试 PASS。

- [ ] **Step 2: 运行编译、JSON 和空白检查**

Run: `python -m compileall -q scripts tests`

Run: `python -m json.tool templates/keyword-union-export-job.json > $null`

Run: `git diff --check`

Expected: 全部退出码为 0。

- [ ] **Step 3: 确认工作树只剩用户原有修改或本任务明确文件**

Run: `git status --short`

Expected: `SKILL.md` 可保留未提交的 Developer Token 预检修改；不存在临时补丁、测试缓存或意外 Vault 内容。

### Task 6: 正式 Vault 迁移、只读审计与独立验收

**Files:**
- Runtime target: configured `OBSIDIAN_VAULT_PATH`
- Runtime reports: `<vault>/.state/yinxiang-notes/`

**Interfaces:**
- Consumes: `scripts/migrate_domain_taxonomy.py`
- Consumes: `scripts/reclassify_selected_materials.py audit`
- Consumes: `scripts.export_integrity.scan_export_integrity`
- Produces: 正式 Vault 十二领域目录、迁移事务、只读审计报告和验收证据

- [ ] **Step 1: 运行只读预览并保存计划摘要**

Run: `python -X utf8 scripts/migrate_domain_taxonomy.py preview --vault "D:\OneDrive\文档\@_Obsidian"`

Expected: 只列出“软件工程 -> 信息技术”、缺失目录、frontmatter/链接更新和索引重建；无冲突或路径错误。

- [ ] **Step 2: 执行一次确认写入**

Run: `python -X utf8 scripts/migrate_domain_taxonomy.py apply --vault "D:\OneDrive\文档\@_Obsidian" --confirm EXPAND_MANAGED_DOMAINS`

Expected: 事务状态为 committed，命令返回 `ok: true`。

- [ ] **Step 3: 独立验证十二领域与索引**

Run: `python -X utf8 scripts/migrate_domain_taxonomy.py verify --vault "D:\OneDrive\文档\@_Obsidian"`

Expected: 两层目录集合、frontmatter、首页、知识索引、十二个精选资料索引、附件和链接全部通过。

- [ ] **Step 4: 生成只读重分类审计，禁止应用 decisions**

Run: `python -X utf8 scripts/reclassify_selected_materials.py audit --vault "D:\OneDrive\文档\@_Obsidian"`

Expected: 生成十二领域建议报告；不运行 `apply`，不移动、删除或改域任何其他资料。

- [ ] **Step 5: 运行全领域完整性扫描和 Vault Git 验证**

Run: `python -X utf8 -c "from pathlib import Path; from scripts.domain_taxonomy import MANAGED_DOMAINS; from scripts.export_integrity import scan_export_integrity; r=scan_export_integrity(Path(r'D:\OneDrive\文档\@_Obsidian'), MANAGED_DOMAINS); print(r.to_dict())"`

Run: `python -X utf8 scripts/vault_git.py verify --vault "D:\OneDrive\文档\@_Obsidian"`

Expected: 完整性结果 `ok: true`，所有问题集合为空；Vault Git 只跟踪允许的 Markdown 和稳定配置。

- [ ] **Step 6: 记录正式 Vault 的 Markdown-only Git 变更**

使用现有 `vault_git.py` 的事务提交接口，只提交本次迁移允许的 Markdown、索引和稳定配置，不提交附件、`.state`、快照或凭据。提交消息使用：`扩展固定受管领域并重命名信息技术`。

- [ ] **Step 7: 最终复核幂等性和源仓库状态**

再次运行 `preview`，Expected: 无业务变更。运行源仓库 `git status --short`，确认只保留已知的用户修改；记录源仓库提交、Vault 提交、事务 ID、审计报告路径和完整性结果。
