# 关键词导出增量快照与 Markdown-only Git 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用与实际变更量相关的事务快照替换 `keyword_union` 全量 ZIP，并为正式 Vault 建立只跟踪 Markdown、目录索引和稳定配置的 Git 历史。

**Architecture:** 新增 `VaultMutationJournal` 作为所有关键词导出文件写入、删除和移动的统一事务边界，并使用 SQLite backup API 保存目录库前像。新增 `vault_git` 模块负责 Git 白名单、基线初始化、干净工作树检查和按事务路径提交；`export_multi_domain` 在完整性验收后提交 Git、提交事务并安全清理旧全量 ZIP。

**Tech Stack:** Python 3.12、标准库 `pathlib`/`hashlib`/`json`/`sqlite3`/`subprocess`、Git、`unittest`、PowerShell。

## Global Constraints

- 只改造 `keyword_union`；重分类、Vault 重组和旧逐篇治理继续使用原快照机制。
- 新任务默认不得创建 `<任务 ID>-before.zip`。
- 增量事务不得预扫描或哈希全部未变化附件。
- Git 只允许 Markdown、目录索引、`.gitignore`、`.gitattributes` 和稳定 `.obsidian` 配置。
- Git 必须忽略 `_attachments`、`.state`、快照、凭据和其他二进制文件。
- 未配置远程仓库时只声明本地 Git 历史，不声明独立异地备份。
- Git 工作树不干净时必须在正式 Vault 业务写入前停止。
- 首个增量任务完整验收前保留 `d86b2fe8acea43bb` 全量快照。
- 中文文档和 Git Commit 消息使用简体中文。
- 每个任务采用红—绿测试循环，并在提交前运行 `git diff --check`。

---

## 文件结构

- 新建 `scripts/export_transaction.py`：事务清单、内容寻址前像、SQLite 检查点、恢复和事务保留。
- 新建 `scripts/vault_git.py`：Git 白名单、初始化、验证、导出前检查和按事务提交。
- 修改 `scripts/sync_to_obsidian.py`：附件写入接受事务钩子。
- 修改 `scripts/export_search_results.py`：Markdown 物化接受事务钩子。
- 修改 `scripts/knowledge_base.py`：迁移、去重和索引重建接受事务钩子。
- 修改 `scripts/export_multi_domain.py`：创建事务、传递事务钩子、提交 Git、写报告并迁移旧快照。
- 修改 `scripts/export_snapshot.py`：增加增量任务成功后的旧全量 ZIP 安全清理入口。
- 新建 `tests/test_export_transaction.py`：事务和恢复单元测试。
- 新建 `tests/test_vault_git.py`：Git 跟踪边界和提交测试。
- 修改 `tests/test_export_search_results.py`、`tests/test_knowledge_base.py`、`tests/test_export_multi_domain.py`、`tests/test_export_snapshot.py`：集成和迁移测试。
- 修改 `SKILL.md`、`references/export-workflows.md`、`README.md`、`tests/test_skill_documentation.py`：长期契约和命令文档。

---

### Task 1: 增量事务核心与 SQLite 检查点

**Files:**
- Create: `scripts/export_transaction.py`
- Create: `tests/test_export_transaction.py`

**Interfaces:**
- Produces: `VaultMutationJournal.begin(vault, state_root, job_id, selection_hash, catalog_path, baseline_git_head=None)`
- Produces: `prepare_write(path)`, `record_write(path)`, `prepare_delete(path)`, `record_delete(path)`, `prepare_move(source, destination)`, `record_move(source, destination)`
- Produces: `seal() -> TransactionSummary`, `mark_committed(git_commit)`, `restore(confirm)`, `to_dict()`
- Produces: `prune_committed_transactions(vault, state_root, current_job_id, retain_count=1)`

- [ ] **Step 1: 写入事务失败测试**

