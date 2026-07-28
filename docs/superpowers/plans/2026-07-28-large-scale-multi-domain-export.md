# 印象笔记大规模多领域导出实施计划

> [!WARNING]
> **已废弃。** 本文记录早期实施过程，其中仓库 `.state/` 和任务文件保存 Vault 路径等步骤不得作为现行操作指引；现行契约以 [Vault 范围运行状态设计](../specs/2026-07-28-vault-scoped-runtime-state-design.md)、`README.md` 和 `SKILL.md` 为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一次任务完成多领域搜索、正文审核、唯一归属、全局去重、跨任务解析缓存、限流续跑和完整性验收的大规模导出命令。

**Architecture:** 保留单领域导出命令，把限流和分页下沉到共享运行时，把领域判定和规则指纹保留在现有导出模块，新增独立完整性扫描模块与多领域编排模块。编排过程按 GUID 流式处理完整正文，每处理一篇便保存不含正文的原子状态，结束后统一重建索引并执行硬性验收。

**Tech Stack:** Python 3.12、标准库 `argparse`、`dataclasses`、`hashlib`、`json`、`pathlib`、`time`、`unittest`，以及现有 `evernote3`、Thrift 和 ENML/Markdown 转换函数。

## Global Constraints

- 使用简体中文编写文档、命令帮助和 Git 提交消息。
- 不打印、记录或提交 Developer Token，不把完整 ENML 或附件持久化进 `.state/`。
- 历史解析目录只保存标题、GUID、摘要、领域标签、规则指纹和审计元数据，不保存完整正文。
- 日期区间固定为左闭右开；目标目录固定为 `<vault>/30_精选资料/<domain>`。
- 同一 GUID 在一次正常任务中只请求一次完整正文，限流后的同操作重试除外。
- 只有正文唯一主领域、全局标题去重和附件保存全部成功后才记录 accepted。
- 所有行为变更先写失败测试并确认按预期失败，再写最小实现。
- 真实账号只执行读取，测试使用假 NoteStore 和临时 vault。

---

### Task 1: 共享全量分页与限流重试

