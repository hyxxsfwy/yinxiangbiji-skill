# Obsidian 生命周期目录重新编号实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `80_系统`、`90_归档`、`99_废纸篓`设为唯一有效生命周期结构，并让重组脚本安全迁移旧 `90_系统`和 `99_归档`。

**Architecture:** 在现有 `restructure_obsidian_vault.py` 受控迁移流程中加入生命周期目录映射、文件级冲突预检和 Markdown 内部路径改写；快照、清单、验证、清理和失败恢复继续共用同一事务边界。验证器只接受新目录，`sync_to_obsidian.py` 使用 `80_系统`识别正式 LLM Wiki 根目录。

**Tech Stack:** Python 3.12、`pathlib`、`hashlib`、`zipfile`、`unittest`、Markdown、PowerShell

## Global Constraints

- 唯一有效顶层结构为 `00_首页.md`、`01_收件箱`、`10_项目`、`20_知识笔记`、`30_精选资料`、`80_系统`、`90_归档`、`99_废纸篓`。
- 旧 `90_系统`只允许作为 `80_系统`的迁移来源，旧 `99_归档`只允许作为 `90_归档`的迁移来源。
- 同路径异内容或文件/目录类型冲突必须在迁移写入前中止。
- 迁移不得覆盖用户文件；同内容文件可以幂等合并。
- 迁移记录写入 `80_系统/迁移记录`，快照必须覆盖本次实际存在的全部旧来源。
- Git Commit 消息使用简体中文。

---

### Task 1: 生命周期映射与冲突预检

**Files:**
- Modify: `tests/test_vault_restructure.py`
- Modify: `scripts/restructure_obsidian_vault.py`

**Interfaces:**
- Consumes: `MigrationItem`、`MigrationPlan`、`sha256_file(Path) -> str`
- Produces: `LEGACY_LIFECYCLE_MAPPINGS`、`build_migration_plan(Path) -> MigrationPlan`、`find_migration_conflicts(MigrationPlan) -> tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

在 `MigrationPlanTests` 中增加三个真实文件系统测试：

```python
def test_plan_includes_existing_lifecycle_directories(self):
    # 构造旧 90_系统和 99_归档，断言分别映射到 80_系统和 90_归档。

def test_preflight_accepts_same_content_but_rejects_different_content(self):
    # 同路径同字节无冲突；改写目标字节后返回包含相对路径的冲突。

def test_lifecycle_only_vault_does_not_require_retired_content_directories(self):
    # 只有 .obsidian、90_系统、99_归档时仍能构建迁移计划。
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_vault_restructure.MigrationPlanTests -v
```

Expected: FAIL，原因分别为生命周期映射缺失、`find_migration_conflicts` 不存在，以及构建计划仍强制要求三个历史知识库目录。

- [ ] **Step 3: Implement the minimal plan and preflight**

在 `scripts/restructure_obsidian_vault.py`：

```python
LEGACY_CONTENT_DIRECTORIES = (
    "AI相关知识库",
    "Quant相关知识库",
    "HYXX个人知识库",
)
LEGACY_LIFECYCLE_MAPPINGS = {
    "90_系统": "80_系统",
    "99_归档": "90_归档",
}
```

让 `build_migration_plan()` 只纳入实际存在的旧来源；历史知识库来源部分存在但必需文件缺失时仍报错。`destination_for_source()` 对生命周期目录保持相对路径。`find_migration_conflicts()` 比较目标类型及文件 SHA-256，返回全部冲突，不创建任何文件。

- [ ] **Step 4: Run the focused tests and full migration-plan tests**

Run:

```powershell
python -m unittest tests.test_vault_restructure.MigrationPlanTests -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add scripts/restructure_obsidian_vault.py tests/test_vault_restructure.py
git commit -m "支持旧生命周期目录预检"
```

### Task 2: 生命周期复制、快照和失败恢复

**Files:**
- Modify: `tests/test_vault_restructure.py`
- Modify: `scripts/restructure_obsidian_vault.py`

**Interfaces:**
- Consumes: `MigrationPlan.old_directories`、`destination_for_source()`、`create_backup()`、`write_manifest()`
- Produces: `copy_lifecycle_content(MigrationPlan) -> None`，扩展后的 `cleanup_old_directories()` 与恢复行为

- [ ] **Step 1: Write the failing integration tests**

增加以下测试：

```python
def test_apply_moves_old_lifecycle_files_and_creates_trash(self):
    # 执行完整命令，断言旧系统/归档文件进入新目录、99_废纸篓存在、旧目录消失。