```python
def test_write_delete_move_and_sqlite_backup_are_recorded_once():
    journal = VaultMutationJournal.begin(
        vault,
        state_root,
        "1111111111111111",
        "selection-hash",
        catalog,
    )
    journal.prepare_write(existing)
    existing.write_text("after", encoding="utf-8")
    journal.record_write(existing)
    journal.prepare_write(existing)
    journal.record_write(existing)
    journal.prepare_delete(deleted)
    deleted.unlink()
    journal.record_delete(deleted)
    journal.prepare_move(source, destination)
    source.replace(destination)
    journal.record_move(source, destination)
    summary = journal.seal()
    assert summary.changed_paths == 3
    assert summary.object_count == 3
    assert sqlite_integrity(summary.sqlite_backup) == "ok"
```

同时添加路径逃逸、符号链接、同任务续跑不覆盖前像、相同内容只保存一个对象、清单半写入后拒绝加载测试。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_export_transaction -v`

Expected: FAIL，提示 `scripts.export_transaction` 不存在。

- [ ] **Step 3: 实现最小事务模型**

```python
@dataclass(frozen=True)
class TransactionSummary:
    job_id: str
    state: str
    changed_paths: int
    object_count: int
    stored_bytes: int
    sqlite_backup: str | None


class VaultMutationJournal:
    @classmethod
    def begin(
        cls,
        vault,
        state_root,
        job_id,
        selection_hash,
        catalog_path,
        baseline_git_head=None,
    ):
        ...

    def prepare_write(self, path):
        ...

    def record_write(self, path):
        ...
```

清单保存到 `.state/yinxiang-notes/transactions/<job_id>/manifest.json`；对象以 SHA-256 为文件名。SQLite 存在时用只读源连接的 `backup()` 写入 `export-catalog.sqlite3.before`，不存在时记录 `catalog_existed: false`。

- [ ] **Step 4: 实现显式恢复和保留**

恢复前验证无活动锁、当前文件符合事务 after 哈希、所有对象和 SQLite 备份哈希有效。按操作逆序恢复，并使用固定确认词 `ROLLBACK_KEYWORD_EXPORT`。

- [ ] **Step 5: 运行事务测试**

Run: `python -m unittest tests.test_export_transaction -v`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add scripts/export_transaction.py tests/test_export_transaction.py
git diff --cached --check
git commit -m "实现关键词导出增量事务快照"
```

---

### Task 2: 给附件、Markdown、迁移、去重和索引写入接入事务钩子

**Files:**
- Modify: `scripts/sync_to_obsidian.py`
- Modify: `scripts/export_search_results.py`
- Modify: `scripts/knowledge_base.py`
- Modify: `tests/test_export_search_results.py`
- Modify: `tests/test_knowledge_base.py`
- Test: `tests/test_export_transaction.py`

**Interfaces:**
- Consumes: Task 1 的 `VaultMutationJournal`
- Produces: `save_attachments(resources, attachments_dir, journal=None)`
- Produces: `export_note_to_obsidian(..., journal=None)`
- Produces: `archive_root_notes(root, journal=None)`, `deduplicate_archived_notes(root, journal=None)`, `write_knowledge_base_index(root, domain="AI", journal=None)`, `finalize_knowledge_base(root, domain="AI", journal=None)`

- [ ] **Step 1: 写入附件和 Markdown 事务测试**

```python
def test_export_records_only_new_attachment_and_changed_markdown():
    output = export_note_to_obsidian(
        note,
        "收件箱",
        target,
        selection_mode="keyword_union",
        matched_keywords=("AI",),
        selection_hash="hash",
        journal=journal,
    )
    summary = journal.seal()
    assert output in journal.changed_paths()
    assert attachment in journal.changed_paths()
    assert untouched_large_attachment not in journal.changed_paths()
```

- [ ] **Step 2: 运行测试并确认签名失败**

Run: `python -m unittest tests.test_export_search_results tests.test_knowledge_base -v`

Expected: FAIL，提示不接受 `journal`。

- [ ] **Step 3: 修改写入函数**

在真正写入前调用 `prepare_write`，成功后调用 `record_write`。已存在且哈希相同的附件不写入、不记事务。临时索引文件不进入事务，只对最终 `目录索引.md` 记录前像和 after 哈希。

- [ ] **Step 4: 修改迁移和去重函数**

