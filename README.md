# 印象笔记中国版 Skill

通过印象笔记中国版 NoteStore API 搜索、读取和整理笔记，并把正文、图片和附件导出为 Obsidian 可用的 Markdown。仓库同时提供创建、更新、移入废纸篓等写操作；永久删除设有独立的强确认参数。

## 环境准备

需要 Python 3.9+ 和印象笔记 Developer Token：

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑仓库根目录的 `.env`：

```dotenv
EVERNOTE_TOKEN=your-developer-token
EVERNOTE_NOTESTORE_URL=https://app.yinxiang.com/shard/sXX/notestore
OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian_全量同步暂存
```

`EVERNOTE_NOTESTORE_URL` 必须使用令牌页面显示的实际 shard。环境变量优先于 `.env`。真实令牌会获得账户访问权限，`.env` 已被 Git 忽略，不要把令牌写入命令、文档、日志或提交记录。

## 常用命令

所有脚本都可以在仓库根目录直接执行；使用 `--help` 查看完整参数。

### 只读查询

```powershell
# 笔记本与标签
python scripts/list_notebooks.py
python scripts/list_notebooks.py --verbose
python scripts/list_tags.py

# 搜索；支持原生语法及“标题:”“创建时间:”“any:”中文快捷写法
python scripts/search_notes.py "intitle:Agent" --max-results 10

# 查看废纸篓，不修改数据
python scripts/list_trash.py --max-count 20

# 下载一篇笔记的原始 ENML
python scripts/get_note_enml.py --guid "NOTE_GUID" --output ".\note.xml"
```

### 搜索并导出到 Obsidian

以下单领域命令适合少量结果。它分别搜索 AI、Agent、人工智能；搜索关键词只用于产生候选，脚本会逐篇拉取完整正文，确认正文主旨属于 AI 后才选择并导出前三篇：

```powershell
python scripts/export_search_results.py `
  --since 2025-07-26 `
  --until 2025-08-26 `
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"
```

`--since` 包含当日，`--until` 不包含当日，因此两者可表达稳定的左闭右开创建时间区间。使用 `--limit all` 可导出全部候选；此时应把 `--max-per-keyword` 设为足够大的值，并确认命令输出中每个关键词的“共 N 条”与“拉取 N 条候选”一致，避免候选上限造成遗漏。

导出顺序固定为：合并 GUID 并排序候选、通过 API 拉取完整正文和资源、判断正文主旨、对审核通过项按完全一致标题去重、应用 `--limit`，最后才写入 Markdown 和附件。标题或搜索关键词命中不能代替正文判断；目标领域证据不足、其他领域明显占优或无法确定主领域时，脚本会输出跳过原因和正文证据，不写入 Markdown 或附件，也不占用导出名额。若最新的同标题剪藏错域，脚本会继续检查较旧版本，直到找到正文匹配的版本或耗尽该标题候选。

通过门禁的同标题文章依次按 `updated`、`created`、GUID 保留最新版本。文章按 `created` 归入 `YYYY年MM月/`；图片和附件统一保存在知识库根目录 `_attachments/`，月度文章使用 `../_attachments/`。同名附件内容不同时会自动追加内容哈希，正文已经引用的图片不会在文末重复展示。

导出的文章只保留一个一级标题，frontmatter 不再重复写 `title` 属性；正文标题从二级开始，连续空行会压缩为一个空行。印象笔记代码块中的原始换行会保留，图片、链接、列表和表格仍使用标准 Markdown。

根目录自动重建 `目录索引.md`。每篇索引项包含可点击链接、可读的相对位置，以及由首段有效正文和最多四个二、三级目录标题综合形成的一到两句话简介。重复运行会迁移根目录旧文章、清理同标题旧版本并重建索引，不产生重复条目。

```text
30_精选资料/AI/
├── 目录索引.md
├── _attachments/
└── 2026年07月/
    ├── 一张图看懂 AI Agent 全流程.md
    └── 删掉80%的Skill，Agent反而更听话了.md
```

### 大规模多领域导出与历史解析目录

两个及以上领域、关键词重叠或全量导出时，使用任务文件驱动的编排命令：

```powershell
Copy-Item templates\multi-domain-export-job.json .state\jobs\2026-q2.json

