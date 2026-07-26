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

脚本按 GUID 去重，导出 Markdown、图片和附件。完成后核对：

1. Markdown 数量等于预期导出数。
2. `_attachments/` 中的文件存在且非空。
3. 每个 `_attachments/...` 引用都有对应文件。
4. 同标题不同 GUID、同名不同内容附件均未被覆盖。

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
| Markdown 没图片 | `getNote` 是否请求资源数据；引用路径与 `_attachments/` 是否一致 |
| 同名笔记被覆盖 | frontmatter 中 `source_guid` 是否不同；输出名是否带 GUID 后缀 |
| 同名附件只剩一个 | 文件名冲突时是否追加内容哈希 |
| 同步漏笔记 | 是否分页读取元数据；不要按标题去重 |

完整参数和实现说明见 `python scripts/<脚本>.py --help` 与 `README.md`。
