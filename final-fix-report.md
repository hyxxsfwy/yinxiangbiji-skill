# 最终 Important 修复报告

## 修复结论

最终审阅提出的 2 个 Important 均已修复。

1. 多领域导出现在先取得 `runtime_write_lock()`，再执行旧状态迁移、v1→v2 状态接管、凭据加载、NoteStore 创建和业务写入。活锁冲突时，不会创建目录数据库、迁移清单或 v2 接管文件，也不会修改既有 v1 状态。
2. Vault 状态目录、单领域目标目录和显式状态输出统一使用解析后路径边界校验。目标路径及其既存祖先经 `resolve()` 后必须仍位于解析后的 Vault 内；显式状态输出还必须位于 Vault 状态命名空间内。普通尚不存在且没有逃逸祖先的路径仍可正常派生和创建。

## TDD 证据

RED 阶段新增 3 个确定性回归用例，修复前均按预期失败：

- 活锁存在时，旧目录数据库仍被迁移到 Vault。
- 状态根解析到 Vault 外时，`VaultStatePaths.for_vault()` 未拒绝。
- 默认领域目标解析到 Vault 外时，`derive_domain_target()` 未拒绝。

GREEN 阶段上述 3 项全部通过。扩大定向回归覆盖状态迁移与锁、多个领域命令行路径、单领域命令行路径，共 43 项通过；另有 2 个真实目录符号链接用例因当前 Windows 环境无创建权限而按测试约定跳过，确定性 `Path.resolve()` 模拟用例已覆盖相同逃逸分支。

## 验证范围

- 定向测试：`tests.test_vault_state`、`tests.test_export_multi_domain.CommandLinePathTests`、`tests.test_export_search_results.CommandLineTests`
- Python 语法编译：相关实现与测试文件
- Git 空白错误检查：`git diff --check`

`final-review.md` 仅作为审阅输入，不纳入提交。
