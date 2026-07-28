---
name: yinxiang-notes
description: Use when a user needs to search, filter, read, export, synchronize, create, update, or delete notes in 印象笔记中国版 at app.yinxiang.com, especially when migrating Markdown, images, and attachments to Obsidian.
---

# 印象笔记中国版

## 使用原则

用仓库内的脚本访问中国版 NoteStore API。先判定操作是否只读；只有用户明确要求修改账户数据时，才运行创建、更新或删除命令。不得输出、转述或提交 Developer Token。

## 准备

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填写令牌页面显示的 `EVERNOTE_TOKEN` 和 `EVERNOTE_NOTESTORE_URL`。`OBSIDIAN_VAULT_PATH` 是每台设备的正式 Vault 根目录，`YINXIANG_SYNC_VAULT_PATH` 是独立的全量同步暂存目录；两者不能指向同一位置。环境变量优先于 `.env`，每台设备分别维护自己的路径。PowerShell 不会自动把 `.env` 注入 `$env:`；Python 脚本通过 `scripts.runtime` 加载配置。Token 和 `.env` 不随 Vault 同步，不得把凭据写入 Vault、命令、文档、日志或提交。

## 快速参考

| 需求 | 命令 | 账户影响 |
|---|---|---|
| 列笔记本 | `python scripts/list_notebooks.py` | 只读 |
| 列标签 | `python scripts/list_tags.py` | 只读 |
| 搜索 | `python scripts/search_notes.py "intitle:Agent" --max-results 10` | 只读 |
| 查看废纸篓 | `python scripts/list_trash.py --max-count 20` | 只读 |
| 下载 ENML | `python scripts/get_note_enml.py --guid "GUID" --output ".\note.xml"` | 只读账户 |
| 全量同步到暂存区 | `python scripts/sync_to_obsidian.py` | 只读账户 |
| 大规模多领域导出 | `$vault = python -c "from scripts.runtime import load_vault_root; print(load_vault_root())"; python scripts/export_multi_domain.py --job "$vault\.state\yinxiang-notes\jobs\任务.json"` | 只读账户；修改正式 Vault |
| 创建 | `python scripts/create_note.py --title "标题" --content "<en-note>内容</en-note>"` | 修改账户 |
| 更新 | `python scripts/update_note.py --guid "GUID" --title "新标题"` | 修改账户 |
| 移入废纸篓 | `python scripts/delete_note.py --guid "GUID" --confirm` | 修改账户 |
| 永久清空 | `python scripts/empty_trash.py --confirm DELETE_ALL` | 不可恢复 |
| 预览 vault 重组 | `python scripts/restructure_obsidian_vault.py` | 只读本地 |
| 执行 vault 重组 | `python scripts/restructure_obsidian_vault.py --apply --confirm MIGRATE_OBSIDIAN_VAULT` | 修改本地 vault |
| 验证 vault 结构 | `python scripts/restructure_obsidian_vault.py --verify` | 只读本地 |
| 预览精选资料审阅 | `python scripts/curate_selected_materials.py --review "reviews\审阅清单.json"` | 只读本地 |
| 执行精选资料审阅 | `python scripts/curate_selected_materials.py --review "reviews\审阅清单.json" --apply --confirm CURATE_SELECTED_MATERIALS` | 修改本地 vault |
| 验证精选资料审阅 | `python scripts/curate_selected_materials.py --review "reviews\审阅清单.json" --verify` | 只读本地 |

## 搜索并导出

只涉及一个领域且数量较小时，使用单领域组合命令：