**Files:**
- Modify: `scripts/runtime.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Produces: `find_all_notes_metadata(note_store, token, note_filter, result_spec, page_size=250) -> tuple[list, int]`
- Produces: `call_with_rate_limit_retry(operation, *, mode, max_wait_seconds, sleep, on_wait=None) -> object`
- Produces: `RateLimitBudgetExceeded`

- [ ] **Step 1: 写全量分页失败测试**

构造假 NoteStore，第一页返回 `totalNotes=3` 和两条，第二页返回一条；断言 `find_all_notes_metadata` 返回三条且 offset 依次为 0、2。该测试应因函数不存在失败。

- [ ] **Step 2: 运行分页测试并确认 RED**

Run: `python -m unittest tests.test_runtime.RuntimeConfigTests.test_find_all_notes_metadata_reads_until_server_total -v`

Expected: FAIL，提示无法导入 `find_all_notes_metadata`。

- [ ] **Step 3: 实现全量分页**

复用 NoteStore 参数顺序，每页读取 `min(page_size, total-offset)`；空页但仍未达到服务端总数时抛出 `RuntimeError`，禁止静默返回截断结果。

- [ ] **Step 4: 写限流等待、停止和超预算失败测试**

使用依次抛出 `EDAMSystemException(errorCode=19, rateLimitDuration=2)`、返回 `"ok"` 的操作，断言 wait 模式调用 `sleep(2)` 后成功；stop 模式和等待时间大于预算时抛出 `RateLimitBudgetExceeded`。

- [ ] **Step 5: 运行限流测试并确认 RED**

Run: `python -m unittest tests.test_runtime.RuntimeConfigTests.test_rate_limit_wait_retries_same_operation tests.test_runtime.RuntimeConfigTests.test_rate_limit_stop_and_budget_exhaustion_preserve_control -v`

Expected: FAIL，提示无法导入限流接口。

- [ ] **Step 6: 实现有预算重试**

只识别错误码 19；`mode` 仅允许 `wait`、`stop`。等待时间取非负整数，累计等待不得超过 `max_wait_seconds`，其他异常原样抛出。

- [ ] **Step 7: 运行共享运行时测试**

Run: `python -m unittest tests.test_runtime -v`

Expected: PASS。

### Task 2: 领域规则指纹与可验证状态

**Files:**
- Modify: `scripts/export_search_results.py`
- Modify: `tests/test_export_search_results.py`

**Interfaces:**
- Produces: `EXPORT_POLICY_VERSION: int`
- Produces: `domain_policy_hash() -> str`
- Produces: `assess_primary_domain(title, content, allowed_domains) -> DomainAssessment`
- Modifies: `export_domain_candidates(..., policy_hash=None)`，只有 accepted 状态与当前规则一致时快速跳过。

- [ ] **Step 1: 写唯一主领域失败测试**

分别构造 AI 主导、投资理财主导、AI 与投资理财并列正文。断言前两者返回对应领域并匹配，并列结果 `matched=False` 且原因包含“并列”。

- [ ] **Step 2: 运行主领域测试并确认 RED**

Run: `python -m unittest tests.test_export_search_results.DomainRelevanceTests.test_primary_domain_is_unique_across_allowed_domains -v`

Expected: FAIL，提示 `assess_primary_domain` 不存在。

- [ ] **Step 3: 实现唯一主领域和稳定规则指纹**

规则指纹由 `EXPORT_POLICY_VERSION` 和排序后的 `DOMAIN_PROFILES` JSON 生成；主领域使用现有 `_score_domain`，其他已知领域占优时仍拒绝。

- [ ] **Step 4: 写 accepted 状态失效失败测试**

准备已导出的 Markdown 和两种状态：当前规则指纹时不得调用 `getNote`；旧指纹时必须调用一次并按新规则重新审核。附件引用缺失时，即使指纹一致也必须重新调用。

- [ ] **Step 5: 运行状态测试并确认 RED**

Run: `python -m unittest tests.test_export_search_results.DomainGatedExportTests.test_fast_skip_requires_current_policy_and_complete_attachments -v`

Expected: FAIL，旧实现仅比较 GUID 与 updated，会错误跳过。

- [ ] **Step 6: 实现版本 2 状态契约**

accepted 和 rejected 都写入 `updated`、`domain`、`outcome`、`policy_hash`、`reason`、`evidence`；accepted 额外记录相对路径。读取版本 1 状态时视为需要重审，不直接跳过。

- [ ] **Step 7: 运行导出模块测试**

Run: `python -m unittest tests.test_export_search_results -v`

Expected: PASS。

### Task 3: 跨任务历史解析目录

**Files:**
- Create: `scripts/export_catalog.py`
- Create: `tests/test_export_catalog.py`

**Interfaces:**
- Produces: `CatalogEntry`
- Produces: `ExportCatalog(path: Path)`
- Produces: `ExportCatalog.get_current(guid, updated_ms, policy_hash) -> CatalogEntry | None`
- Produces: `ExportCatalog.upsert(entry: CatalogEntry) -> None`
- Produces: `ExportCatalog.mark_seen(guid, seen_at) -> None`
- Produces: `ExportCatalog.stats() -> dict`

- [ ] **Step 1: 写目录建表和持久化失败测试**

在临时路径创建目录，写入包含标题、GUID、摘要、主领域、领域标签、得分、证据和规范路径的记录；关闭后重新打开，断言所有字段完整且 SQLite 文件不包含完整正文夹具。

- [ ] **Step 2: 运行持久化测试并确认 RED**

Run: `python -m unittest tests.test_export_catalog.ExportCatalogTests.test_catalog_persists_summary_domain_labels_and_audit_metadata -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 schema 和 upsert**

以 GUID 为主键；JSON 字段写入排序后的 UTF-8 JSON。使用 SQLite 事务逐条提交，创建 `updated_ms`、`primary_domain` 和规范化标题索引。

- [ ] **Step 4: 写跨关键词复用和失效失败测试**

同一 GUID、updated 和规则指纹应命中；关键词不参与缓存键。updated 或规则指纹任一变化时返回 `None`，但保留旧记录供统计。

- [ ] **Step 5: 运行复用测试并确认 RED**

Run: `python -m unittest tests.test_export_catalog.ExportCatalogTests.test_cache_key_ignores_keywords_but_invalidates_updated_or_policy -v`

Expected: FAIL，尚未实现当前记录判定。

- [ ] **Step 6: 实现查询、最近出现时间和统计**

`get_current` 只返回完整且当前的记录；`mark_seen` 不修改最近正文获取时间；统计区分总记录、当前任务命中、失效和正文请求节省量，由编排层累计任务统计。

- [ ] **Step 7: 运行解析目录测试**

Run: `python -m unittest tests.test_export_catalog -v`

Expected: PASS。

### Task 4: 精选资料完整性扫描器

**Files:**
- Create: `scripts/export_integrity.py`
- Create: `tests/test_export_integrity.py`

