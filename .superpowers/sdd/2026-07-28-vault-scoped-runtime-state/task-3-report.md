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

## Round 2 评审修复

状态：`DONE`

已按旧 CLI 的真实任务 ID 算法补齐 v1 到 v2 的安全接管：

- 回归测试直接复刻 v1 的 `since`、`until`、`vault.casefold()` 和 `domains` 载荷并执行 SHA-256，不使用新版 `_job_id()` 伪造旧文件名；
- 旧任务 JSON 含 `vault` 时，用该旧设备路径与规范化后的日期、领域和关键词计算 v1 ID，新版 v2 ID 仍不包含任何 Vault 绝对路径；
- 仓库旧 `.state` 迁移完成后，将 `runs/multi-export-<v1-id>.json` 和 `reports/<v1-id>.json` 无覆盖接管到对应 v2 默认路径，v1 文件与仓库旧源文件均保留；
- 接管先预检 run/report 的全部目标，再以同目录临时副本和排他硬链接发布；已有 v2 内容相同则复用，内容不同则在复制前明确报错并保留双方，并发创建目标时再次校验。

### Round 2 TDD 记录

真实 v1 RED 命令：

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_export_multi_domain.CommandLinePathTests.test_main_migrates_legacy_default_state_into_paths_it_uses -v
```

结果：退出码 1。旧 v1 run/report 已迁入 Vault，但新 CLI 派发 v2 路径，读取 `runs/multi-export-<v2-id>.json` 时出现预期 `FileNotFoundError`。

冲突预检 RED 命令：

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_export_multi_domain.CommandLinePathTests.test_legacy_state_takeover_preflights_all_targets_before_copying -v
```

结果：退出码 1。报告目标冲突时，旧实现已提前发布 v2 run；修复后先完成全部目标预检，不再产生部分接管。

GREEN：Task 3 三模块定向测试共 21 项全部通过；扩大到 `tests.test_vault_state` 后共 44 项全部通过。冲突用例确认既有 v2 不被覆盖，相同 v2 可直接复用；`py_compile` 与 `git diff --check` 均通过。

## Round 3 评审修复

状态：`DONE`

已将 v1 run/report 接管改为事务式发布：

- `_copy_without_overwrite()` 在新建 v2 目标时返回硬链接对应的文件身份，已有相同目标不计入本轮新建；
- `_adopt_legacy_job_state()` 记录本轮已发布目标，任一后续目标失败时逆序回滚；
- 回滚先将当前目标原子移入隔离路径，再比较设备号和文件号。仅当文件仍属于本轮发布时才删除；若已被并发替换，则以无覆盖硬链接恢复并发文件，即使替换内容与本轮内容相同也不会误删。

### Round 3 TDD 记录

RED 命令：

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_export_multi_domain.CommandLinePathTests.test_legacy_state_takeover_rolls_back_run_after_report_race -v
```

结果：退出码 1。run 发布成功后注入不同内容的并发 report，旧实现按预期抛错，但断言发现本轮 v2 run 仍然残留。

GREEN：定向竞态与并发替换所有权测试 2/2 通过；v1 run/report、并发 report 和并发替换的目标均未丢失。按 Round 3 限定范围未运行全套测试；`py_compile` 与 `git diff --check` 均通过。

## Round 4 评审修复

状态：`DONE`

已修复回滚异常掩盖原始接管异常的问题：

- `_adopt_legacy_job_state()` 单独捕获回滚阶段的 `BaseException`，通过原始异常的 `add_note()` 附加回滚异常及隔离路径，再以 bare `raise` 保持原始异常对象和回溯；
- 业务发布冲突、`KeyboardInterrupt` 与 `SystemExit` 均保持原始传播语义，回滚失败只作为补充诊断信息，不会替代首要错误。

### Round 4 TDD 记录

RED 命令：

```powershell
$env:PYTHONUTF8='1'
python -m unittest tests.test_export_multi_domain.CommandLinePathTests.test_legacy_state_takeover_preserves_publish_error_when_rollback_fails tests.test_export_multi_domain.CommandLinePathTests.test_legacy_state_takeover_preserves_control_flow_base_exceptions -v
```

结果：退出码 1。注入 report 发布冲突后，再令回滚恢复目标时遭到第三次占用，旧实现最终抛出回滚 `ValueError`，掩盖原始发布冲突；注入 `KeyboardInterrupt` 时也被回滚 `RuntimeError` 替代。

GREEN：同一命令 2/2 通过。最终传播的仍为原始发布异常或控制流异常对象，回滚错误和 `.rollback` 隔离路径保留在异常注记中。
