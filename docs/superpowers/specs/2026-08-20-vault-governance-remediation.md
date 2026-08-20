# Obsidian Vault 治理问题整改规格

## 目标

修复 2026-08-20 对正式 Vault `D:\OneDrive\文档\@_Obsidian` 审计发现的真实治理缺口，同时消除 LLM Wiki 与历史结构验证中的确定性误报。

## 范围

- 在 Vault 根目录安装现行 `AGENTS.md` Schema。
- 为 `Codex CLI 使用技巧记录.md` 增加可解析到精选资料的 `sources`。
- 将 Quant 资料中的过期月份链接改为当前路径，并补齐对称链接。
- 创建符合 Schema 的 `LLM Wiki 操作日志.md`。
- Lint 忽略围栏、缩进和行内代码中的伪 WikiLink，识别 `.md` 文件名内部的 `#`。
- 当前结构扫描排除 `.state` 与 `.git`，并把精选资料中的普通 Markdown 教程链接与受管 WikiLink/图片引用分开处理。
- 历史迁移验证接受唯一、可证明的 Markdown 后续迁移，以及受管 domain 旧别名；历史报告按 manifest 记录的检查口径验证，不与持续变化的当前计数强绑定。
- 分类器识别“辞职/涨薪”引流标题下以 AI 训练营、大模型项目、MCP/Skills 和 AI 产品为主体的正文，避免误报为个人成长迁移。

## 安全边界

- 用户已在当前任务明确授权处理正式 Vault 治理问题。
- 不批量重分类，不删除正文，不清空废纸篓，不修改 `.state/quarantine` 历史文件。
- Vault 写入前必须确认配置路径、路径边界、无活动锁和 Git 基线干净。
- Vault 内容改动限定为治理 Schema、日志、知识笔记 frontmatter 与两篇 Quant 资料的受管链接块。
- 源码变更遵循 TDD；每个行为必须先观察回归测试失败。

## 验收

- `lint_llm_wiki.py` 对正式 Vault 返回 `ok: true`，error/warning/manual_review 均为 0。
- `restructure_obsidian_vault.py --verify` 不再扫描 `.state`，且完成验证通过。
- 十二 domain、2479 篇资料与索引、附件、重复 GUID/标题继续全绿。
- 分类审计不产生新增高置信错误迁移建议。
- 已人工核验的 AI 训练与产品资料保持在 AI domain，最终分类审计的 move 候选为 0。
- SQLite `PRAGMA integrity_check` 为 `ok`；Vault Git 只包含预期文件并形成可恢复提交。
- 源码测试全量通过，`git diff --check` 通过。