def test_apply_merges_identical_lifecycle_file(self):
    # 目标已有同内容文件时完整迁移成功且文件只保留一份。

def test_apply_stops_before_snapshot_when_lifecycle_file_conflicts(self):
    # 目标同路径异内容时退出非零，旧目录和目标原内容不变，且不产生本次迁移记录。

def test_cleanup_failure_restores_lifecycle_sources(self):
    # 模拟第二个旧目录删除失败，断言 ZIP 恢复旧 90_系统和 99_归档全部文件。
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_vault_restructure.CommandLineTests tests.test_vault_restructure.CleanupGateTests -v
```

Expected: FAIL，旧生命周期文件未复制、冲突发生在写入后或恢复集合不完整。

- [ ] **Step 3: Implement lifecycle copy within the existing transaction**

在创建快照前调用预检；存在冲突时打印全部冲突并返回非零。快照和清单遍历 `plan.old_directories` 的所有文件。新增 `copy_lifecycle_content()`：

```python
def copy_lifecycle_content(plan: MigrationPlan):
    for source in iter_lifecycle_files(plan):
        destination = destination_for_source(plan, source)
        copy_file_without_overwrite(source, destination)
```

生命周期 Markdown 在写入前只改写本地路径前缀 `90_系统/` → `80_系统/`、`99_归档/` → `90_归档/`；二进制文件保持哈希。为避免与旧迁移记录重名，本次记录使用带“目录重编号”标识的新文件名；验证器保留读取已手工迁移 vault 中旧记录文件名的回退逻辑。

- [ ] **Step 4: Run focused and complete vault migration tests**

Run:

```powershell
python -m unittest tests.test_vault_restructure -v
```

Expected: PASS，且故障注入测试证明旧生命周期来源可恢复。

- [ ] **Step 5: Commit**

```powershell
git add scripts/restructure_obsidian_vault.py tests/test_vault_restructure.py
git commit -m "迁移并恢复旧生命周期目录"
```

### Task 3: 新结构生成与严格验证

**Files:**
- Modify: `tests/test_vault_restructure.py`
- Modify: `scripts/restructure_obsidian_vault.py`

**Interfaces:**
- Consumes: `ensure_target_structure()`、`write_vault_documents()`、`verify_completed_vault()`
- Produces: 只生成新路径的首页、模板、治理资产、报告和验证结果

- [ ] **Step 1: Write the failing structure and verifier tests**

把脚手架期望值改为 `80_系统`、`90_归档`、`99_废纸篓`，并新增：

```python
def test_verify_rejects_remaining_legacy_lifecycle_directories(self):
    # 已完成新结构中重新创建 90_系统或 99_归档，--verify 必须失败并指出旧目录。

def test_generated_home_and_summary_use_only_new_lifecycle_paths(self):
    # 断言系统链接指向 80_系统，归档说明指向 90_归档，不产生旧路径链接。

