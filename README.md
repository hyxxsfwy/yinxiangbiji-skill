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

以下命令分别搜索 AI、Agent、人工智能，先按 GUID 合并命中，再对标题完全一致的剪藏去重，最后选择标题匹配且最近更新的前三篇：

```powershell
python scripts/export_search_results.py `
  --since 2025-07-26 `
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"
```

标题完全一致时依次按 `updated`、`created`、GUID 保留最新版本，去重发生在 `--limit` 之前。文章按 `created` 归入 `YYYY年MM月/`；图片和附件统一保存在知识库根目录 `_attachments/`，月度文章使用 `../_attachments/`。同名附件内容不同时会自动追加内容哈希，正文已经引用的图片不会在文末重复展示。

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
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"
```

最终结构、索引职责、审核规则和旧标签映射见 `references/obsidian-knowledge-management.md`。其中 `20_知识笔记` 只保留目录索引和知识地图两份根索引，`30_精选资料` 的每个领域各自维护一份目录索引。

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