**Interfaces:**
- Produces: `IntegrityIssue(kind: str, domain: str, source: Path, detail: str)`
- Produces: `DomainIntegrity(domain, total_articles, in_range_articles, index_entries, image_references, issues)`
- Produces: `ExportIntegrityReport(domains, cross_domain_guid_duplicates, cross_domain_title_duplicates)`
- Produces: `scan_export_integrity(vault, domains, since, until) -> ExportIntegrityReport`
- Produces: `report.ok -> bool` 和 `report.to_dict() -> dict`

- [ ] **Step 1: 写索引、附件和范围扫描失败测试**

临时 vault 中创建一篇范围内资料、一条缺失附件引用、缺失索引目标和一篇越界资料；断言报告分别产生 `missing_attachment`、`missing_index_target` 和正确的范围内数量。

- [ ] **Step 2: 运行扫描测试并确认 RED**

Run: `python -m unittest tests.test_export_integrity.ExportIntegrityTests.test_scanner_reports_index_attachment_and_range_facts -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现只读领域扫描**

复用 `extract_note_metadata`、`_split_frontmatter` 和 `iter_markdown_references`。只把图片或 `_attachments` 本地引用作为附件契约，避免把正文示例 `REFERENCE.md` 误报为知识库链接。

- [ ] **Step 4: 写跨领域重复失败测试**

在 AI 与投资理财目录创建同一 GUID 和同一标题，断言报告各发现一个跨领域重复；不同 GUID 的完全一致标题也必须计入标题重复。

- [ ] **Step 5: 运行重复测试并确认 RED**

Run: `python -m unittest tests.test_export_integrity.ExportIntegrityTests.test_scanner_finds_cross_domain_guid_and_title_duplicates -v`

Expected: FAIL，尚未实现全局聚合。

- [ ] **Step 6: 实现全局重复和 JSON 序列化**

按 GUID、标题聚合领域和路径；`ok` 只有解析、索引、附件、领域内重复和跨领域重复全部为空时为真。检索区间使用搜索统计对账；目标目录已有的其他月份属于历史知识库，只计入总量，不视为本次任务越界。

- [ ] **Step 7: 运行完整性测试**

Run: `python -m unittest tests.test_export_integrity -v`

Expected: PASS。

### Task 5: 多领域流式编排

**Files:**
- Create: `scripts/export_multi_domain.py`
- Create: `tests/test_export_multi_domain.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `load_job(path: Path) -> ExportJob`
- Produces: `normalize_job(payload: dict) -> ExportJob`
- Produces: `run_export_job(job, note_store, token, *, state_file, report_file, rate_limit_mode, max_rate_limit_wait, verbose=False) -> dict`
- Consumes: `ExportCatalog`、`find_all_notes_metadata`、`call_with_rate_limit_retry`、`assess_primary_domain`、`export_note_to_obsidian`、`finalize_knowledge_base`、`scan_export_integrity`

- [ ] **Step 1: 写任务校验失败测试**

断言 `until <= since`、未知领域、空关键词、vault 直接指向 `30_精选资料` 都被拒绝；合法任务把目标解析到 `<vault>/30_精选资料/<domain>`。

- [ ] **Step 2: 运行任务校验测试并确认 RED**

