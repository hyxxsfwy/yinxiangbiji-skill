# 关键词导出增量快照与 Markdown-only Git 设计

## 1. 背景与目标

当前 `keyword_union` 导出在首次物化前，会把九个受管领域完整压缩为 `<任务 ID>-before.zip`。正式 Vault 目前约有 1,941 个 Markdown，合计 22.09 MiB；附件约 23,598 个，合计 7.69 GiB。完整快照因此约为 7.58 GiB，其耗时主要来自反复读取、哈希和压缩未发生变化的附件，而不是本次导出的实际变更。

本次改造同时解决两个问题：

1. 导出失败或人工回滚时，只依赖本次变更的增量前像，不再为每个任务压缩整个精选资料库。
2. 使用 Git 保存 Markdown、目录索引和稳定配置的版本历史，但不让附件、运行状态或快照进入 Git。

Git 在本阶段只提供本地历史。未配置远程仓库时，不能把它表述为独立异地备份；OneDrive 仍承担现有同步。后续若要推送私有远程仓库，必须单独配置远程地址和授权。

## 2. 方案选择

### 2.1 采用的混合方案

- 导出回滚使用增量事务快照。
- Markdown、目录索引和稳定配置使用 Git。
- `_attachments`、`.state`、快照、凭据和其他二进制文件不进入 Git。
- 成功导出在完整性验收后提交 Git；失败或中断保留事务状态，不创建成功提交。

### 2.2 不采用的方案

不把整个 Vault 直接提交到 Git 或 Git LFS。附件历史会持续扩大对象库，并使 OneDrive 同时同步工作区文件和 Git 对象，增加锁冲突、传输和恢复成本。

不只使用 Markdown-only Git 替代导出快照。Git 不跟踪附件，无法单独恢复本次被覆盖或删除的附件，也不能恢复 SQLite 分析缓存。

## 3. 增量事务快照

### 3.1 状态目录

每个关键词任务在以下目录维护一个事务：

```text
<vault>/.state/yinxiang-notes/transactions/<16 位任务 ID>/
  manifest.json
  objects/<sha256>
  export-catalog.sqlite3.before
```

`manifest.json` 至少包含：

- 格式版本、任务 ID、选择指纹和 Vault 标识；
- 创建时间、状态和基线 Git HEAD；
- `created`、`modified`、`deleted`、`moved` 操作；
- 每个路径的变更前哈希、大小和对象位置；
- 变更后的预期哈希；
- SQLite 备份路径和哈希；
- 完成、回滚或失败原因。

事务状态固定为：

```text
prepared -> in_progress -> committed
                         -> rollback_required -> rolled_back
```

同一任务续跑复用原事务，前像一旦写入不得覆盖。

### 3.2 写入拦截

所有关键词导出文件变更通过统一的 `VaultMutationJournal` 执行：

- 修改或删除现有文件前，调用 `capture_preimage(path)`；
- 创建新文件后，调用 `record_created(path)`；
- 移动或隔离文件时，记录源路径、目标路径和两端状态；
- 重建 `目录索引.md` 前保存旧索引；
- 写附件时，新附件只记录创建路径；若目标已经存在且内容不同，先保存前像并沿用现有“禁止无提示覆盖”规则；
- 事务开始时使用 SQLite backup API 生成一致的目录库检查点。

对象以 SHA-256 命名。同一事务内相同内容只保存一次。实现不得预扫描或重新哈希全部未变附件，运行复杂度应与本次实际修改文件数相关。

### 3.3 原子性和续跑

- 清单使用临时文件加原子替换写入。
- 每个文件先提交前像和操作意图，再执行 Vault 写入。
- 进程被终止时保留 `in_progress` 状态；同一任务续跑从现有运行状态继续，不自动回滚。
- 限流退出、Thrift 中断或完整性验收失败时，不清理事务对象。
- 只有报告准备写为 `ok: true`、事务清单完整且 Git 提交成功后，事务才标记为 `committed`。

### 3.4 恢复命令

提供只读检查和显式恢复命令：

```powershell
python scripts/export_transaction.py inspect --job-id <任务 ID>
python scripts/export_transaction.py restore --job-id <任务 ID> --confirm ROLLBACK_KEYWORD_EXPORT
```

恢复前必须：

- 确认不存在活动 Vault 写锁；
- 校验事务路径仍位于配置的正式 Vault；
- 校验当前文件与事务记录的变更后哈希一致；
- 检测到 Obsidian 或人工产生的后续修改时停止，不覆盖新内容；
- 校验 SQLite 备份和全部前像对象。

恢复顺序为：恢复移动和删除文件、恢复修改文件、删除本次创建文件、恢复 SQLite、重建并验证索引。任何一步失败都保留事务和诊断报告。

### 3.5 保留策略与迁移

- 保留最近一个成功事务。
- 所有 `prepared`、`in_progress`、`rollback_required` 和回滚失败事务不自动删除。
- 只有当前增量事务、恢复演练、完整性验收和 Git 提交全部成功后，才清理旧的 16 位任务 ID 全量 ZIP 快照。
- 旧 ZIP 创建和读取代码暂时保留为兼容能力，但新关键词任务默认不再创建完整 ZIP。
- 首个增量任务成功前，保留当前 `d86b2fe8acea43bb` 完整快照。

## 4. Markdown-only Git

### 4.1 仓库位置与分支

在正式 Vault 根目录初始化独立 Git 仓库，默认分支为 `main`。当前 Vault 尚无 `.git` 和 `.gitignore`。