```powershell
$vault = python -c "from scripts.runtime import load_vault_root; print(load_vault_root())"
python scripts/export_search_results.py `
  --since 2025-07-26 `
  --until 2025-08-26 `
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "$vault\30_精选资料\AI"
```

`--since` 包含当日，`--until` 不包含当日。导出完整时间区间时使用 `--limit all`，同时提高 `--max-per-keyword`，并确认每个关键词的总命中数与实际拉取数一致。

搜索关键词只用于产生候选，标题命中不能作为落盘依据。精选导出必须按以下顺序执行：

1. 按元数据合并 GUID 并排序候选。
2. 逐篇调用 `getNote` 拉取完整正文和资源数据。
3. 判断正文主旨是否与 `--domain` 匹配；目标领域证据不足、其他领域占优或无法确定主领域时均拒绝。
4. 通过正文门禁后再按完全一致标题去重，依次按 `updated`、`created`、GUID 保留最新的匹配版本，最后应用 `--limit`。
5. 仅对审核通过的笔记写入 Markdown 和附件；拒绝项只输出标题、原因和正文证据，不创建目标文件。

不得先创建 Markdown 或保存图片后再判断领域，也不得因为标题含 AI、Agent 等词而放宽门禁。错域内容不自动搬到另一领域；若要迁入其他领域，必须以该领域重新审核。

输出契约：

- 正文匹配数量不足时继续审核后续候选，直至凑满 `--limit` 或候选耗尽；拒绝项不占导出名额。
- 文章按笔记 `created` 归入 `YYYY年MM月/`，例如 `2026年07月/`。
- 根目录生成 `目录索引.md`；每项包含文档位置，以及由首段有效正文和二、三级目录大纲综合生成的一到两句话简介。
- 附件保留在根目录 `_attachments/`，月度文章使用 `../_attachments/`。

完成后核对：

1. 根目录没有散落的文章 Markdown，文章均位于月份目录。
2. `目录索引.md` 的条目数等于唯一标题数，链接可打开且简介非空。
3. 每个 `../_attachments/...` 引用都有对应文件。
4. 同标题文章只保留按上述新旧规则选中的一篇；同名不同内容附件仍分别存在。
5. 日志中的错域或无法确定项在目标目录内没有 Markdown 和附件残留。

### 大规模多领域导出

任务涉及两个及以上领域、关键词大量重叠、要求 `all` 或预计会触发 API 限流时，必须使用 `export_multi_domain.py`，不能分别运行多个单领域命令后再人工去重。

先把 `templates/multi-domain-export-job.json` 复制到正式 Vault 的状态目录，只修改日期、领域和关键词，然后运行：

```powershell
$vault = python -c "from scripts.runtime import load_vault_root; print(load_vault_root())"
New-Item -ItemType Directory -Force `
  "$vault\.state\yinxiang-notes\jobs" | Out-Null
Copy-Item templates\multi-domain-export-job.json `
  "$vault\.state\yinxiang-notes\jobs\2026-q2.json"
python scripts/export_multi_domain.py `
  --job "$vault\.state\yinxiang-notes\jobs\2026-q2.json" `
  --rate-limit-mode wait `
  --max-rate-limit-wait 3600
```

任务 JSON 不保存 `vault`，Vault 始终来自当前设备的 `OBSIDIAN_VAULT_PATH`。旧任务中的 `vault` 等旧字段会被忽略并产生警告，不得把某台设备的绝对路径重新写回任务。

运行状态固定在 `<vault>/.state/yinxiang-notes/`：

```text
<vault>/.state/yinxiang-notes/export-catalog.sqlite3
<vault>/.state/yinxiang-notes/jobs/
<vault>/.state/yinxiang-notes/runs/
<vault>/.state/yinxiang-notes/reports/
<vault>/.state/yinxiang-notes/single-domain/
<vault>/.state/yinxiang-notes/migrations/
<vault>/.state/yinxiang-notes/active-run.lock
```

首次使用时会从仓库旧 `.state/` 复制已知文件并校验哈希。必须复制旧状态，不删除旧状态；遇到目标同名异内容时停止，不覆盖任何一份文件。迁移成功后只使用 Vault 新位置，状态会随正式 Vault 同步。

禁止两台设备同时写入同一个 Vault。锁文件不是分布式锁；切换设备前，必须先等待当前任务结束、SQLite 关闭，并等待上一台设备完成 Vault 同步，再在另一台设备启动导出。

多领域流程的固定契约：

1. 每个关键词自动分页到服务端 `totalNotes`，合并 GUID 后才请求正文；不得用候选上限代替全量分页。
2. 新任务先用现有 `30_精选资料` Markdown 自动补建 SQLite 历史解析目录，再查询目录。缓存身份是 `GUID + updated + 规则指纹`，与关键词无关；因此更改检索关键词后，未变化且按当前规则解析过的文章可以直接复用。
3. 历史目录保存标题、GUID、内容摘要、正文哈希、领域标签与得分证据、唯一主领域、规范文件路径和审计时间，不保存完整正文、附件或 Token。规则或 `updated` 变化时缓存失效；规范文件缺失或附件不完整时只为重新落盘请求正文。
4. 一个 GUID 在一次任务中只审核一次。正文统一比较全部已知领域，只允许一个唯一主领域；并列、证据不足或任务外领域占优时拒绝。不得用多领域标签代替唯一主领域，目录中的多领域标签只保留为历史分析证据。
5. 主领域判定后进行全局标题去重，全部目标领域只保留按 `updated`、`created`、GUID 选出的最新匹配版本。
6. 限流在等待预算内按服务端时长继续；超预算时状态和 SQLite 目录已经逐篇提交，可直接续跑。
7. 默认终端只显示汇总，完整搜索、审核、限流和验收结果写入 JSON。报告中的 `catalog_hits` 和 `body_requests_saved` 用于确认历史目录实际节省的正文请求。

