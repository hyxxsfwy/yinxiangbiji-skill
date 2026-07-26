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

在 `.env` 中填写令牌页面显示的 `EVERNOTE_TOKEN` 和 `EVERNOTE_NOTESTORE_URL`。可用 `OBSIDIAN_VAULT_PATH` 设置默认 vault。环境变量优先。

## 快速参考

| 需求 | 命令 | 账户影响 |
|---|---|---|
| 列笔记本 | `python scripts/list_notebooks.py` | 只读 |
| 列标签 | `python scripts/list_tags.py` | 只读 |
| 搜索 | `python scripts/search_notes.py "intitle:Agent" --max-results 10` | 只读 |
| 查看废纸篓 | `python scripts/list_trash.py --max-count 20` | 只读 |
| 下载 ENML | `python scripts/get_note_enml.py --guid "GUID" --output ".\note.xml"` | 只读账户 |
| 同步 vault | `python scripts/sync_to_obsidian.py --vault "D:\vault"` | 只读账户 |
| 创建 | `python scripts/create_note.py --title "标题" --content "<en-note>内容</en-note>"` | 修改账户 |
| 更新 | `python scripts/update_note.py --guid "GUID" --title "新标题"` | 修改账户 |
| 移入废纸篓 | `python scripts/delete_note.py --guid "GUID" --confirm` | 修改账户 |
| 永久清空 | `python scripts/empty_trash.py --confirm DELETE_ALL` | 不可恢复 |

## 搜索并导出

涉及“最近一年、多个关键词、导出前 N 篇”时，直接使用组合命令：

```powershell
python scripts/export_search_results.py `
  --since 2025-07-26 `
  --keywords AI Agent 人工智能 `
  --limit 3 `
  --target "D:\vault\AI相关知识库"
```

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