def test_verify_accepts_manually_renumbered_vault_with_legacy_record_names(self):
    # 迁移记录已随 90_系统手工移动到 80_系统时仍可只读验证。
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_vault_restructure.ScaffoldTests tests.test_vault_restructure.CommandLineTests -v
```

Expected: FAIL，生成路径仍含 `90_系统`/`99_归档`，验证器未拒绝旧生命周期目录。

- [ ] **Step 3: Replace canonical paths and strengthen verification**

将脚手架、模板安装、首页链接、项目说明、治理文件、记录目录和报告映射统一改为：

```text
80_系统/模板
80_系统/Bases
80_系统/知识库治理
80_系统/迁移记录
90_归档
99_废纸篓
```

`verify_completed_vault()` 要求三者存在，拒绝实际残留的旧 `90_系统`、`99_归档`，但不把历史迁移报告中作为说明文字出现的旧名称误判为当前目录。

- [ ] **Step 4: Run all vault migration tests**

Run:

```powershell
python -m unittest tests.test_vault_restructure -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add scripts/restructure_obsidian_vault.py tests/test_vault_restructure.py
git commit -m "统一 Obsidian 生命周期目录契约"
```

### Task 4: 全量同步安全边界

**Files:**
- Modify: `tests/test_sync_integrity.py`
- Modify: `scripts/sync_to_obsidian.py`

**Interfaces:**
- Consumes: `is_unified_llm_wiki_root(Path) -> bool`
- Produces: 使用 `80_系统`识别正式 LLM Wiki 的全量同步保护

- [ ] **Step 1: Change the safety test first**

将统一根目录测试夹具的系统目录改为 `80_系统`，再增加旧 `90_系统`单独存在时不满足新结构标记的断言。

- [ ] **Step 2: Run the safety test and verify RED**

Run:

```powershell
python -m unittest tests.test_sync_integrity.SyncDestinationSafetyTests -v
```

Expected: FAIL，因为 `is_unified_llm_wiki_root()` 仍查找 `90_系统`。

- [ ] **Step 3: Implement the new root marker**

把 `is_unified_llm_wiki_root()` 的系统标记改为 `vault_path / "80_系统"`，其余三个业务目录和 `00_首页.md`保持不变。

- [ ] **Step 4: Run sync integrity tests**

Run:

```powershell
python -m unittest tests.test_sync_integrity -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add scripts/sync_to_obsidian.py tests/test_sync_integrity.py
git commit -m "更新正式知识库同步保护"
```

### Task 5: Skill、文档与真实 vault 验收

**Files:**
- Modify: `tests/test_skill_documentation.py`
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `references/obsidian-knowledge-management.md`
- Modify: `docs/superpowers/specs/2026-07-27-obsidian-lifecycle-directory-renumbering-design.md`

**Interfaces:**
- Consumes: 新目录树和三个脚本命令
- Produces: 面向用户和代理的唯一有效目录规则、自动迁移说明和最终验证证据

- [ ] **Step 1: Update the documentation contract test first**

将 `test_documents_final_vault_structure_and_migration_command` 的顶层目录字面量更新为：

```python
[
    "00_首页.md",
    "01_收件箱/",
    "10_项目/",
    "20_知识笔记/",
    "30_精选资料/",
    "80_系统/",
    "90_归档/",
    "99_废纸篓/",
]
```

并断言文档明确写出“旧 `90_系统`和`99_归档`由重组脚本自动迁移”，治理路径为 `80_系统/知识库治理/`。

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```powershell
python -m unittest tests.test_skill_documentation -v
```

Expected: FAIL，现有 README、Skill 和参考文档仍声明旧结构。

- [ ] **Step 3: Update authoritative documentation**

统一修改 README、Skill 和参考文档：

- 新目录是唯一有效结构；
- `80_系统`只存模板、Bases、治理资产和迁移记录；
- `90_归档`存完成项目和不再活跃的过程材料；
- `99_废纸篓`存待删除、可恢复内容；
- 预览、执行、验证命令保持不变；
- 执行命令自动迁移旧 `90_系统`和`99_归档`；
- 历史设计正文不批量改写，只保留“已被取代”标注。

同时清理新设计文档末尾多余空行。

- [ ] **Step 4: Run all automated and real-vault checks**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --verify
```

Expected: 所有测试通过；编译和空白检查无输出；真实 vault 只读验证返回 0。

- [ ] **Step 5: Commit**

```powershell
git add README.md SKILL.md references/obsidian-knowledge-management.md tests/test_skill_documentation.py docs/superpowers/specs/2026-07-27-obsidian-lifecycle-directory-renumbering-design.md
git commit -m "同步 Obsidian 新目录文档"
```
