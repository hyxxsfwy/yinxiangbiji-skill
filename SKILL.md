---
name: yinxiang-notes
description: Use when a user needs 印象笔记中国版 note operations or local Obsidian governance, including export or sync, reclassify vault content, rebuild an index, or maintain bidirectional links.
---

# 印象笔记中国版与 Obsidian 治理

## 核心原则

使用仓库脚本访问中国版 NoteStore API，并把本地知识库操作限制在配置的 Vault 内。先判断任务是否只读；只有用户明确授权时才执行账户或 Vault 写入。

详细规则按任务加载，不在入口重复：

- 导出、唯一领域、全局去重、断点续跑与验收：`references/export-workflows.md`
- 精选资料逐篇决策、双向链接与审核：`references/selected-materials-governance.md`
- Obsidian 目录、Properties、索引与 LLM Wiki：`references/obsidian-knowledge-management.md`

精选资料固定受管十二领域：AI、Quant、信息技术、投资理财、知识管理、健康医学、中医、两性情感、个人成长、科技产业、自然科学、历史与社会。

## 凭据与路径边界

### Developer Token 预检与更新

每次真实账号任务开始前，先运行只读命令 `python scripts/list_notebooks.py` 验证 Token；连续任务跨天时，每天首次访问前重新验证。不得输出、转述或记录 Token 与 NoteStore URL。

若返回 `AUTH_EXPIRED` 或 `EDAMUserException(errorCode=9, parameter='authenticationToken')`，停止全部账号写操作，并按以下步骤更新：

1. 在浏览器登录需要操作的印象笔记中国版账号。
2. 打开 [Developer Token 页面](https://app.yinxiang.com/api/DeveloperToken.action)，按页面提示生成或更新 Token。
3. 将页面提供的 Developer Token 和 NoteStore URL 分别写入仓库根目录 `.env` 的 `EVERNOTE_TOKEN`、`EVERNOTE_NOTESTORE_URL`；只在本地替换，不发送到聊天、日志、Vault 或 Git。
4. 重新运行只读预检；只有预检成功后，才继续创建、更新、删除或导出任务。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 配置 `EVERNOTE_TOKEN`、`EVERNOTE_NOTESTORE_URL`、`OBSIDIAN_VAULT_PATH` 和 `YINXIANG_SYNC_VAULT_PATH`。正式 Vault 与全量同步暂存目录不能相同；PowerShell 不会自动把 `.env` 注入 `$env:`，Python 脚本通过 `scripts.runtime` 加载配置。

不得输出、转述、记录或提交 Developer Token、NoteStore URL 与 `.env`。Token 不写入 Vault、任务 JSON、命令、日志或文档。

## 快速任务路由

| 任务 | reference / 命令 | 影响 |
|---|---|---|
| 列笔记本或标签 | `python scripts/list_notebooks.py` / `python scripts/list_tags.py` | 只读账户 |
| 搜索或读取 | `python scripts/search_notes.py --help` / `python scripts/get_note_enml.py --help` | 只读账户 |
| 查看废纸篓 | `python scripts/list_trash.py --help` | 只读账户 |
| 全量同步到独立暂存区 | `python scripts/sync_to_obsidian.py --help` | 只读账户；写暂存区 |
| 单领域精选导出 | `references/export-workflows.md` → `python scripts/export_search_results.py --help` | 只读账户；写正式 Vault |
| 多领域或关键词并集导出 | `references/export-workflows.md` → `python scripts/export_multi_domain.py --help` | 只读账户；写正式 Vault 与状态 |
| 创建或更新笔记 | `python scripts/create_note.py --help` / `python scripts/update_note.py --help` | 修改账户 |
| 移入账户废纸篓 | `python scripts/delete_note.py --help` | 修改账户 |
| 永久清空账户废纸篓 | `python scripts/empty_trash.py --confirm DELETE_ALL` | 不可恢复 |
| 预览 vault 重组 | `python scripts/restructure_obsidian_vault.py` | 只读本地 |
| 执行 vault 重组 | `python scripts/restructure_obsidian_vault.py --apply --confirm MIGRATE_OBSIDIAN_VAULT` | 修改本地 Vault |
| 验证 vault 结构 | `python scripts/restructure_obsidian_vault.py --verify` | 只读本地 |
| 预演领域契约迁移 | `python scripts/migrate_domain_taxonomy.py preview` | 只读本地 |
| 执行领域契约迁移 | `python scripts/migrate_domain_taxonomy.py apply --confirm EXPAND_MANAGED_DOMAINS` | 修改本地 Vault；增量事务可回滚 |
| 验证领域契约迁移 | `python scripts/migrate_domain_taxonomy.py verify` | 只读业务资料 |
| 重扫并审计精选资料归类 | `references/selected-materials-governance.md` → `python scripts/reclassify_selected_materials.py audit` | 只读本地；写审计报告 |
| 执行重分类决定 | `python scripts/reclassify_selected_materials.py apply --decisions "decisions.json" --confirm RECLASSIFY_SELECTED_MATERIALS` | 修改本地 Vault |
| 验证重分类结果 | `python scripts/reclassify_selected_materials.py verify --decisions "decisions.json"` | 业务资料只读；写验证报告 |
| 应用旧逐篇清单 | `references/selected-materials-governance.md` 兼容小节 → `python scripts/curate_selected_materials.py --help` | 默认只读本地 |

完整参数以 `python scripts/<脚本>.py --help` 和 `README.md` 为准。

## 写入确认

- 未明确授权写操作时，只运行列表、搜索、读取、预览、验证和账户只读导出。
- 创建、更新、移入废纸篓必须对应用户的明确请求。
- 永久清空只接受固定确认词 `DELETE_ALL`，且仍需用户明确授权。
- Vault 重组只接受 `MIGRATE_OBSIDIAN_VAULT`。
- 固定受管领域迁移只接受 `EXPAND_MANAGED_DOMAINS`，仅自动执行“软件工程”到“信息技术”的契约迁移。
- 精选资料重分类只接受 `RECLASSIFY_SELECTED_MATERIALS`；必须先运行 `audit` 并人工确认 decisions。
- 旧逐篇清单执行只接受 `CURATE_SELECTED_MATERIALS`；默认命令仅预览，不落盘。
- 不用真实账号执行创建、更新或删除回归测试。

## 完成门禁

- 导出：只在 JSON 报告为 `ok: true`，且范围、唯一归属、标题去重、索引和附件验证全部通过后声明完成。
- 关键词并集增量事务快照：只保存本次实际变更的文件前像和 SQLite 检查点；最终验收与 Markdown-only Git 提交成功后，清理明细以 `legacy_snapshot_cleanup` 为准。
- 限流或验收失败：保留状态，报告部分完成并按 reference 续跑，不把进程结束等同于业务完成。
- Vault 重组：快照、路径、Properties、索引、链接和附件验证全部通过后才完成。
- 精选资料重分类：`audit` 已覆盖全局、`apply` 已创建快照，且独立 `verify` 的索引、双向链接和附件验证全部通过后才完成。
- 账户写入：核对目标 GUID、操作结果和用户授权范围；不可恢复操作必须单独说明。