根目录文章迁移和胜出文件改名使用 `prepare_move`/`record_move`；旧重复文件删除使用 `prepare_delete`/`record_delete`。保持 `journal=None` 时原行为不变。

- [ ] **Step 5: 运行定向测试**

Run: `python -m unittest tests.test_export_search_results tests.test_knowledge_base tests.test_export_transaction -v`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add scripts/sync_to_obsidian.py scripts/export_search_results.py scripts/knowledge_base.py tests/test_export_search_results.py tests/test_knowledge_base.py tests/test_export_transaction.py
git diff --cached --check
git commit -m "接入导出文件事务写入"
```

---

### Task 3: Markdown-only Git 白名单、初始化与按事务提交

**Files:**
- Create: `scripts/vault_git.py`
- Create: `tests/test_vault_git.py`

**Interfaces:**
- Produces: `GitBaseline(enabled: bool, branch: str | None, head: str | None)`
- Produces: `GitHistoryResult(enabled: bool, branch: str | None, commit: str | None, tracked_paths: int, pushed: bool, status: str)`
- Produces: `write_git_policy(vault)`, `initialize_vault_git(vault)`, `verify_tracked_paths(vault)`, `preflight_vault_git(vault)`, `commit_transaction(vault, journal, baseline, message)`
- CLI: `python scripts/vault_git.py init|verify`

- [ ] **Step 1: 写入 Git 白名单失败测试**

```python
def test_initialize_tracks_only_markdown_and_stable_config():
    initialize_vault_git(vault)
    tracked = git_lines(vault, "ls-files")
    assert "文章.md" in tracked
    assert ".obsidian/app.json" in tracked
    assert ".obsidian/workspace.json" not in tracked
    assert "30_精选资料/AI/_attachments/a.png" not in tracked
    assert ".state/yinxiang-notes/report.json" not in tracked
```

增加非允许扩展、凭据文件、脏工作树、事务外路径、无 Git 身份和无变更提交测试。

- [ ] **Step 2: 运行测试并确认模块缺失**

Run: `python -m unittest tests.test_vault_git -v`

Expected: FAIL，提示 `scripts.vault_git` 不存在。

- [ ] **Step 3: 实现 `.gitignore` 和 `.gitattributes` 白名单**

`.gitignore` 先忽略全部文件，再只放行目录、`*.md`、`.gitignore`、`.gitattributes` 和设计中列出的 `.obsidian` 稳定配置；随后再次显式忽略 `.state/`、`**/_attachments/`、`workspace*.json`、凭据和二进制。

- [ ] **Step 4: 实现 Git 命令边界**

所有 Git 命令使用参数数组和 `subprocess.run(..., check=True, text=True, encoding="utf-8")`，不经 shell。`verify_tracked_paths` 对 `git ls-files -z` 的每条路径运行允许列表判断。自动提交只接收事务清单过滤后的路径，不调用无边界 `git add -A`。

- [ ] **Step 5: 运行 Git 测试**

Run: `python -m unittest tests.test_vault_git -v`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add scripts/vault_git.py tests/test_vault_git.py
git diff --cached --check
git commit -m "实现 Obsidian Markdown Git 历史"
```

---

### Task 4: `keyword_union` 集成、报告契约和旧 ZIP 迁移

**Files:**
- Modify: `scripts/export_multi_domain.py`
- Modify: `scripts/export_snapshot.py`
- Modify: `tests/test_export_multi_domain.py`
- Modify: `tests/test_export_snapshot.py`

**Interfaces:**
- Consumes: Task 1 的事务接口
- Consumes: Task 2 的 `journal` 参数
- Consumes: Task 3 的 Git 接口
- Produces: 报告字段 `transaction_snapshot`、`git_history`、`legacy_snapshot_cleanup`
- Produces: `prune_legacy_export_snapshots(vault, snapshot_dir)`

- [ ] **Step 1: 修改集成测试为期望“不创建新 ZIP”**

```python
report = run_export_job(...)
assert report["ok"] is True
assert report["transaction_snapshot"]["mode"] == "incremental"
assert report["transaction_snapshot"]["state"] == "committed"
assert not (
    snapshot_dir / f"{_job_id(job)}-before.zip"
).exists()
assert report["git_history"]["status"] in {"committed", "no_changes", "disabled"}
```

