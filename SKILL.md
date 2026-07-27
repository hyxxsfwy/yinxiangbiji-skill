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

在 `.env` 中填写令牌页面显示的 `EVERNOTE_TOKEN` 和 `EVERNOTE_NOTESTORE_URL`。`OBSIDIAN_VAULT_PATH` 只用于全量同步的独立暂存目录，不能指向统一 LLM Wiki 根目录。环境变量优先。

## 快速参考

| 需求 | 命令 | 账户影响 |
|---|---|---|
| 列笔记本 | `python scripts/list_notebooks.py` | 只读 |
| 列标签 | `python scripts/list_tags.py` | 只读 |
| 搜索 | `python scripts/search_notes.py "intitle:Agent" --max-results 10` | 只读 |
| 查看废纸篓 | `python scripts/list_trash.py --max-count 20` | 只读 |
| 下载 ENML | `python scripts/get_note_enml.py --guid "GUID" --output ".\note.xml"` | 只读账户 |
| 全量同步到暂存区 | `python scripts/sync_to_obsidian.py --vault "D:\OneDrive\文档\@_Obsidian_全量同步暂存"` | 只读账户 |
| 创建 | `python scripts/create_note.py --title "标题" --content "<en-note>内容</en-note>"` | 修改账户 |
| 更新 | `python scripts/update_note.py --guid "GUID" --title "新标题"` | 修改账户 |
| 移入废纸篓 | `python scripts/delete_note.py --guid "GUID" --confirm` | 修改账户 |
| 永久清空 | `python scripts/empty_trash.py --confirm DELETE_ALL` | 不可恢复 |
| 预览 vault 重组 | `python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian"` | 只读本地 |
| 执行 vault 重组 | `python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --apply --confirm MIGRATE_OBSIDIAN_VAULT` | 修改本地 vault |
| 验证 vault 结构 | `python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --verify` | 只读本地 |
| 预览精选资料审阅 | `python scripts/curate_selected_materials.py --vault "D:\OneDrive\文档\@_Obsidian" --review "reviews\审阅清单.json"` | 只读本地 |
| 执行精选资料审阅 | `python scripts/curate_selected_materials.py --vault "D:\OneDrive\文档\@_Obsidian" --review "reviews\审阅清单.json" --apply --confirm CURATE_SELECTED_MATERIALS` | 修改本地 vault |
| 验证精选资料审阅 | `python scripts/curate_selected_materials.py --vault "D:\OneDrive\文档\@_Obsidian" --review "reviews\审阅清单.json" --verify` | 只读本地 |

## 搜索并导出

涉及“最近一年、多个关键词、导出前 N 篇”时，直接使用组合命令：

```powershell
python scripts/export_search_results.py `
  --since 2025-07-26 `
  --until 2025-08-26 `
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"
```

`--since` 包含当日，`--until` 不包含当日。导出完整时间区间时使用 `--limit all`，同时提高 `--max-per-keyword`，并确认每个关键词的总命中数与实际拉取数一致。

输出契约：

- 先按 GUID 合并搜索命中，再对标题完全一致的剪藏去重；依次按 `updated`、`created`、GUID 保留最新版本，最后应用 `--limit`。
- 文章按笔记 `created` 归入 `YYYY年MM月/`，例如 `2026年07月/`。
- 根目录生成 `目录索引.md`；每项包含文档位置，以及由首段有效正文和二、三级目录大纲综合生成的一到两句话简介。
- 附件保留在根目录 `_attachments/`，月度文章使用 `../_attachments/`。

完成后核对：

1. 根目录没有散落的文章 Markdown，文章均位于月份目录。
2. `目录索引.md` 的条目数等于唯一标题数，链接可打开且简介非空。
3. 每个 `../_attachments/...` 引用都有对应文件。
4. 同标题文章只保留按上述新旧规则选中的一篇；同名不同内容附件仍分别存在。

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
| 目录索引缺文章 | 文章是否有可解析的 `created`、`updated` 和 `source_guid` |
| 同名附件只剩一个 | 文件名冲突时是否追加内容哈希 |
| 整库同步漏笔记 | 是否分页读取元数据；整库同步不按标题去重，组合导出才按标题去重 |

完整参数和实现说明见 `python scripts/<脚本>.py --help` 与 `README.md`。