Git 仓库位于 OneDrive 同步目录时，继续遵守“同一时刻只允许一台设备写同一 Vault”的约束。不得在两台设备同时导出、提交或解决冲突。

### 4.2 跟踪范围

允许跟踪：

- Vault 内所有 `*.md`；
- 所有领域的 `目录索引.md`，其已包含在 `*.md` 中；
- 根目录 `.gitignore` 和 `.gitattributes`；
- `.obsidian` 下稳定配置：
  - `app.json`
  - `appearance.json`
  - `core-plugins.json`
  - `graph.json`
  - `snippets/*.css`
  - `themes/*/manifest.json`
  - `themes/*/theme.css`
  - `plugins/*/manifest.json`
  - `plugins/*/data.json`

明确忽略：

- `.state/` 及其中的报告、SQLite、事务、快照和隔离区；
- 所有 `_attachments/`；
- `.env`、Token、NoteStore URL、ENEX 和凭据文件；
- `.obsidian/workspace*.json`、缓存、日志等设备相关状态；
- 除上述允许项外的图片、音频、视频、PDF、压缩包和其他二进制文件。

`.gitignore` 采用默认忽略、按允许列表放行的策略。初始化后必须用 `git ls-files` 做反向检查：任何被禁路径或非允许扩展进入索引都视为失败。

### 4.3 基线提交

初始化流程：

1. 写入 `.gitignore` 和 `.gitattributes`；
2. `git init -b main`；
3. 只添加允许范围；
4. 验证被跟踪文件清单；
5. 创建中文基线提交。

若系统未配置 Git 用户名或邮箱，初始化停止并给出明确错误，不写入虚构身份。

### 4.4 每次导出的提交

启用 Git 历史后，关键词导出前要求被跟踪工作树干净。这样不会把用户尚未提交的 Obsidian 编辑混入自动提交。

导出验收成功后：

1. 从事务清单取得本次新增、修改、移动和删除的 Markdown 或稳定配置路径；
2. 只暂存这些路径，不使用无边界的 `git add -A`；
3. 再次验证暂存区不含附件、`.state` 或禁用配置；
4. 创建中文提交，例如：

```text
同步印象笔记关键词导出：2026-07-20 至 2026-08-01
```

5. 把提交 SHA 写入导出报告的 `git_history` 字段。

如果导出期间出现新的被跟踪工作树修改，或 Git 提交失败，报告不得标记为最终成功；事务保持可续跑状态。重新执行同一任务时只重试验收和提交，不重新请求已经缓存的正文。

自动推送不在本次范围内。配置私有远程仓库后，推送必须作为独立、可审计步骤加入。

## 5. 报告契约

成功报告新增：

```json
{
  "transaction_snapshot": {
    "mode": "incremental",
    "job_id": "<任务 ID>",
    "state": "committed",
    "changed_paths": 0,
    "object_count": 0,
    "stored_bytes": 0,
    "sqlite_backup": "..."
  },
  "git_history": {
    "enabled": true,
    "branch": "main",
    "commit": "<SHA>",
    "tracked_paths": 0,
    "pushed": false
  }
}
```

以下任一条件成立时不得声明完成：

- 事务清单或对象校验失败；
- 目录库检查点无效；
- 完整性门禁未通过；
- Git 暂存区包含禁用路径；
- Git 工作树在导出期间产生未纳入事务的被跟踪修改；
- Git 提交失败。

## 6. 测试策略

### 6.1 单元测试

- 同一路径多次修改只保留一个最初前像；
- 相同内容只保存一个对象；
- 新增、修改、删除、移动操作正确写入清单；
- 路径逃逸、符号链接和目标同名异内容被拒绝；
- SQLite backup API 生成可通过 `PRAGMA integrity_check` 的检查点；
- 清单原子写入和中断后重载保持幂等。

### 6.2 恢复测试

在临时 Vault 中覆盖以下场景：

- 修改 Markdown 和索引；
- 新增 Markdown 与附件；
- 删除或隔离旧文件；
- 更新 SQLite；
- 执行恢复后逐文件哈希、索引集合和 SQLite 与事务前完全一致；
- 当前文件被外部修改时恢复拒绝覆盖；
- 中断后续跑不丢失最初前像。

### 6.3 Git 边界测试

- 基线提交只包含 Markdown、索引和允许配置；
- `git ls-files` 不包含 `_attachments`、`.state`、快照、凭据和其他二进制；
- 自动提交只暂存事务记录路径；
- 工作树初始不干净时在 Vault 写入前停止；
- 导出期间出现额外被跟踪修改时不创建成功提交；
- Git 提交失败时报告为未完成并保留事务。

### 6.4 集成与性能门禁

- 未变化的大附件目录不得被完整读取、哈希或压缩；
- 使用包含大附件但只修改少量 Markdown 的测试 Vault，增量快照大小必须与变更量相关；
- 成功导出后不生成新的 `<任务 ID>-before.zip`；
- 首个增量任务成功后才删除旧完整 ZIP；
- 全量测试、`git diff --check`、导出独立审计和恢复演练全部通过。

## 7. 实施边界

本次实施只修改 `keyword_union` 导出、事务恢复工具、Git 初始化与自动提交、测试和技能文档。重分类、Vault 重组和旧逐篇治理工作流继续使用各自现有快照机制，不在本次改造中统一重写。

正式 Vault 的 Git 初始化必须在代码和临时 Vault 测试通过后执行。初始化完成后先验证跟踪边界和基线提交，再用一个真实关键词任务验收增量快照；在此之前保留当前完整快照作为迁移保护。
