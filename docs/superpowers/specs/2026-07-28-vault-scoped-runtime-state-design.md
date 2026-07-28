# Obsidian Vault 内运行状态与跨设备配置设计

## 背景

调整前，仓库没有统一的正式 Obsidian Vault 配置入口：多领域任务文件保存设备相关的绝对 `vault` 路径，单领域导出依赖 `--target`，知识库管理脚本依赖 `--vault`，而 `OBSIDIAN_VAULT_PATH` 被全量同步脚本当作暂存目录使用。大规模导出的 SQLite 历史解析目录、断点和报告也曾保存在代码仓库的 `.state/`，无法随 Obsidian 知识库跨设备同步。

当前契约将 `OBSIDIAN_VAULT_PATH` 定义为每台设备本地配置的正式 Obsidian Vault 根目录。任务文件不再保存设备路径，运行状态统一进入 Vault 内的隐藏命名空间，并继续把账号凭据留在各设备本地。

## 目标

1. `OBSIDIAN_VAULT_PATH` 成为正式 Vault 的全局默认路径，系统环境变量优先于仓库 `.env`。
2. 同一份多领域任务 JSON 能在 Vault 路径不同的设备上直接使用。
3. 历史解析目录、断点、报告、任务文件和单领域审核状态随 Vault 同步。
4. 全量同步暂存区与正式 Vault 使用不同配置，禁止混用。
5. 首次运行可无损复制仓库旧 `.state/`，验证新位置后再切换读取来源。
6. 明确 SQLite 跨设备使用边界，避免两台设备同时写入。

## 非目标

- Token 和 `.env` 不随 Vault 同步；Developer Token、NoteStore URL 和 `.env` 都只留在当前设备。
- 不允许全量同步直接写入统一知识库。
- 不承诺 OneDrive 锁文件具备实时分布式锁语义。
- 不自动删除仓库旧 `.state/`。
- 不把 `.state/` 内容纳入 Git。

## 配置模型

### 正式 Vault

每台设备在仓库根目录 `.env` 或系统环境变量中配置：

```dotenv
OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian
```

`OBSIDIAN_VAULT_PATH` 是每台设备的正式 Vault 根目录。不同设备的本地绝对路径可以不同，不得把该路径固化到任务 JSON。

共享运行时新增 `load_vault_root()`。它使用现有 `load_setting()` 的优先级读取配置，并执行以下校验：

1. 配置非空；
2. 路径存在且是目录；
3. 目录包含 `.obsidian`；
4. 路径不是 `30_精选资料` 等生命周期子目录。

命令行保留 `--vault` 或 `--target` 作为显式覆盖入口，便于测试和特殊维护。覆盖路径必须通过同一套 Vault 边界校验；默认执行只依赖 `OBSIDIAN_VAULT_PATH`。

### 全量同步暂存区

新增独立配置：

```dotenv
YINXIANG_SYNC_VAULT_PATH=D:\OneDrive\文档\@_Obsidian_全量同步暂存
```

`YINXIANG_SYNC_VAULT_PATH` 是独立的全量同步暂存目录，不能与 `OBSIDIAN_VAULT_PATH` 指向同一位置。

`sync_to_obsidian.py` 未传 `--vault` 时只读取 `YINXIANG_SYNC_VAULT_PATH`。它不再读取 `OBSIDIAN_VAULT_PATH`，并继续拒绝写入具有统一 LLM Wiki 标记的正式 Vault。

### `.env.example`

示例文件包含以下三类配置，注释必须区分用途：

```dotenv
EVERNOTE_TOKEN=your-developer-token
EVERNOTE_NOTESTORE_URL=https://app.yinxiang.com/shard/sXX/notestore

# 正式 Obsidian 知识库根目录；每台设备路径可以不同。
OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian

# 可选：全量同步使用的独立暂存目录，不能指向正式知识库。
YINXIANG_SYNC_VAULT_PATH=D:\OneDrive\文档\@_Obsidian_全量同步暂存
```

## 任务模型

任务 JSON 不保存 `vault`，只保存日期、领域和关键词。`load_job()` 从本机全局配置取得 Vault，再构造 `ExportJob`。

旧任务文件中的 `vault` 字段继续允许读取，但视为已废弃：旧字段会被忽略，脚本输出一次警告，不比较路径，也不让旧设备路径阻断新设备执行。为了让任务 ID 跨设备稳定，任务 ID 只包含日期、领域、关键词和任务格式版本，不包含 Vault 绝对路径；运行状态文件位于本机配置的 Vault，因此不同设备能用同一任务 ID 定位同步后的断点。

任务模板存放于：

```text
<vault>/.state/yinxiang-notes/jobs/
```

仓库中的模板仍作为初始来源，但复制后的任务文件不包含绝对路径。

## 状态目录

正式结构为：

```text
<vault>/
└─ .state/
   └─ yinxiang-notes/
      ├─ export-catalog.sqlite3
      ├─ jobs/
      ├─ runs/
      ├─ reports/
      ├─ single-domain/
      ├─ migrations/
      └─ active-run.lock
```

各路径职责如下：

| 路径 | 内容 |
|---|---|
| `export-catalog.sqlite3` | 标题、GUID、摘要、正文指纹、领域分析和规范文件位置 |
| `jobs/` | 可跨设备复用的多领域任务 JSON |
| `runs/` | 当前任务逐篇提交的断点 |
| `reports/` | 完整性验收和 API 节省统计 |
| `single-domain/` | 单领域审核与续跑状态 |
| `migrations/` | 旧状态迁移清单、来源路径和 SHA-256 |
| `active-run.lock` | 当前写入设备、进程和启动时间 |