只有报告为 `ok: true`，且索引、附件、检索范围对账和重复项全部通过，才可以声称完成。至少检查：每个关键词 `pulled == total`、缺失附件为零、领域内和跨领域重复标题/GUID 为零、索引位置全部存在、任务范围内数量与按月统计一致。目标领域既有的其他月份是历史知识库，只计入目录总量，不作为本次任务越界错误。进程退出码为零但完整性验收未通过时，只能报告部分完成。

### 关键词穷尽并集导出

当用户要求“标题或完整正文命中任一关键词就导出”，任务必须声明 `selection_mode: keyword_union`。该模式不同于高精度正文主旨门禁：它逐一搜索所有规范关键词及别名，按 GUID 合并候选，然后用 ASCII 字母数字边界和 Unicode NFKC 规则重新核验标题及完整正文。短词 `AI`、`SOL` 不得误命中 `training`、`solution`。目录归属按各目录命中的规范关键词数量决定；数量并列时使用任务文件中的目录顺序。

本次正式任务使用 `templates/keyword-union-export-job.json`，日期区间为 `[2026-04-01, 2026-08-01)`，即包含 2026-04-01、不包含 2026-08-01。模板保留用户输入的规范词 `HugginFace`，并额外搜索 `HuggingFace` 和 `Hugging Face`；报告仍归并到规范词。禁止把中文 JSON 通过 PowerShell 管道或 `python -` 传递，必须从 UTF-8 文件加载：

```powershell
$env:PYTHONUTF8 = "1"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$vault = python -c "from scripts.runtime import load_vault_root; print(load_vault_root())"
$jobDir = Join-Path $vault ".state\yinxiang-notes\jobs"
New-Item -ItemType Directory -Force -Path $jobDir | Out-Null
$job = Join-Path $jobDir "2026-04-01-to-2026-08-01-keyword-union.json"
Copy-Item -LiteralPath "templates\keyword-union-export-job.json" -Destination $job
python scripts/export_multi_domain.py `
  --job $job `
  --rate-limit-mode wait `
  --max-rate-limit-wait 3600
