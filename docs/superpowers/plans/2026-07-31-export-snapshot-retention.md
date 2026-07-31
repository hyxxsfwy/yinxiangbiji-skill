# 导出快照自动保留实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关键词并集导出验收成功后自动只保留当前完整导出快照，并把清理结果写入验收报告。

**Architecture:** 在 `scripts/export_snapshot.py` 中实现只管理 16 位任务 ID 快照对的独立清理器；`scripts/export_multi_domain.py` 在最终完整性结果确定、报告落盘前调用它。清理器先验证当前快照，再精确枚举历史快照对，保留非本工作流文件和不完整目标。

**Tech Stack:** Python 3.12、`pathlib`、`dataclasses`、`unittest`

## Global Constraints

- 默认只保留当前任务的一组完整导出快照。
- 只管理 `<16 位十六进制任务 ID>-before.zip` 与对应 `.sha256.json`。
- 重分类快照、孤立文件、非法名称、符号链接、报告、SQLite、运行状态和隔离区不得删除。
- 仅在导出最终验收成功且当前快照校验通过时清理。
- 清理错误必须使导出报告失败，并保留当前快照与可审计结果。

---

### Task 1: 快照保留清理器

**Files:**
- Modify: `scripts/export_snapshot.py`
- Test: `tests/test_export_snapshot.py`

**Interfaces:**
- Consumes: `create_domain_snapshot(vault, domains, snapshot_dir, job_id) -> SnapshotResult`
- Produces: `prune_export_snapshots(vault, snapshot_dir, current_job_id, retain_count=1) -> SnapshotCleanupResult`
- Produces: `SnapshotCleanupResult.to_dict() -> dict`

- [ ] **Step 1: 添加只保留当前快照的失败测试**

在 `tests/test_export_snapshot.py` 创建两个 16 位任务 ID 快照，并断言：

```python
result = prune_export_snapshots(
    vault,
    snapshot_dir,
    current_job_id="2222222222222222",
)
self.assertFalse((snapshot_dir / "1111111111111111-before.zip").exists())
self.assertTrue((snapshot_dir / "2222222222222222-before.zip").is_file())
self.assertEqual(result.deleted_files, 2)
```

- [ ] **Step 2: 添加误删防护和损坏当前快照测试**

创建重分类快照、孤立 ZIP、符号链接或目录，并断言全部保留；篡改当前 ZIP 后调用清理器，断言抛出 `ValueError` 且历史快照仍存在。

- [ ] **Step 3: 运行测试并确认按预期失败**

Run:

```powershell
python -m unittest tests.test_export_snapshot -v
```

Expected: `ImportError`，提示 `prune_export_snapshots` 尚不存在。

- [ ] **Step 4: 实现最小清理器**

在 `scripts/export_snapshot.py` 增加：

```python
_EXPORT_SNAPSHOT_ARCHIVE_RE = re.compile(
    r"(?P<job_id>[0-9a-f]{16})-before[.]zip"
)


@dataclass(frozen=True)
class SnapshotCleanupResult:
    executed: bool
    kept_job_ids: tuple[str, ...]
    deleted: tuple[dict, ...]
    skipped: tuple[dict, ...]

    @property
    def deleted_files(self):
        return len(self.deleted)

    @property
    def deleted_bytes(self):
        return sum(int(item["size"]) for item in self.deleted)

    def to_dict(self):
        return {
            "executed": self.executed,
            "kept_job_ids": list(self.kept_job_ids),
            "deleted_files": self.deleted_files,
            "deleted_bytes": self.deleted_bytes,
            "deleted": list(self.deleted),
            "skipped": list(self.skipped),
        }
```

`prune_export_snapshots` 必须先用 `_load_existing_snapshot` 校验当前快照；只枚举快照目录的直接子文件；拒绝符号链接；只有 ZIP 与清单都是普通文件时才形成候选对；保留当前任务和按修改时间倒序补足的 `retain_count - 1` 组。删除时先删大 ZIP、再删小清单，并把实际删除的路径和字节数写入结果。

- [ ] **Step 5: 运行快照测试**

Run:

```powershell
python -m unittest tests.test_export_snapshot -v
```

