# Task 3 实现报告

## 结论

状态：`DONE_WITH_CONCERNS`

多领域导出任务已去除设备绝对 Vault 依赖，并迁入正式 Vault 的 `.state/yinxiang-notes/` 状态命名空间。任务 ID 不再包含 Vault 路径，旧任务文件中的 `vault` 字段只警告并忽略；CLI 默认目录、运行状态和报告均跟随当前 Vault，显式路径逃逸会被拒绝，实际导出运行由共享写锁包裹。

## TDD 记录

### RED

命令：

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_job_id_is_device_path_independent tests.test_export_multi_domain.CommandLinePathTests -v
```

结果：退出码 1，共出现 5 个预期断言失败。现有实现不接受独立 Vault 参数，`run_export_job()` 未处于 `runtime_write_lock()` 内，且 `--catalog`、`--state-file`、`--report-file` 均未拒绝状态命名空间外路径。

### GREEN

同一命令在最小实现后通过，3/3 项成功。随后 `tests.test_export_multi_domain` 12/12 项通过。

## 实现摘要

- `normalize_job(payload, vault)` 仅使用调用方传入的正式 Vault；`load_job(path, vault)` 对旧 `vault` 字段输出废弃警告并忽略。
- `_job_id()` 载荷固定为版本 2，只包含日期、领域与关键词，不含 Vault 绝对路径。
- CLI 使用 `load_vault_root()`、`VaultStatePaths.for_vault()` 和 `migrate_legacy_state()`，再派生 Vault 内的 catalog、runs 和 reports 路径。
- 所有显式输出路径在解析符号链接后必须位于当前 Vault 状态根内。
- `run_export_job()` 由 `runtime_write_lock(paths, task_id)` 包裹。
- 多领域任务模板删除 `vault` 字段，并由测试执行 UTF-8 JSON 严格解析。

## 修改文件

- `scripts/export_multi_domain.py`
- `templates/multi-domain-export-job.json`
- `tests/test_export_multi_domain.py`
- `.superpowers/sdd/2026-07-28-vault-scoped-runtime-state/task-3-report.md`

## 疑虑

首次运行三模块验证时，Windows 在原子替换测试临时状态文件时出现一次 `PermissionError: [WinError 5]`。该用例随后独立连续运行 5 次均通过，完整三模块测试复跑也通过，未能稳定复现；本任务没有为瞬时文件占用增加无依据的重试逻辑。

## Round 1 评审修复

状态：`DONE`

已按独立复审意见补齐旧默认状态的真实迁移链路：

- `main()` 从旧 CLI 实际使用的 `REPO_ROOT/.state` 扫描旧状态；
- `multi-export-*.json` 迁移到新 CLI 实际读写的 `paths.runs`，catalog、jobs 和 reports 保持各自既定映射；
- `load_job()` 先确认 JSON 根节点是对象，再检查废弃的 `vault` 字段，`null` 和数字均统一转为 `ValueError`。

### Round 1 TDD 记录

RED 命令：

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_vault_state.LegacyMigrationTests.test_first_migration_copies_allowed_files_and_records_sha256 tests.test_export_multi_domain.MultiDomainJobTests.test_non_object_job_payload_is_rejected_as_validation_error tests.test_export_multi_domain.CommandLinePathTests.test_main_migrates_legacy_default_state_into_paths_it_uses -v
```

结果：退出码 1。旧 multi-export 在 `runs/` 中不存在；`load_job(null/42)` 抛出 `TypeError`；端到端 CLI 用例在 Vault 新 catalog 路径读到 `FileNotFoundError`。

GREEN：同一命令修复后 3/3 通过。扩大验证到 `tests.test_vault_state`、`tests.test_export_multi_domain`、`tests.test_export_catalog` 和 `tests.test_export_integrity`，共 41 项全部通过。