python scripts/export_multi_domain.py `
  --job ".state\jobs\2026-q2.json" `
  --catalog ".state\export-catalog.sqlite3" `
  --rate-limit-mode wait `
  --max-rate-limit-wait 3600
```

任务中的 `since` 包含当日，`until` 不包含当日。脚本为每个关键词自动分页到服务端总数，合并 GUID 后流式获取完整正文，并在所有已知领域之间选择唯一主领域。不得用多领域标签代替唯一主领域；领域并列或任务外领域占优的文章不落盘。通过门禁后再执行全部目标领域范围内的全局标题去重。

SQLite 历史解析目录默认位于 `.state/export-catalog.sqlite3`。首次运行会扫描现有 `30_精选资料` Markdown，用已有正文自动补建历史记录；此后每次完整正文分析都会写入标题、GUID、内容摘要、正文哈希、自动领域标签、各领域得分和证据、唯一主领域、规范文件路径及审计时间。缓存以 `GUID + updated + 规则指纹` 验证，与搜索关键词无关；因此更改检索关键词后，只要正文和规则未变化，就可以复用领域判断和摘要。缓存命中的拒绝项、被新版本淘汰的同标题文章，以及已有完整规范文件的文章都不重复请求正文；确实需要重新落盘但本地正文或附件缺失时才重新读取。

限流等待、断点和报告保存在 `.state/`，不会提交到 Git。默认日志只显示汇总；JSON 报告中的 `catalog_hits`、`catalog_stale` 和 `body_requests_saved` 分别表示历史目录命中、失效和实际节省的正文请求数。

只有 `ok: true` 且索引、附件、日期范围和重复项全部通过时任务才算完成。完整性验收会检查关键词搜索是否拉全、图片和附件是否存在、索引位置是否有效、领域内及跨领域重复是否为零，并区分任务日期范围内数量和目录现存总数。

### 增量同步整个 vault

```powershell
python scripts/sync_to_obsidian.py `
  --vault "D:\path\to\vault" `
  --max-sync 50 `
  --api-delay 1

# 仅同步一个笔记本，并自定义状态文件
python scripts/sync_to_obsidian.py `
  --vault "D:\path\to\vault" `
  --notebook "笔记本名" `
  --state-file "D:\path\to\sync-state.json"
```

未传 `--vault` 时读取 `OBSIDIAN_VAULT_PATH`。默认状态文件为 `<vault>/.yinxiang_sync_state.json`。同步按 NoteStore 元数据分页拉取，不按标题丢弃笔记；每个笔记本下分别创建 `_attachments/` 和 `_clips/`。超过 200 KB 的网页裁剪可保存为 HTML，其余正文转为 Markdown。

全量同步会按印象笔记本名称创建目录，因此只能写入独立暂存目录；检测到统一 LLM Wiki 根目录时脚本会在读取凭据前拒绝执行。进入正式 Wiki 的内容使用上面的精选导出命令，并显式指定 `--domain` 和领域目标目录。

生成的 frontmatter 示例：

```yaml
---
created: "2026-07-26 08:30:00"
updated: "2026-07-26 09:45:00"
source: "Evernote"
source_guid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
notebook: "AI 知识库"
type: "inline-images"
---
```

## 统一 LLM Wiki 结构

迁移只作用于本地 Obsidian vault，不访问印象笔记帐号。先预览迁移计划，再在用户明确授权后执行；执行会创建 ZIP 快照，验证失败不会删除旧目录。

唯一有效的生命周期目录是：

```text
@_Obsidian/
├── 01_收件箱/
├── 10_项目/
├── 20_知识笔记/
├── 30_精选资料/
├── 80_系统/
├── 90_归档/
└── 99_废纸篓/
```

重组脚本会把旧 `90_系统`自动迁入 `80_系统`，把旧 `99_归档`自动迁入 `90_归档`，并创建 `99_废纸篓`。预检发现同路径异内容或文件类型冲突时，会在创建快照和迁移写入前中止。

```powershell
# 预览：只读本地 vault
python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian"

# 执行：创建 ZIP 快照并重组目录
python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --apply --confirm MIGRATE_OBSIDIAN_VAULT

# 验证：只检查最终结构、清单和链接
python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --verify
```

后续精选导出写入对应领域资料目录：

```powershell
python scripts/export_search_results.py `
  --since 2025-07-27 `
  --until 2025-08-27 `
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"
```