Expected: 全部通过。

- [ ] **Step 6: 提交清理器**

```powershell
git add scripts/export_snapshot.py tests/test_export_snapshot.py
git commit -m "实现导出快照自动保留"
```

### Task 2: 成功导出集成与报告

**Files:**
- Modify: `scripts/export_multi_domain.py`
- Test: `tests/test_export_multi_domain.py`

**Interfaces:**
- Consumes: `prune_export_snapshots(...) -> SnapshotCleanupResult`
- Produces: 报告字段 `snapshot_cleanup`

- [ ] **Step 1: 添加成功与失败分支的集成测试**

成功关键词任务预置一组旧快照，运行后断言旧快照被删除且报告包含：

```python
self.assertTrue(report["ok"])
self.assertTrue(report["snapshot_cleanup"]["executed"])
self.assertEqual(report["snapshot_cleanup"]["deleted_files"], 2)
```

构造完整性失败任务，断言旧快照仍存在，且：

```python
self.assertFalse(report["ok"])
self.assertFalse(report["snapshot_cleanup"]["executed"])
self.assertEqual(
    report["snapshot_cleanup"]["reason"],
    "export_validation_failed",
)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
python -m unittest \
  tests.test_export_multi_domain.MultiDomainJobTests.test_successful_keyword_export_prunes_old_export_snapshots \
  tests.test_export_multi_domain.MultiDomainJobTests.test_failed_keyword_export_keeps_old_export_snapshots \
  -v
```

Expected: 报告缺少 `snapshot_cleanup`，旧快照仍存在。

- [ ] **Step 3: 在报告落盘前集成清理**

在关键词报告构建后：

```python
if report["ok"]:
    try:
        cleanup = prune_export_snapshots(
            job.vault,
            VaultStatePaths.for_vault(job.vault).root / "snapshots",
            current_job_id=_job_id(job),
        )
        report["snapshot_cleanup"] = cleanup.to_dict()
    except (OSError, ValueError) as exc:
        report["ok"] = False
        report["snapshot_cleanup"] = {
            "executed": False,
            "reason": "cleanup_failed",
            "error": str(exc),
        }
else:
    report["snapshot_cleanup"] = {
        "executed": False,
        "reason": "export_validation_failed",
    }
_atomic_json(report_file, report)
```

- [ ] **Step 4: 运行集成测试和相关回归**

Run:

```powershell
python -m unittest tests.test_export_multi_domain tests.test_export_snapshot -v
```

Expected: 全部通过。

- [ ] **Step 5: 提交集成**

```powershell
git add scripts/export_multi_domain.py tests/test_export_multi_domain.py
git commit -m "在成功导出后清理旧快照"
```

### Task 3: Skill 契约与全量验证

**Files:**
- Modify: `SKILL.md`
- Modify: `references/export-workflows.md`
- Modify: `README.md`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Documents: 自动清理触发条件、保留范围、失败行为、报告字段

- [ ] **Step 1: 添加文档契约失败测试**

在 `tests/test_skill_documentation.py` 断言文档包含：

```python
self.assertIn("snapshot_cleanup", export_workflows)
self.assertIn("只保留当前任务的一组完整导出快照", export_workflows)
self.assertIn("验收失败", export_workflows)
self.assertIn("不清理", export_workflows)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
python -m unittest \
  tests.test_skill_documentation.SkillDocumentationTests.test_export_snapshot_retention_contract \
  -v
```

Expected: 文档缺少自动保留契约。

- [ ] **Step 3: 更新 Skill、工作流与 README**

写明：

- 成功关键词导出只保留当前完整快照；
- 验收失败、限流退出或当前快照校验失败时不清理；
- 其他工作流快照及状态文件不属于自动清理范围；
- `snapshot_cleanup` 是清理审计凭据。

- [ ] **Step 4: 运行全量测试和格式检查**

Run:

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest discover -s tests -v
git diff --check
```

Expected: 所有测试通过，`git diff --check` 无输出。

- [ ] **Step 5: 提交文档和最终验证结果**

```powershell
git add SKILL.md references/export-workflows.md README.md tests/test_skill_documentation.py
git commit -m "完善导出快照保留规则"
```