Run: `python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_job_validation_and_target_derivation -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现任务模型和 CLI**

使用冻结 dataclass 保存日期、vault、领域关键词；CLI 提供 `--job`、`--catalog`、`--rate-limit-mode {wait,stop}`、`--max-rate-limit-wait`、`--state-file`、`--report-file` 和 `--verbose`。

- [ ] **Step 4: 写单次正文和全局标题去重失败测试**

让同一 GUID 同时命中 AI、Agent 和金融批次，断言只调用一次 `getNote`；再提供同标题新旧 GUID，断言只导出较新的正文匹配版本。

- [ ] **Step 5: 运行核心编排测试并确认 RED**

Run: `python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_each_guid_is_fetched_once_and_titles_are_globally_deduplicated -v`

Expected: FAIL，尚未实现任务执行。

- [ ] **Step 6: 实现全量搜索和流式审核**

所有关键词先全量搜索并按 GUID 合并；候选按更新时间排序。逐篇获取正文、计算唯一主领域、全局标题去重、立即写入、立即保存状态，不保留 Note 对象。

- [ ] **Step 7: 写续跑和报告失败测试**

第一次运行在第二篇遇到限流超预算，断言第一篇已写入且状态有效；第二次运行跳过第一篇并完成。默认标准输出不得逐篇打印拒绝标题，报告必须包含搜索总数、正文请求、跳过、领域/月度统计和限流统计。

- [ ] **Step 8: 运行续跑测试并确认 RED**

Run: `python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_interrupted_job_resumes_and_writes_bounded_summary_report -v`

Expected: FAIL，尚未实现状态恢复和报告。

- [ ] **Step 9: 写历史目录复用失败测试**

第一次任务用关键词 `Claude` 拉取并解析一篇正文；第二次任务改为 `LLM`，搜索仍返回相同 GUID 和 updated。断言第二次不调用 `getNote`，报告 `catalog_hits=1`、`body_requests_saved=1`。若该篇需要落盘但规范文件不存在，则只为物化请求一次正文。

- [ ] **Step 10: 运行目录复用测试并确认 RED**

Run: `python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_changed_keywords_reuse_catalog_without_refetching_body -v`

Expected: FAIL，编排层尚未查询历史目录。

- [ ] **Step 11: 实现目录优先、延迟物化和原子状态**

先用历史目录参与领域归属和标题去重。缓存拒绝项、已有完整规范文件和被新版本淘汰项不请求正文；只有目录未命中、失效或最终入选但缺少规范文件时调用 `getNote`。状态与报告先写 `.tmp` 再替换。

- [ ] **Step 12: 实现汇总日志和验收门禁**

处理完后重建所有声明领域索引，调用完整性扫描；报告增加 `catalog_hits`、`catalog_stale`、`body_requests_saved`。报告 `ok=false` 时 CLI 返回非零且不能打印完成语句。

- [ ] **Step 13: 运行多领域端到端测试**

Run: `python -m unittest tests.test_export_multi_domain -v`

Expected: PASS。

### Task 6: Skill 行为规则与用户文档

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Create: `templates/multi-domain-export-job.json`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Documents: 大规模任务触发条件、唯一主领域、全局去重、跨任务历史目录、规则指纹、限流预算、汇总报告和验收契约。
- Provides: 可复制的多领域任务模板。

- [ ] **Step 1: 执行无新规则的基线行为测试**

向子代理提供“大范围、多关键词、三个领域、服务端会限流”的任务，但不提供更新后的 Skill；记录其是否选择三个独立命令、人工估算 `max-per-keyword`、仅靠命令退出码声称成功，形成 RED 证据。

- [ ] **Step 2: 写文档契约失败测试**

在 `test_skill_documentation.py` 中验证 Skill 明确要求：两个及以上领域使用 `export_multi_domain.py`；新关键词先查询 SQLite 历史目录；同一 GUID 只取一次正文；规则指纹不匹配要重审；成功必须通过索引、附件和跨领域重复验收。

- [ ] **Step 3: 运行文档测试并确认 RED**

Run: `python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_large_multi_domain_exports_use_orchestrated_verified_workflow -v`

Expected: FAIL，当前 Skill 仍只给出单领域命令。

- [ ] **Step 4: 更新 Skill、README 和任务模板**

把一次性复盘写成可复用触发规则和成功契约，不记录本轮具体文章标题或临时统计。快速参考中增加多领域命令，并保留单领域命令的小批量用途。

- [ ] **Step 5: 运行有新规则的行为复测**

向子代理提供同一场景并加载更新后的 Skill；要求其选择编排命令、明确唯一领域与全局去重，并以 JSON 报告和完整性扫描作为成功条件。

- [ ] **Step 6: 运行文档测试**

Run: `python -m unittest tests.test_skill_documentation -v`

Expected: PASS。

### Task 7: 全量验证与提交

**Files:**
- Modify as required by verification failures.

**Interfaces:**
- Verifies all interfaces and documentation from Tasks 1-5.

- [ ] **Step 1: 运行完整测试**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: 所有测试通过，0 failures，0 errors。

- [ ] **Step 2: 运行编译、差异和凭据检查**

Run: `python -m compileall -q scripts tests`

Run: `git diff --check`

Run: `rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" SKILL.md README.md scripts tests templates`

Expected: 全部返回成功或凭据搜索无匹配。

- [ ] **Step 3: 运行 CLI 帮助和模板解析**

Run: `python scripts/export_multi_domain.py --help`

Run: `python -c "from scripts.export_multi_domain import load_job; print(load_job('templates/multi-domain-export-job.json'))"`

Expected: 帮助为 UTF-8；模板可解析且目标只位于 `30_精选资料`。

- [ ] **Step 4: 审阅最终差异并提交**

确认没有 `.state/`、Token、真实笔记正文或 Obsidian 文件进入提交；提交消息使用简体中文。