增加 Git 脏工作树在 Catalog/Vault 写入前失败、Git 提交失败报告未完成、旧完整快照只在增量事务和 Git 成功后删除、失败时保留旧快照测试。

- [ ] **Step 2: 运行定向测试并确认旧行为失败**

Run: `python -m unittest tests.test_export_multi_domain tests.test_export_snapshot -v`

Expected: FAIL，报告仍包含全量 `snapshot`。

- [ ] **Step 3: 在候选分页后创建事务**

在打开 `ExportCatalog` 前：

```python
baseline = preflight_vault_git(job.vault)
journal = VaultMutationJournal.begin(
    job.vault,
    VaultStatePaths.for_vault(job.vault).root,
    _job_id(job),
    selection_hash,
    catalog_path,
    baseline_git_head=baseline.head,
)
```

删除 `create_domain_snapshot` 调用，并把 `journal` 传给 Markdown、附件、隔离和最终化函数。

- [ ] **Step 4: 给隔离区接入移动/删除事务**

`reconcile_keyword_outputs(..., journal=None)` 在移动到隔离区或删除重复隔离副本前记录对应操作。隔离清单属于 `.state`，仍由事务保护但不进入 Git。

- [ ] **Step 5: 集成验收、Git 和报告**

完整性报告初步通过后依次执行：

1. `journal.seal()`；
2. `commit_transaction(...)`；
3. `journal.mark_committed(git_commit)`；
4. `prune_committed_transactions(...)`；
5. `prune_legacy_export_snapshots(...)`；
6. 写入最终报告。

Git 未初始化时允许 `status: disabled`，以保持其他设备兼容；正式 Vault 初始化 Git 后，提交失败必须令报告 `ok: false`。

- [ ] **Step 6: 运行集成测试**

Run: `python -m unittest tests.test_export_multi_domain tests.test_export_snapshot tests.test_export_transaction tests.test_vault_git -v`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add scripts/export_multi_domain.py scripts/export_snapshot.py tests/test_export_multi_domain.py tests/test_export_snapshot.py
git diff --cached --check
git commit -m "将关键词导出切换为增量快照"
```

---

### Task 5: 恢复 CLI、技能文档和长期契约

**Files:**
- Modify: `scripts/export_transaction.py`
- Modify: `SKILL.md`
- Modify: `references/export-workflows.md`
- Modify: `README.md`
- Modify: `tests/test_skill_documentation.py`
- Test: `tests/test_export_transaction.py`

**Interfaces:**
- Consumes: Task 1 的恢复逻辑
- Produces: `inspect` 与 `restore --confirm ROLLBACK_KEYWORD_EXPORT`

- [ ] **Step 1: 写入 CLI 和文档失败测试**

```python
result = run_transaction_cli("inspect", "--job-id", job_id)
assert result.returncode == 0
assert json.loads(result.stdout)["state"] == "in_progress"

restore = run_transaction_cli("restore", "--job-id", job_id)
assert restore.returncode != 0
assert "ROLLBACK_KEYWORD_EXPORT" in restore.stderr
```

文档测试要求出现 `transaction_snapshot`、`git_history`、`ROLLBACK_KEYWORD_EXPORT`、Markdown-only Git 和旧 ZIP 迁移门禁。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_export_transaction tests.test_skill_documentation -v`

Expected: FAIL，CLI 或文档契约尚未出现。

- [ ] **Step 3: 实现 CLI 和更新文档**

CLI 使用 `scripts.runtime.load_vault_root()`，不得接受绕过配置 Vault 的任意根路径。`inspect` 只读；`restore` 校验固定确认词、活动锁、事务对象和 after 哈希。

- [ ] **Step 4: 运行定向测试**

Run: `python -m unittest tests.test_export_transaction tests.test_skill_documentation -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add scripts/export_transaction.py SKILL.md references/export-workflows.md README.md tests/test_export_transaction.py tests/test_skill_documentation.py
git diff --cached --check
git commit -m "补充增量快照恢复与 Git 契约"
```