`.state/` 是 Vault 的机器状态区，不进入 `目录索引.md`、知识地图或正文链接。文档不要求用户在 Obsidian 中直接编辑其中内容。

## 脚本行为

### 多领域导出

`export_multi_domain.py` 从 `OBSIDIAN_VAULT_PATH` 取得根目录，默认派生：

```text
catalog = <vault>/.state/yinxiang-notes/export-catalog.sqlite3
state   = <vault>/.state/yinxiang-notes/runs/multi-export-<task-id>.json
report  = <vault>/.state/yinxiang-notes/reports/<task-id>.json
```

显式 `--catalog`、`--state-file` 和 `--report-file` 继续可用，但写路径必须位于 `<vault>/.state/yinxiang-notes/`，防止状态再次散落到仓库或正文目录。

### 单领域导出

`export_search_results.py` 未传 `--target` 时，根据 `--domain` 派生：

```text
target = <vault>/30_精选资料/<domain>
state  = <vault>/.state/yinxiang-notes/single-domain/export-<domain>.json
```

显式 `--target` 必须位于 `<vault>/30_精选资料/<domain>`，不能指向其他生命周期目录。

### 知识库管理脚本

重组、审核和验证命令的 `--vault` 改为可选。未传时读取 `OBSIDIAN_VAULT_PATH`；显式路径仍接受同样的 Vault 根校验。

## 旧状态迁移

共享运行时提供幂等的迁移函数。第一次需要状态目录的命令执行以下步骤：

1. 创建 Vault 新状态目录；
2. 扫描仓库根目录旧 `.state/`；
3. 只复制已知文件：`export-catalog.sqlite3`、`export-*.json`、`multi-export-*.json`、`jobs/*.json` 和 `reports/*.json`；
4. 目标不存在时复制；目标存在且 SHA-256 相同时跳过；
5. 目标存在但内容不同时停止迁移并报告冲突，不覆盖任何一方；
6. 写入 `migrations/<timestamp>.json`，记录源、目标、大小和 SHA-256；
7. 验证所有目标文件后，后续运行只读取 Vault 新位置。

迁移采用复制而非移动，即复制旧状态，不删除旧状态。仓库旧 `.state/` 继续保留，用户确认跨设备同步正常后再自行清理。

## 多设备并发

写入 SQLite 前以独占创建方式生成 `active-run.lock`，内容包括设备名、进程号、任务 ID 和开始时间。正常结束时删除锁。

若锁存在：

- 当前设备的进程仍存活：拒绝启动第二个写任务；
- 锁来自其他设备，或无法验证进程：拒绝自动覆盖，并显示设备与时间；
- 当前导出命令不自动覆盖陈旧锁；必须先确认上一任务已经结束且同步完成，再单独处理陈旧锁。

OneDrive 可能延迟同步锁文件，因此该机制只能降低冲突概率，不能提供严格分布式互斥。操作规则固定为：上一台设备运行结束并完成同步后，才能在另一台设备启动导出。

禁止两台设备同时写入同一个 Vault。切换设备前必须等待上一台设备完成 Vault 同步，并确认 SQLite 已关闭；`active-run.lock` 不能替代这条操作纪律。

SQLite 保持默认回滚日志模式，不启用 WAL，避免跨设备同步时遗漏 `-wal` 或 `-shm` 文件。目录数据库关闭后才视为该设备本轮写入完成。

## 错误处理

- 缺少 `OBSIDIAN_VAULT_PATH`：在加载凭据和调用 API 前终止。
- Vault 不存在或没有 `.obsidian`：在任何文件写入前终止。
- 状态迁移冲突：保留新旧文件并终止，报告精确路径和哈希。
- 活跃锁冲突：不打开 SQLite、不请求正文。
- 状态目录无法写入：不退回仓库 `.state/`，直接失败。
- 全量同步暂存区指向正式 Vault：在读取凭据前拒绝。

## 测试策略

1. 配置测试：环境变量覆盖 `.env`，缺失、子目录和无 `.obsidian` 路径均被拒绝。
2. 任务测试：新任务不含 `vault`；旧字段被忽略；任务 ID 不受设备路径影响。
3. 路径测试：多领域、单领域、报告和目录数据库均落在 Vault 命名空间。
4. 迁移测试：首次复制、重复执行、同内容跳过、不同内容冲突和迁移清单。
5. 并发测试：活跃锁、陈旧锁恢复和异常退出清理。
6. 全量同步测试：只读取 `YINXIANG_SYNC_VAULT_PATH`，继续拒绝正式 Vault。
7. 文档与 Skill 测试：`.env.example`、README、SKILL 和任务模板使用同一配置契约。
8. 回归测试：完整仓库测试、命令 `--help`、UTF-8 模板解析、凭据扫描和 `git diff --check`。

## 成功标准

- 同一任务文件可在 Vault 路径不同的两台设备上加载。
- 所有精选导出状态默认位于 `<vault>/.state/yinxiang-notes/`。
- 首次运行可无损复用仓库旧状态，且不删除源文件。
- 正式 Vault 与全量同步暂存区配置不会混用。
- 并发锁冲突发生在打开目录数据库和请求正文之前。
- `.env.example`、README、SKILL、模板和脚本行为一致。