```

关键词分析写入 SQLite 独立表 `keyword_analyses`，不会覆盖高精度模式使用的 `parsed_notes`。缓存保存 GUID、更新时间、摘要、正文哈希、匹配证据、唯一目录、结果和规范路径，不保存完整正文、附件二进制、Token 或 NoteStore URL。每篇分析先提交 SQLite，再物化 Markdown 和附件；发生中断时使用同一命令续跑。已拒绝项和完整的已导出项不重复请求正文，已接受但文件缺失的项目只重新请求一次用于物化。

第一次正式文件写入前，脚本为任务声明的七个目录创建 `snapshots/<job-id>-before.zip` 和 SHA-256 清单。完成门禁同时要求所有查询项 `pulled == total`、每个候选都有当前 `keyword_analyses` 记录、候选恒等式成立、关键词 frontmatter 与选择指纹一致、附件和索引完整、日期无越界、领域内及跨领域重复为零，最终 JSON 报告为 `ok: true`。

退出码 75 表示限流等待预算耗尽：保留 SQLite、快照、运行状态和已物化文件，等待后使用同一命令续跑。退出码 1 表示验收未通过：必须读取 JSON 报告并修复后续跑，不得声称完成，也不得手工修改报告中的 `ok`。

## Obsidian 精选知识管理

默认精选迁移，不复制印象笔记的笔记本组、年份归档和自动采集目录；历史剪藏继续保留在印象笔记。五项迁移条件中至少两项满足时才按需迁移：正在用于项目、仍有效且不易重找、能说明保留价值、可关联或形成知识笔记、预计会再次引用。

正式 vault 只使用 `01_收件箱`、`10_项目`、`20_知识笔记`、`30_精选资料`、`80_系统`、`90_归档`和`99_废纸篓`。`80_系统`保存模板、Bases、治理资产和迁移记录；`90_归档`保存不再活跃但仍需保留的材料；`99_废纸篓`只保存待删除且可恢复的内容。运行 vault 重组命令时，脚本自动把旧 `90_系统`迁入 `80_系统`、旧 `99_归档`迁入 `90_归档`，发现同路径异内容时在写入前中止。

| 判定 | 去向 |
|---|---|
| 值得引用的原文或剪藏 | 资料层 |
| 已理解、重写或验证的内容 | 知识层 |
| 仅服务当前交付 | 项目层 |

人工字段固定为 `type`、`domain`、`status`、`tags`。标签只表达主题，每篇笔记最多 3 个标签，且只能使用受控主题词表；`_Apps` 转为来源属性，任务标签转为状态属性，个人状态不进入知识库。

详细规则与模板：`references/obsidian-knowledge-management.md`、`templates/obsidian-source-note.md`、`templates/obsidian-knowledge-note.md`、`templates/obsidian-knowledge-map.md`。

### 精选资料逐篇治理

审阅清单必须逐篇给出 `path`、`decision`、`reason`、`topic` 和 `links`。内容与所在领域不符时使用 `trash`，脚本把 Markdown 移入 `99_废纸篓/30_精选资料/` 的镜像路径，并复制其本地附件，不能用跨领域搬运掩盖错域。保留文档的自动关联必须人工确认语义相关、严格双向且每篇不超过 3 条；没有明确关联时保持为空。执行前创建带 SHA-256 清单的 ZIP 快照，执行后重建领域索引并写入逐篇审核日志。

### LLM Wiki 半自动审核

- 原始资料正文只读；AI 只能直接维护知识地图的自动区域。
- `llm_policy: strict` 只允许建议；`llm_policy: off` 禁止处理。
- 自动审批须通过白名单、可定位证据、受控词表、链接消歧、幂等性、独立审核、确定性校验、日志和可回滚检查；同名或多候选链接存在歧义时不得自动审批，进入人工队列。
- 新永久标签、人工结论、合并、移动、重命名、删除和提升常青状态必须人工审批。
- 每篇知识笔记只保留 3 至 7 个语义明确的高价值链接。

## 安全边界

- 未明确授权写操作：只运行列表、搜索、读取、导出和同步命令。
- `delete_note.py` 省略 `--confirm` 时仅预览。
- `empty_trash.py` 只有固定确认词 `DELETE_ALL` 才会调用永久删除；仍须获得用户明确授权。
- 真实账号不用于创建、更新、删除的回归测试。
- API 限流时保留状态并稍后重试，不声称脚本能自动消除服务端限流。

## 常见问题

| 症状 | 检查 |
|---|---|
| 鉴权失败 | Token 是否过期；URL 的 shard 是否与令牌页面一致 |
| Markdown 没图片 | `getNote` 是否请求资源数据；月度文章是否使用 `../_attachments/` |
| 重复剪藏仍出现 | 是否在 `--limit` 前按完全一致标题比较 `updated`、`created`、GUID |
| 标题相关但正文错域 | 是否先拉取完整正文并通过正文主旨门禁；拒绝项不得写入 Markdown 或附件 |
| 新关键词又重复拉正文 | 是否使用 `<vault>/.state/yinxiang-notes/export-catalog.sqlite3`；GUID、updated 或规则指纹是否变化 |
| 同一文章进入多个领域 | 是否使用多领域编排器选择唯一主领域并执行全局标题去重 |
| 目录索引缺文章 | 文章是否有可解析的 `created`、`updated` 和 `source_guid` |
| 同名附件只剩一个 | 文件名冲突时是否追加内容哈希 |
| 整库同步漏笔记 | 是否分页读取元数据；整库同步不按标题去重，组合导出才按标题去重 |
| 换设备后状态缺失 | 是否等待上一台设备完成 Vault 同步；本机 `OBSIDIAN_VAULT_PATH` 是否指向已同步的正式 Vault |
| Vault 写锁冲突 | 禁止覆盖 `active-run.lock`；确认另一设备任务已结束并完成同步后再处理陈旧锁 |

完整参数和实现说明见 `python scripts/<脚本>.py --help` 与 `README.md`。