---

### Task 6: 全量测试、恢复演练和性能门禁

**Files:**
- Modify only if verification exposes defects in Tasks 1-5.

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 可进入正式 Vault 的已验证版本

- [ ] **Step 1: 运行完整测试**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 PASS。

- [ ] **Step 2: 运行静态门禁**

```powershell
git diff --check
python -m compileall -q scripts tests
```

Expected: exit 0。

- [ ] **Step 3: 在临时 Vault 执行恢复演练**

创建包含大附件、旧 Markdown、索引和 SQLite 的临时 Vault；运行增量导出模拟写入后执行 `restore`。比较事务前后所有受管文件 SHA-256、索引集合和 `PRAGMA integrity_check`。

Expected: 完全一致；未变化大附件不出现在事务对象中。

- [ ] **Step 4: 验证 Git 白名单**

在临时 Vault 初始化 Git，运行：

```powershell
python scripts/vault_git.py verify
git ls-files
```

Expected: 只包含允许路径。

- [ ] **Step 5: 提交验证修复**

仅在前述验证发现缺陷并修改文件时提交：

```powershell
git add <验证修复文件>
git diff --cached --check
git commit -m "修正增量快照验收问题"
```

---

### Task 7: 初始化正式 Vault Git 并完成真实迁移验收

**Files:**
- Create in formal Vault: `.gitignore`
- Create in formal Vault: `.gitattributes`
- Create in formal Vault: `.git/`
- Modify in formal Vault: `.state/yinxiang-notes/transactions/`、报告和旧快照状态

**Interfaces:**
- Consumes: Tasks 1-6 的 CLI 和导出器
- Produces: 正式 Vault `main` 基线提交、真实增量任务报告和跟踪边界审计

- [ ] **Step 1: 正式 Vault 预检**

确认无 `active-run.lock`、Git 用户名和邮箱存在、OneDrive Vault 路径正确、当前完整快照对存在且哈希有效。

- [ ] **Step 2: 初始化 Markdown-only Git**

Run: `python -X utf8 scripts/vault_git.py init`

Expected: 创建 `main` 和中文基线提交，不跟踪附件、`.state` 或 `workspace.json`。

- [ ] **Step 3: 独立验证正式跟踪边界**

运行 `git -C <vault> ls-files -z`，逐条检查允许列表；检查跟踪文件数量、总大小和 `git status --short`。

Expected: 工作树干净，禁用路径计数为 0。

- [ ] **Step 4: 用已完成的 2026-07-20 至 2026-08-01 任务执行真实增量续跑**

Run:

```powershell
python -X utf8 scripts/export_multi_domain.py --job .state\keyword-union-2026-07-20--2026-08-01.json --rate-limit-mode wait --max-rate-limit-wait 7200 --verbose
```

Expected: 复用正文缓存，不创建新完整 ZIP；报告 `ok: true`，事务 `committed`，Git 为 `committed` 或 `no_changes`。

- [ ] **Step 5: 验证旧完整快照迁移**

确认旧 `d86b2fe8acea43bb-before.zip` 和清单只在 Step 4 全部通过后删除；当前事务对象大小与实际变更相关。

- [ ] **Step 6: 独立审计**

验证 65 项查询 `pulled == total`、候选闭环、九域索引集合、附件、重复项、范围、选择指纹、SQLite、活动锁和 Git 工作树。

Expected: 全部通过。

---

### Task 8: 源仓库最终提交与交付

**Files:**
- All source files changed by Tasks 1-7.

**Interfaces:**
- Produces: 可审计的源仓库提交历史和最终验收摘要

- [ ] **Step 1: 运行最终门禁**

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
git status -sb
```

Expected: 测试全通过、编译通过、无空白错误、工作区干净。

- [ ] **Step 2: 核对提交历史**

Run: `git log --oneline --decorate -10`

Expected: 每个实现单元有独立中文提交，未包含正式 Vault 数据或凭据。

- [ ] **Step 3: 交付**

报告源仓库提交、正式 Vault Git 基线、真实增量任务 ID、事务大小、旧 ZIP 清理、九域索引和附件验收结果。