最终结构、索引职责、审核规则和旧标签映射见 `references/obsidian-knowledge-management.md`。其中 `20_知识笔记` 只保留目录索引和知识地图两份根索引，`30_精选资料` 的每个领域各自维护一份目录索引。

### 精选资料逐篇审阅

`curate_selected_materials.py` 根据显式 JSON 清单逐篇核对领域归属，并维护受控双向链接。错域资料移入 `99_废纸篓/30_精选资料/` 的镜像路径，引用的本地附件同步复制；保留资料每篇最多写入 3 条人工确认的双向链接，没有明确关联时不写链接块。执行前会创建 ZIP 快照和 SHA-256 清单，完成后重建领域索引并生成逐篇审核日志。

```powershell
# 预览
python scripts/curate_selected_materials.py --vault "D:\OneDrive\文档\@_Obsidian" --review "reviews\2026-07-27-selected-materials-review.json"

# 执行
python scripts/curate_selected_materials.py --vault "D:\OneDrive\文档\@_Obsidian" --review "reviews\2026-07-27-selected-materials-review.json" --apply --confirm CURATE_SELECTED_MATERIALS

# 验证
python scripts/curate_selected_materials.py --vault "D:\OneDrive\文档\@_Obsidian" --review "reviews\2026-07-27-selected-materials-review.json" --verify
```

## 写操作与安全边界

只有在明确需要修改账户数据时才运行这些命令：

```powershell
# 创建
python scripts/create_note.py `
  --title "标题" `
  --content "<en-note>内容</en-note>" `
  --notebook "笔记本名" `
  --tags "标签1,标签2"

# 更新；必须至少指定一项变化
python scripts/update_note.py `
  --guid "NOTE_GUID" `
  --title "新标题" `
  --add-tags "标签1"

# 省略 --confirm 时只预览；加上后移入废纸篓，仍可恢复
python scripts/delete_note.py --guid "NOTE_GUID"
python scripts/delete_note.py --guid "NOTE_GUID" --confirm
```

永久清空废纸篓必须完整输入固定确认词，执行后无法恢复：

```powershell
python scripts/empty_trash.py --confirm DELETE_ALL
```

## 脚本一览

| 脚本 | 功能 | 数据影响 |
|---|---|---|
| `list_notebooks.py` | 列出笔记本，可选逐本计数 | 只读 |
| `list_tags.py` | 列出标签 | 只读 |
| `search_notes.py` | 搜索笔记元数据 | 只读 |
| `get_note_enml.py` | 下载原始 ENML 到本地 | 只读账户；写本地文件 |
| `export_search_results.py` | 搜索并导出 Markdown、图片、附件 | 只读账户；写本地文件 |
| `export_multi_domain.py` | 多领域全量搜索、历史解析复用、唯一归属和验收 | 只读账户；写本地 vault 和 `.state/` |
| `export_catalog.py` | 维护本地 SQLite 历史解析目录 | 只读本地 |
| `export_integrity.py` | 验证索引、附件、范围和跨领域重复 | 只读本地 |
| `sync_to_obsidian.py` | 增量同步全部或指定笔记本 | 只读账户；写本地 vault |
| `create_note.py` | 创建笔记 | 修改账户 |
| `update_note.py` | 更新标题、内容、标签 | 修改账户 |
| `delete_note.py` | 预览或移入废纸篓 | `--confirm` 时修改账户 |
| `list_trash.py` | 查看废纸篓 | 只读 |
| `empty_trash.py` | 永久清空废纸篓 | 不可恢复 |

## 测试

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q scripts tests
git diff --check
```

真实账号验证只应运行只读命令。创建、更新、删除和清空废纸篓使用假客户端和命令行测试验证，避免破坏账户数据。

## 已知边界

- Developer Token 可能过期或被撤销；遇到鉴权错误时重新生成，并同步更新对应的 NoteStore URL。
- API 有调用频率限制。`--api-delay` 和 `--max-sync` 用于主动控制请求节奏，但脚本不会替服务端保证“不限流”。
- `update_note.py --content` 接收完整 ENML，不是 Markdown；无效 ENML 会由服务端拒绝。

## 许可证

MIT
