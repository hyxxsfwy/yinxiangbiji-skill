# 印象笔记关键词穷尽导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将印象笔记中创建时间位于 2026-01-01 至 2026-04-01 左闭右开区间、标题或完整正文命中指定关键词的全部唯一笔记，缓存分析结果到正式 Obsidian Vault 的 SQLite 状态库，并把 Markdown、图片和附件同步到 `30_精选资料` 的七个主题目录。

**Architecture:** 保留现有高精度领域导出模式，新增 `keyword_union` 选择模式。新模式先按每个查询词全量分页拉取元数据并合并 GUID，再逐篇获取一次正文和资源，使用边界安全的关键词匹配器确定是否入选和唯一主目录；每篇分析结果先提交到独立的 SQLite 表，再使用同一个 Note 对象写入 Markdown 和附件。运行完成后重建各目录索引，并以服务端搜索对账、SQLite 对账、frontmatter、附件、索引和重复项检查共同决定任务是否成功。

**Tech Stack:** Python 3.12、标准库 `argparse`、`dataclasses`、`hashlib`、`json`、`pathlib`、`re`、`sqlite3`、`unicodedata`、`zipfile`、`unittest`，以及现有 `evernote3`、Thrift、ENML/Markdown 转换与 Vault 状态组件。

## Global Constraints

- 使用简体中文编写文档、日志和 Git Commit 消息。
- 正式查询区间固定为 `[2026-01-01, 2026-04-01)`；包含 2026-01-01，不包含 2026-04-01。
- 63 个用户关键词必须全部作为规范关键词保留；`HugginFace` 额外展开为查询别名 `HuggingFace` 和 `Hugging Face`，报告仍归并到规范关键词 `HugginFace`。
- 真实印象笔记账户只执行搜索、读取正文和读取资源，不创建、不更新、不删除账户数据。
- 所有中文任务配置必须从 UTF-8 JSON 文件读取，不得通过 PowerShell 管道把中文源码传给 `python -`。
- 同一 GUID 在一次运行中最多调用一次 `getNote`；服务端限流后的同操作重试除外。
- SQLite 不保存完整 ENML、附件二进制、Developer Token 或 NoteStore URL，只保存元数据、摘要、哈希、匹配证据、归档结果和审计时间。
- 关键词模式使用独立表 `keyword_analyses`，不得覆盖现有 `parsed_notes` 高精度领域缓存。
- 英文和数字关键词使用 ASCII 字母数字边界；`AI` 不得命中 `training`，`SOL` 不得命中 `solution`，但允许命中 `AI助手`、`使用SOL交易`。
- 中文关键词使用 Unicode NFKC 规范化后的不区分大小写子串匹配。
- 主目录按规范关键词命中数量决定；并列时按任务 JSON 中的目录顺序选择，顺序固定为软件工程、AI、Quant、投资理财、知识管理、健康医学、两性情感。
- 同一 GUID 只导出一次；完全一致标题只保留按 `updated`、`created`、GUID 排序后的最新匹配版本。
- 正式写入前必须创建目标主题目录 ZIP 快照和 SHA-256 清单。
- 正式 Vault 中的旧 `30_精选资料\婚姻情感` 必须在独立迁移快照后安全归并到 `30_精选资料\两性情感`；不同内容的同路径文件立即停止，不得覆盖；迁移和验收完成后删除空的旧目录。
- 只有每个查询项 `pulled == total`、所有候选都有 SQLite 分析记录、报告 `ok: true`、附件和索引无缺失、领域内及跨领域重复为零时才能声明完成。
- 运行状态、SQLite、任务、快照和报告固定写入 `$vault\.state\yinxiang-notes\`；`$vault` 必须由 `load_vault_root()` 解析，任务 JSON 不保存设备绝对路径。

---

## File Structure

- Create: `scripts/keyword_selection.py`
  - 只负责关键词规范化、别名展开、边界匹配、唯一主目录判定和选择规则指纹。
- Create: `scripts/export_snapshot.py`
  - 只负责正式写入前的主题目录 ZIP 快照及 SHA-256 清单。
- Modify: `scripts/export_catalog.py`
  - 在同一个 SQLite 文件中新增独立的 `keyword_analyses` 表和读写接口。
- Modify: `scripts/export_multi_domain.py`
  - 扩展任务模型、搜索编排、Vault 历史回填、缓存优先处理、断点状态和最终报告。
- Modify: `scripts/export_search_results.py`
  - 允许写出关键词审计 frontmatter，不改变现有高精度正文门禁。
- Modify: `scripts/export_integrity.py`
  - 校验关键词模式 frontmatter、任务日期范围、SQLite/文件对账、附件、索引和重复项。
- Create: `tests/test_keyword_selection.py`
- Create: `tests/test_export_snapshot.py`
- Modify: `tests/test_export_catalog.py`
- Modify: `tests/test_export_multi_domain.py`
- Modify: `tests/test_export_search_results.py`
- Modify: `tests/test_export_integrity.py`
- Modify: `tests/test_skill_documentation.py`
- Create: `templates/keyword-union-export-job.json`
- Modify: `README.md`
- Modify: `SKILL.md`

---

### Task 1: 建立关键词规范、别名和边界安全匹配器

**Files:**
- Create: `scripts/keyword_selection.py`
- Create: `tests/test_keyword_selection.py`

**Interfaces:**
- Produces: `KeywordAssessment`
- Produces: `expanded_query_terms(domains, aliases) -> tuple[tuple[str, str, str], ...]`
- Produces: `match_keyword_terms(title, content, domains, aliases) -> dict[str, tuple[str, ...]]`
- Produces: `assess_keyword_union(title, content, domains, aliases) -> KeywordAssessment`
- Produces: `keyword_selection_hash(domains, aliases) -> str`

- [ ] **Step 1: 写关键词边界和中文匹配失败测试**

```python
class KeywordBoundaryTests(unittest.TestCase):
    def test_ascii_terms_require_ascii_alphanumeric_boundaries(self):
        domains = {
            "AI": ("AI",),
            "投资理财": ("SOL",),
        }
        self.assertFalse(
            assess_keyword_union(
                "training solution",
                "<en-note>training solution</en-note>",
                domains,
                {},
            ).matched
        )
        result = assess_keyword_union(
            "AI助手与SOL交易",
            "<en-note>使用AI助手分析SOL交易</en-note>",
            domains,
            {},
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.matched_keywords, ("AI", "SOL"))

    def test_chinese_terms_match_normalized_title_or_full_body(self):
        domains = {"健康医学": ("中医", "医学")}
        result = assess_keyword_union(
            "门诊记录",
            "<en-note><div>中医与现代医学</div></en-note>",
            domains,
            {},
        )
        self.assertEqual(result.primary_domain, "健康医学")
        self.assertEqual(result.matched_keywords, ("中医", "医学"))
```

- [ ] **Step 2: 运行匹配测试并确认 RED**

Run:

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest tests.test_keyword_selection.KeywordBoundaryTests -v
```

Expected: FAIL，提示 `scripts.keyword_selection` 不存在。

- [ ] **Step 3: 实现数据类型和匹配函数**

```python
from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata

from scripts.export_search_results import full_body_text

KEYWORD_SELECTION_POLICY_VERSION = 1


@dataclass(frozen=True)
class KeywordAssessment:
    matched: bool
    primary_domain: str | None
    matched_keywords: tuple[str, ...]
    matched_terms: tuple[str, ...]
    reason: str


def _normalized(value):
    return unicodedata.normalize("NFKC", value or "").casefold()


def _contains_term(text, term):
    normalized_text = _normalized(text)
    normalized_term = _normalized(term)
    if re.fullmatch(r"[a-z0-9]+(?:[ ._-][a-z0-9]+)*", normalized_term):
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(normalized_term)
            + r"(?![a-z0-9])"
        )
        return re.search(pattern, normalized_text) is not None
    return normalized_term in normalized_text
```

`match_keyword_terms` 同时检查标题和 `full_body_text(content)`，每个规范关键词只计一次；别名命中归并到规范关键词。`assess_keyword_union` 按每个目录的规范关键词命中数排序，计数并列时使用 `domains` 插入顺序。`keyword_selection_hash` 对版本、目录关键词和排序后的别名 JSON 计算 SHA-256。

- [ ] **Step 4: 写别名、唯一主目录和稳定指纹测试**

```python
class KeywordAssessmentTests(unittest.TestCase):
    def test_alias_is_reported_as_canonical_keyword(self):
        result = assess_keyword_union(
            "HuggingFace 入门",
            "<en-note>Hugging Face Transformer</en-note>",
            {"AI": ("HugginFace", "Transformer")},
            {"HugginFace": ("HuggingFace", "Hugging Face")},
        )
        self.assertEqual(
            result.matched_keywords,
            ("HugginFace", "Transformer"),
        )

    def test_domain_count_wins_and_job_order_breaks_ties(self):
        domains = {
            "软件工程": ("软件工程",),
            "AI": ("AI", "LLM"),
        }
        result = assess_keyword_union(
            "软件工程中的AI与LLM",
            "<en-note>软件工程 AI LLM</en-note>",
            domains,
            {},
        )
        self.assertEqual(result.primary_domain, "AI")
        tie = assess_keyword_union(
            "软件工程与AI",
            "<en-note>软件工程 AI</en-note>",
            domains,
            {},
        )
        self.assertEqual(tie.primary_domain, "软件工程")

    def test_policy_hash_is_stable_and_changes_with_keywords(self):
        first = keyword_selection_hash({"AI": ("AI",)}, {})
        second = keyword_selection_hash({"AI": ("AI",)}, {})
        changed = keyword_selection_hash({"AI": ("AI", "LLM")}, {})
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
```

- [ ] **Step 5: 运行关键词模块测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_keyword_selection -v
```

Expected: PASS。

- [ ] **Step 6: 提交关键词匹配器**

```powershell
git add scripts/keyword_selection.py tests/test_keyword_selection.py
git commit -m "新增关键词穷尽匹配器"
```

---

### Task 2: 扩展任务 JSON 和安全校验

**Files:**
- Modify: `scripts/export_multi_domain.py:93-214`
- Modify: `tests/test_export_multi_domain.py`
- Create: `templates/keyword-union-export-job.json`

**Interfaces:**
- Modifies: `ExportJob`
- Modifies: `normalize_job(payload, vault) -> ExportJob`
- Produces: `ExportJob.selection_mode: str`
- Produces: `ExportJob.aliases: dict[str, tuple[str, ...]]`
- Consumes: `expanded_query_terms`

- [ ] **Step 1: 写 keyword_union 任务解析和路径安全测试**

```python
def keyword_union_payload():
    return {
        "since": "2026-01-01",
        "until": "2026-04-01",
        "selection_mode": "keyword_union",
        "domains": {
            "软件工程": {"keywords": ["软件工程", "项目管理"]},
            "AI": {"keywords": ["AI", "LLM", "HugginFace"]},
        },
        "aliases": {
            "HugginFace": ["HuggingFace", "Hugging Face"],
        },
    }


def test_keyword_union_accepts_controlled_new_domains_and_aliases(self):
    job = normalize_job(keyword_union_payload(), self.vault)
    self.assertEqual(job.selection_mode, "keyword_union")
    self.assertEqual(job.since.isoformat(), "2026-01-01")
    self.assertEqual(job.until.isoformat(), "2026-04-01")
    self.assertEqual(
        job.aliases["HugginFace"],
        ("HuggingFace", "Hugging Face"),
    )
    self.assertEqual(
        job.target_for("软件工程"),
        self.vault / "30_精选资料" / "软件工程",
    )


def test_keyword_union_rejects_path_escape_and_unknown_alias_key(self):
    payload = keyword_union_payload()
    payload["domains"]["../逃逸"] = {"keywords": ["逃逸"]}
    with self.assertRaisesRegex(ValueError, "领域名称"):
        normalize_job(payload, self.vault)
    payload = keyword_union_payload()
    payload["aliases"]["不存在"] = ["missing"]
    with self.assertRaisesRegex(ValueError, "别名键"):
        normalize_job(payload, self.vault)
```

- [ ] **Step 2: 运行任务解析测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_multi_domain.MultiDomainJobTestMixin.test_keyword_union_accepts_controlled_new_domains_and_aliases tests.test_export_multi_domain.MultiDomainJobTestMixin.test_keyword_union_rejects_path_escape_and_unknown_alias_key -v
```

Expected: FAIL，现有 `ExportJob` 没有 `selection_mode` 和 `aliases`，且未知领域被统一拒绝。

- [ ] **Step 3: 扩展任务模型和校验**

```python
@dataclass(frozen=True)
class ExportJob:
    since: date
    until: date
    vault: Path
    domains: dict[str, tuple[str, ...]]
    selection_mode: str = "domain_gate"
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
```

`selection_mode` 只允许 `domain_gate` 和 `keyword_union`。`domain_gate` 继续要求目录名位于 `DOMAIN_PROFILES`；`keyword_union` 允许任务声明新目录，但目录名必须满足 `^[^<>:"/\\|?*\x00-\x1f.][^<>:"/\\|?*\x00-\x1f]*$`，不得等于 `.`、`..`，解析后的目标必须仍位于 `load_vault_root() / "30_精选资料"`。别名键必须是某个规范关键词，别名值必须是非空字符串数组。

- [ ] **Step 4: 创建本次完整 UTF-8 任务模板**

```json
{
  "since": "2026-01-01",
  "until": "2026-04-01",
  "selection_mode": "keyword_union",
  "domains": {
    "软件工程": {
      "keywords": [
        "软件工程",
        "项目管理",
        "Engineering"
      ]
    },
    "AI": {
      "keywords": [
        "AI",
        "人工智能",
        "机器学习",
        "深度学习",
        "强化学习",
        "大模型",
        "本体",
        "ontology",
        "LLM",
        "GPT",
        "RAG",
        "Agent",
        "MCP",
        "Skills",
        "Harness",
        "Anthropic",
        "OpenAI",
        "Claude",
        "Codex",
        "WorkBuddy",
        "DeepSeek",
        "Qwen",
        "千问",
        "GLM",
        "Kimi",
        "MiniMax",
        "HugginFace",
        "Transformer",
        "Attention",
        "RWKV",
        "RLHF",
        "图文生成",
        "扩散模型"
      ]
    },
    "Quant": {
      "keywords": [
        "量化",
        "量化交易",
        "Quant"
      ]
    },
    "投资理财": {
      "keywords": [
        "金融",
        "理财",
        "定投",
        "基金",
        "贷款",
        "ETF",
        "区块链",
        "比特币",
        "BTC",
        "以太坊",
        "ETH",
        "SOL"
      ]
    },
    "知识管理": {
      "keywords": [
        "GTD",
        "PKM"
      ]
    },
    "健康医学": {
      "keywords": [
        "中医",
        "健康",
        "医学",
        "医生",
        "疾控"
      ]
    },
    "两性情感": {
      "keywords": [
        "婚姻",
        "幸福",
        "两性",
        "情感",
        "心理"
      ]
    }
  },
  "aliases": {
    "HugginFace": [
      "HuggingFace",
      "Hugging Face"
    ]
  }
}
```

- [ ] **Step 5: 写模板完整性测试**

```python
def test_keyword_union_template_contains_every_requested_keyword(self):
    payload = json.loads(
        Path("templates/keyword-union-export-job.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "软件工程", "项目管理", "AI", "人工智能", "机器学习",
        "深度学习", "强化学习", "大模型", "本体", "ontology",
        "LLM", "GPT", "RAG", "Agent", "MCP", "Skills", "Harness",
        "Anthropic", "OpenAI", "Claude", "Codex", "WorkBuddy",
        "DeepSeek", "Qwen", "千问", "GLM", "Kimi", "MiniMax",
        "HugginFace", "Transformer", "Attention", "RWKV", "RLHF",
        "Engineering", "图文生成", "扩散模型", "量化", "量化交易",
        "Quant", "金融", "理财", "定投", "基金", "贷款", "ETF",
        "区块链", "比特币", "BTC", "以太坊", "ETH", "SOL", "GTD",
        "PKM", "中医", "健康", "医学", "医生", "疾控", "婚姻",
        "幸福", "两性", "情感", "心理",
    }
    actual = {
        keyword
        for settings in payload["domains"].values()
        for keyword in settings["keywords"]
    }
    self.assertEqual(actual, expected)
    self.assertEqual(payload["since"], "2026-01-01")
    self.assertEqual(payload["until"], "2026-04-01")
```

- [ ] **Step 6: 运行任务和模板测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_export_multi_domain.MultiDomainJobTestMixin tests.test_skill_documentation.SkillDocumentationTests.test_keyword_union_template_contains_every_requested_keyword -v
```

Expected: PASS。

- [ ] **Step 7: 提交任务契约**

```powershell
git add scripts/export_multi_domain.py tests/test_export_multi_domain.py templates/keyword-union-export-job.json tests/test_skill_documentation.py
git commit -m "扩展关键词穷尽任务契约"
```

---

### Task 3: 新增独立 SQLite 关键词分析缓存

**Files:**
- Modify: `scripts/export_catalog.py:14-194`
- Modify: `tests/test_export_catalog.py`

**Interfaces:**
- Produces: `KeywordCatalogEntry`
- Produces: `ExportCatalog.get_keyword_current(guid, updated_ms, selection_hash) -> KeywordCatalogEntry | None`
- Produces: `ExportCatalog.upsert_keyword(entry: KeywordCatalogEntry) -> None`
- Produces: `ExportCatalog.keyword_stats(selection_hash) -> dict`
- Produces: `ExportCatalog.count_keyword_current(expected_candidates, selection_hash) -> int`
- Preserves: existing `parsed_notes` schema and methods

- [ ] **Step 1: 写独立表建表和持久化失败测试**

```python
def test_keyword_cache_is_separate_from_domain_cache(self):
    with ExportCatalog(self.path) as catalog:
        catalog.upsert_keyword(
            KeywordCatalogEntry(
                guid="guid-1",
                updated_ms=1000,
                selection_hash="selection-1",
                title="AI 医疗",
                created_ms=900,
                notebook_name="收件箱",
                summary="摘要",
                body_sha256="body-hash",
                outcome="accepted",
                primary_domain="AI",
                matched_keywords=("AI", "医学"),
                matched_terms=("AI", "医学"),
                canonical_path=None,
                first_fetched_at="2026-07-29T10:00:00+08:00",
                last_fetched_at="2026-07-29T10:00:00+08:00",
                last_seen_at="2026-07-29T10:00:00+08:00",
            )
        )
        self.assertIsNone(catalog.get("guid-1"))
        entry = catalog.get_keyword_current(
            "guid-1", 1000, "selection-1"
        )
        self.assertEqual(entry.matched_keywords, ("AI", "医学"))
```

- [ ] **Step 2: 运行关键词缓存测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_catalog.ExportCatalogTests.test_keyword_cache_is_separate_from_domain_cache -v
```

Expected: FAIL，提示 `KeywordCatalogEntry` 或关键词缓存方法不存在。

- [ ] **Step 3: 新增关键词缓存表**

```sql
CREATE TABLE IF NOT EXISTS keyword_analyses (
    guid TEXT NOT NULL,
    updated_ms INTEGER NOT NULL,
    selection_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    notebook_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    body_sha256 TEXT NOT NULL,
    outcome TEXT NOT NULL,
    primary_domain TEXT,
    matched_keywords_json TEXT NOT NULL,
    matched_terms_json TEXT NOT NULL,
    canonical_path TEXT,
    first_fetched_at TEXT NOT NULL,
    last_fetched_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (guid, selection_hash)
);
CREATE INDEX IF NOT EXISTS idx_keyword_analyses_updated
    ON keyword_analyses(updated_ms);
CREATE INDEX IF NOT EXISTS idx_keyword_analyses_domain
    ON keyword_analyses(primary_domain);
CREATE INDEX IF NOT EXISTS idx_keyword_analyses_title
    ON keyword_analyses(normalized_title);
CREATE INDEX IF NOT EXISTS idx_keyword_analyses_selection
    ON keyword_analyses(selection_hash);
```

`upsert_keyword` 只允许 `accepted`、`rejected`、`duplicate_title` 三种结果。冲突更新时保留原 `first_fetched_at`，更新其余分析字段；每篇使用独立 SQLite 事务提交。

`count_keyword_current` 接收 `{guid: updated_ms}` 字典，只统计同时匹配 GUID、`updated_ms` 和 `selection_hash` 的当前候选。不得用 `keyword_stats(selection_hash)["total"]` 代替本次候选覆盖数，因为同一选择规则可能被不同日期任务复用。

- [ ] **Step 4: 写缓存失效、拒绝缓存和统计测试**

```python
def test_keyword_cache_requires_updated_and_selection_hash(self):
    entry = keyword_entry(
        guid="guid-1",
        updated_ms=1000,
        selection_hash="selection-1",
        outcome="rejected",
    )
    with ExportCatalog(self.path) as catalog:
        catalog.upsert_keyword(entry)
        self.assertIsNotNone(
            catalog.get_keyword_current(
                "guid-1", 1000, "selection-1"
            )
        )
        self.assertIsNone(
            catalog.get_keyword_current(
                "guid-1", 1001, "selection-1"
            )
        )
        self.assertIsNone(
            catalog.get_keyword_current(
                "guid-1", 1000, "selection-2"
            )
        )
        stats = catalog.keyword_stats("selection-1")
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["rejected"], 1)
```

- [ ] **Step 5: 运行全部目录测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_export_catalog -v
```

Expected: PASS，原 `parsed_notes` 测试保持通过。

- [ ] **Step 6: 提交 SQLite 关键词缓存**

```powershell
git add scripts/export_catalog.py tests/test_export_catalog.py
git commit -m "新增关键词分析缓存表"
```

---

### Task 4: 从 Vault 现有 Markdown 回填关键词缓存

**Files:**
- Modify: `scripts/export_multi_domain.py:404-477`
- Modify: `tests/test_export_multi_domain.py`

**Interfaces:**
- Produces: `bootstrap_keyword_catalog_from_vault(job, catalog, selection_hash, seen_at) -> int`
- Consumes: `assess_keyword_union`
- Consumes: `ExportCatalog.upsert_keyword`

- [ ] **Step 1: 写 Vault 回填失败测试**

```python
def test_existing_keyword_markdown_bootstraps_keyword_cache(self):
    path = (
        self.vault
        / "30_精选资料"
        / "AI"
        / "2026年05月"
        / "AI Agent.md"
    )
    write_exported_note(
        path,
        guid="guid-existing",
        title="AI Agent",
        created="2026-05-02 10:00:00",
        updated="2026-05-03 10:00:00",
        domain="AI",
        body="AI Agent 与 MCP",
    )
    job = normalize_job(keyword_union_payload(), self.vault)
    selection_hash = keyword_selection_hash(
        job.domains, job.aliases
    )
    with ExportCatalog(self.catalog_path) as catalog:
        count = bootstrap_keyword_catalog_from_vault(
            job, catalog, selection_hash, "2026-07-29T10:00:00+08:00"
        )
        entry = catalog.get_keyword_current(
            "guid-existing",
            1780000000000,
            selection_hash,
        )
    self.assertEqual(count, 1)
    self.assertEqual(entry.primary_domain, "AI")
    self.assertIn("AI", entry.matched_keywords)
```

- [ ] **Step 2: 运行回填测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_existing_keyword_markdown_bootstraps_keyword_cache -v
```

Expected: FAIL，提示 `bootstrap_keyword_catalog_from_vault` 不存在。

- [ ] **Step 3: 实现只读 Vault 回填**

遍历任务声明的七个目录，跳过 `目录索引.md`，解析 `type: 资料`、`domain`、`source_guid`、`source_updated_ms` 和正文。仅当文件路径位于任务目录、创建时间在任务范围、附件引用完整、关键词匹配器确认命中时写入 `keyword_analyses`。现有文件的 mtime 作为首次和最近获取时间；`canonical_path` 保存 Vault 相对路径。

- [ ] **Step 4: 写无效文件不入库测试**

```python
def test_keyword_bootstrap_skips_out_of_range_or_missing_attachment(self):
    out_of_range = seed_keyword_markdown(
        self.vault,
        domain="AI",
        title="AI 旧资料",
        guid="old",
        created="2026-03-31 23:59:59",
        body="AI",
    )
    broken = seed_keyword_markdown(
        self.vault,
        domain="AI",
        title="AI 缺图",
        guid="broken",
        created="2026-01-01 00:00:00",
        body="AI ![图](../_attachments/missing.png)",
    )
    job = normalize_job(keyword_union_payload(), self.vault)
    with ExportCatalog(self.catalog_path) as catalog:
        count = bootstrap_keyword_catalog_from_vault(
            job,
            catalog,
            keyword_selection_hash(job.domains, job.aliases),
            "2026-07-29T10:00:00+08:00",
        )
    self.assertEqual(count, 0)
```

- [ ] **Step 5: 运行多领域导出测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_export_multi_domain -v
```

Expected: PASS。

- [ ] **Step 6: 提交 Vault 历史回填**

```powershell
git add scripts/export_multi_domain.py tests/test_export_multi_domain.py
git commit -m "支持从现有资料回填关键词缓存"
```

---

### Task 5: 为导出 Markdown 写入关键词审计元数据

**Files:**
- Modify: `scripts/export_search_results.py:870-945`
- Modify: `tests/test_export_search_results.py`

**Interfaces:**
- Modifies: `export_note_to_obsidian(note, notebook_name, target_dir, domain="AI", *, selection_mode="domain_gate", matched_keywords=(), selection_hash=None) -> Path`
- Adds frontmatter: `selection_mode`
- Adds frontmatter: `matched_keywords`
- Adds frontmatter: `selection_hash`

- [ ] **Step 1: 写关键词 frontmatter 失败测试**

```python
def test_keyword_export_writes_audit_frontmatter(self):
    note = full_note(
        guid="guid-1",
        title="AI Agent",
        content="<en-note>AI Agent 与 MCP</en-note>",
    )
    path = export_note_to_obsidian(
        note,
        notebook_name="收件箱",
        target_dir=self.target,
        domain="AI",
        selection_mode="keyword_union",
        matched_keywords=("AI", "Agent", "MCP"),
        selection_hash="selection-1",
    )
    markdown = path.read_text(encoding="utf-8")
    self.assertIn("selection_mode: keyword_union", markdown)
    self.assertIn("matched_keywords:", markdown)
    self.assertIn("  - AI", markdown)
    self.assertIn("selection_hash: selection-1", markdown)
```

- [ ] **Step 2: 运行 frontmatter 测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_search_results.ExportNoteTests.test_keyword_export_writes_audit_frontmatter -v
```

Expected: FAIL，函数不接受关键词审计参数。

- [ ] **Step 3: 扩展导出函数但保持旧调用兼容**

关键词模式时在现有 `extra` 中加入：

```python
extra.update(
    {
        "selection_mode": selection_mode,
        "matched_keywords": list(matched_keywords),
        "selection_hash": selection_hash,
    }
)
```

`domain_gate` 默认调用不新增这些字段，确保现有单领域和多领域测试输出不变。

- [ ] **Step 4: 运行导出与同步完整测试**

Run:

```powershell
python -m unittest tests.test_export_search_results tests.test_sync_integrity -v
```

Expected: PASS。

- [ ] **Step 5: 提交关键词审计 frontmatter**

```powershell
git add scripts/export_search_results.py tests/test_export_search_results.py
git commit -m "记录关键词导出审计元数据"
```

---

### Task 6: 实现缓存优先的 keyword_union 编排与断点续跑

**Files:**
- Modify: `scripts/export_multi_domain.py:492-923`
- Modify: `tests/test_export_multi_domain.py`

**Interfaces:**
- Consumes: `expanded_query_terms`
- Consumes: `assess_keyword_union`
- Consumes: `ExportCatalog.get_keyword_current`
- Consumes: `ExportCatalog.upsert_keyword`
- Preserves: `run_export_job(...) -> dict`
- Produces report sections: `selection`, `searches`, `candidates`, `cache`, `materialization`

- [ ] **Step 1: 写全量查询、GUID 合并和中文 UTF-8 任务测试**

```python
def test_keyword_union_searches_every_query_term_and_merges_guid(self):
    payload = keyword_union_payload()
    job = normalize_job(payload, self.vault)
    store = FakeNoteStore(
        search_results={
            "软件工程": [metadata("same", "软件工程 AI")],
            "AI": [metadata("same", "软件工程 AI")],
            "HuggingFace": [metadata("hf", "HuggingFace")],
            "Hugging Face": [metadata("hf", "HuggingFace")],
        },
        notes={
            "same": full_note("same", "软件工程 AI", "软件工程 AI"),
            "hf": full_note("hf", "HuggingFace", "Hugging Face"),
        },
    )
    report = run_keyword_job(job, store)
    self.assertEqual(report["candidates"]["unique_guids"], 2)
    self.assertEqual(store.get_note_calls["same"], 1)
    self.assertEqual(store.get_note_calls["hf"], 1)
    self.assertTrue(
        all(item["pulled"] == item["total"] for item in report["searches"])
    )
```

- [ ] **Step 2: 运行搜索编排测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_keyword_union_searches_every_query_term_and_merges_guid -v
```

Expected: FAIL，现有编排器只会调用高精度 `assess_primary_domain`。

- [ ] **Step 3: 分离 domain_gate 与 keyword_union 分支**

`run_export_job` 继续共享以下阶段：

1. 每个查询项分页至服务端 `totalNotes`；
2. GUID 合并并按 `updated`、`created`、GUID 倒序；
3. 限流等待预算；
4. 原子状态文件；
5. 索引重建与完整性扫描。

`keyword_union` 分支使用 `selection_hash = keyword_selection_hash(job.domains, job.aliases)`。搜索报告每行包含：

```json
{
  "domain": "AI",
  "canonical_keyword": "HugginFace",
  "query_term": "HuggingFace",
  "total": 12,
  "pulled": 12
}
```

- [ ] **Step 4: 写缓存先提交、同 Note 物化和拒绝缓存测试**

```python
def test_keyword_analysis_is_committed_before_materialization(self):
    store = FakeNoteStore(
        search_results={"AI": [metadata("guid-1", "AI Agent")]},
        notes={"guid-1": full_note("guid-1", "AI Agent", "AI Agent")},
    )
    with mock.patch(
        "scripts.export_multi_domain.export_note_to_obsidian",
        side_effect=RuntimeError("模拟写入中断"),
    ):
        with self.assertRaisesRegex(RuntimeError, "模拟写入中断"):
            run_keyword_job(
                normalize_job(keyword_union_payload(), self.vault),
                store,
            )
    selection_hash = keyword_selection_hash(
        normalize_job(keyword_union_payload(), self.vault).domains,
        normalize_job(keyword_union_payload(), self.vault).aliases,
    )
    with ExportCatalog(self.catalog_path) as catalog:
        entry = catalog.get_keyword_current(
            "guid-1", metadata("guid-1", "AI Agent").updated,
            selection_hash,
        )
    self.assertEqual(entry.outcome, "accepted")
    self.assertIsNone(entry.canonical_path)
```

```python
def test_no_literal_boundary_match_is_cached_as_rejected(self):
    store = FakeNoteStore(
        search_results={"AI": [metadata("guid-1", "training")]},
        notes={"guid-1": full_note("guid-1", "training", "training")},
    )
    report = run_keyword_job(
        normalize_job(keyword_union_payload(), self.vault),
        store,
    )
    self.assertEqual(report["candidates"]["rejected"], 1)
    self.assertEqual(report["materialization"]["written"], 0)
```

- [ ] **Step 5: 实现逐篇缓存优先处理**

每个候选严格执行：

1. 查询 `(guid, updated_ms, selection_hash)`；
2. 缓存命中且规范文件和附件完整时记为 `already_exported`；
3. 缓存命中但已接受且文件缺失时只重新调用一次 `getNote` 物化；
4. 缓存命中且已拒绝时不请求正文；
5. 缓存未命中或失效时调用一次 `getNote`；
6. 运行关键词匹配，先提交 `keyword_analyses`；
7. 接受项使用同一个 Note 对象写 Markdown 和附件，再更新 `canonical_path`；
8. 处理完一个 GUID 后原子更新运行状态。

标题去重必须在关键词分析之后执行，保证每个搜索候选都有 SQLite 分析记录。较新的同标题候选先分析；首个接受项成为规范文件，其余匹配版本更新缓存结果为 `duplicate_title`，不写文件。

- [ ] **Step 6: 写断点续跑和缓存节省正文请求测试**

```python
def test_keyword_job_resumes_from_sqlite_without_refetching_analysis(self):
    job = normalize_job(keyword_union_payload(), self.vault)
    first_store = FakeNoteStore.with_keyword_notes(
        [
            ("guid-1", "AI Agent", "AI Agent"),
            ("guid-2", "MCP", "MCP"),
        ]
    )
    first_store.fail_materialization_for = "guid-2"
    with self.assertRaises(RuntimeError):
        run_keyword_job(job, first_store)
    second_store = FakeNoteStore.with_keyword_notes(
        [
            ("guid-1", "AI Agent", "AI Agent"),
            ("guid-2", "MCP", "MCP"),
        ]
    )
    report = run_keyword_job(job, second_store)
    self.assertEqual(second_store.get_note_calls["guid-1"], 0)
    self.assertEqual(second_store.get_note_calls["guid-2"], 1)
    self.assertGreaterEqual(report["cache"]["hits"], 2)
```

- [ ] **Step 7: 运行编排测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_export_multi_domain -v
```

Expected: PASS。

- [ ] **Step 8: 提交关键词编排器**

```powershell
git add scripts/export_multi_domain.py tests/test_export_multi_domain.py
git commit -m "实现关键词缓存优先导出"
```

---

### Task 7: 正式写入前创建可验证快照

**Files:**
- Create: `scripts/export_snapshot.py`
- Create: `tests/test_export_snapshot.py`
- Modify: `scripts/export_multi_domain.py`

**Interfaces:**
- Produces: `create_domain_snapshot(vault, domains, snapshot_dir, job_id) -> SnapshotResult`
- Produces: ZIP file and adjacent `.sha256.json`
- Consumes: normalized Vault and domain paths

- [ ] **Step 1: 写快照内容和哈希失败测试**

```python
def test_snapshot_contains_only_declared_domain_files_and_manifest(self):
    ai = self.vault / "30_精选资料" / "AI"
    ai.mkdir(parents=True)
    (ai / "文章.md").write_text("AI", encoding="utf-8")
    outside = self.vault / "20_知识笔记"
    outside.mkdir(parents=True)
    (outside / "不要打包.md").write_text("outside", encoding="utf-8")
    result = create_domain_snapshot(
        self.vault,
        ("AI",),
        self.vault / ".state/yinxiang-notes/snapshots",
        "job-1",
    )
    with zipfile.ZipFile(result.archive) as archive:
        names = set(archive.namelist())
    self.assertIn("30_精选资料/AI/文章.md", names)
    self.assertNotIn("20_知识笔记/不要打包.md", names)
    manifest = json.loads(
        result.manifest.read_text(encoding="utf-8")
    )
    self.assertEqual(manifest["archive_sha256"], sha256(result.archive))
```

- [ ] **Step 2: 运行快照测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_snapshot -v
```

Expected: FAIL，提示 `scripts.export_snapshot` 不存在。

- [ ] **Step 3: 实现确定性 ZIP 和 SHA-256 清单**

归档名称固定为 `f"{job_id}-before.zip"`。ZIP 只包含任务 `domains` 中已存在的 `vault / "30_精选资料" / domain` 文件，成员名使用 Vault 相对 POSIX 路径并按名称排序。清单包含每个成员的路径、大小、SHA-256，以及最终 ZIP 的大小和 SHA-256。目标 ZIP 或清单已存在且哈希不同则停止，不覆盖。

- [ ] **Step 4: 将快照接入 keyword_union 首次写入**

`run_export_job` 在打开 SQLite 并完成 Vault 回填后、第一次 Markdown 或附件写入前创建一次快照；快照路径写入运行状态和最终报告。续跑时校验既有快照哈希，不重复生成。

- [ ] **Step 5: 运行快照和编排测试**

Run:

```powershell
python -m unittest tests.test_export_snapshot tests.test_export_multi_domain -v
```

Expected: PASS。

- [ ] **Step 6: 提交写入前快照**

```powershell
git add scripts/export_snapshot.py tests/test_export_snapshot.py scripts/export_multi_domain.py tests/test_export_multi_domain.py
git commit -m "增加批量导出前快照"
```

---

### Task 8: 扩展完整性验收与 SQLite/文件对账

**Files:**
- Modify: `scripts/export_integrity.py:115-297`
- Modify: `tests/test_export_integrity.py`
- Modify: `scripts/export_multi_domain.py`

**Interfaces:**
- Produces: `scan_keyword_export_integrity(vault, domains, since, until, selection_hash, catalog_path, expected_candidates) -> ExportIntegrityReport`
- Validates frontmatter: `selection_mode`, `matched_keywords`, `selection_hash`
- Validates SQLite: every expected GUID has current keyword analysis

- [ ] **Step 1: 写关键词 frontmatter 和 SQLite 对账失败测试**

```python
def test_keyword_integrity_reports_missing_cache_and_wrong_selection(self):
    seed_keyword_markdown(
        self.vault,
        domain="AI",
        title="AI Agent",
        guid="guid-1",
        created="2026-01-01 00:00:00",
        selection_hash="wrong",
        matched_keywords=["AI", "Agent"],
    )
    with ExportCatalog(self.catalog_path) as catalog:
        pass
    report = scan_keyword_export_integrity(
        self.vault,
        domains=("AI",),
        since=datetime(2026, 4, 1),
        until=datetime(2026, 8, 1),
        selection_hash="selection-1",
        catalog_path=self.catalog_path,
        expected_candidates={"guid-1": 1000, "guid-2": 2000},
    )
    kinds = {
        issue.kind
        for domain in report.domains.values()
        for issue in domain.issues
    }
    self.assertIn("selection_hash_mismatch", kinds)
    self.assertIn("missing_keyword_cache", kinds)
```

- [ ] **Step 2: 运行关键词完整性测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_integrity.ExportIntegrityTests.test_keyword_integrity_reports_missing_cache_and_wrong_selection -v
```

Expected: FAIL，关键词完整性入口不存在。

- [ ] **Step 3: 实现关键词完整性检查**

检查项固定为：

- 每篇关键词导出文件 `selection_mode == keyword_union`；
- `selection_hash` 与本任务一致；
- `matched_keywords` 是非空数组且每项属于任务规范关键词；
- `created` 位于 `[since, until)`；
- `source_guid` 在 SQLite 中存在当前分析记录；
- SQLite 接受项的 `canonical_path` 存在且指向相同 GUID；
- SQLite 拒绝项和 `duplicate_title` 项没有规范文件；
- `expected_candidates` 中每个 GUID 都有相同 `updated_ms` 和 `selection_hash` 的当前分析记录；
- 每个本地附件引用存在；
- 每个目录索引完整；
- 领域内和跨领域 GUID、标题重复为零。

- [ ] **Step 4: 把服务端查询对账并入最终 ok**

最终报告：

```python
searches_complete = all(
    item["pulled"] == item["total"]
    for item in search_stats
)
candidate_cache_complete = (
    cache_counts["rows_for_candidates"] == counts["unique_guids"]
)
report["ok"] = (
    searches_complete
    and candidate_cache_complete
    and integrity.ok
)
```

报告同时给出 63 个规范关键词统计、65 个查询项统计、唯一 GUID 数、正文请求数、缓存命中数、接受数、拒绝数、同标题重复数、实际写入数、已存在数、附件引用数和快照路径。`candidate_manifest` 为每个本次候选保存 `guid`、`updated_ms` 和最终 `outcome`，用于不依赖标题或正文的 SQLite 对账。`integrity_summary` 按问题类型输出整数计数，键固定为 `missing_attachments`、`missing_index_targets`、`index_missing_articles`、`domain_duplicates`、`cross_domain_guid_duplicates`、`cross_domain_title_duplicates`、`selection_hash_mismatches`、`missing_keyword_cache` 和 `out_of_range_articles`。

- [ ] **Step 5: 写候选总数恒等式测试**

```python
def test_keyword_report_accounts_for_every_unique_guid(self):
    report = run_keyword_fixture_job(self.vault)
    counts = report["candidates"]
    self.assertEqual(
        counts["unique_guids"],
        counts["accepted"]
        + counts["rejected"]
        + counts["duplicate_titles"],
    )
    self.assertEqual(
        report["cache"]["rows_for_candidates"],
        counts["unique_guids"],
    )
    self.assertTrue(report["searches_complete"])
```

- [ ] **Step 6: 运行完整性与编排测试**

Run:

```powershell
python -m unittest tests.test_export_integrity tests.test_export_multi_domain -v
```

Expected: PASS。

- [ ] **Step 7: 提交关键词完整性验收**

```powershell
git add scripts/export_integrity.py tests/test_export_integrity.py scripts/export_multi_domain.py tests/test_export_multi_domain.py
git commit -m "完善关键词导出完整性验收"
```

---

### Task 9: 更新使用文档和行为契约

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Documents: `keyword_union` 触发条件、日期语义、UTF-8 任务文件、SQLite 缓存、快照、续跑、`两性情感` 领域名、旧目录迁移和完成门禁。

- [ ] **Step 1: 写文档契约失败测试**

```python
def test_keyword_union_workflow_is_documented(self):
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    for text in (skill, readme):
        self.assertIn("selection_mode", text)
        self.assertIn("keyword_union", text)
        self.assertIn("keyword_analyses", text)
        self.assertIn("HuggingFace", text)
        self.assertIn("pulled == total", text)
        self.assertIn("2026-04-01", text)
        self.assertIn("两性情感", text)
        self.assertNotIn("婚姻情感", text)
        self.assertIn("不保存完整正文", text)
```

- [ ] **Step 2: 运行文档测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_keyword_union_workflow_is_documented -v
```

Expected: FAIL，当前文档只有高精度领域模式。

- [ ] **Step 3: 更新 SKILL 和 README**

文档必须给出以下正式命令，且明确禁止把中文 JSON 通过 PowerShell 管道传给 Python：

```powershell
$env:PYTHONUTF8 = "1"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$vault = python -c "from scripts.runtime import load_vault_root; print(load_vault_root())"
$jobDir = Join-Path $vault ".state\yinxiang-notes\jobs"
New-Item -ItemType Directory -Force -Path $jobDir | Out-Null
$job = Join-Path $jobDir "2026-01-01-to-2026-04-01-keyword-union.json"
Copy-Item -LiteralPath "templates\keyword-union-export-job.json" -Destination $job
python scripts/export_multi_domain.py `
  --job $job `
  --rate-limit-mode wait `
  --max-rate-limit-wait 3600
```

说明退出码 75 时保留状态并使用同一命令续跑；退出码 1 时必须读取 JSON 报告，不得声称完成。七个主题目录使用 `两性情感`，不得继续创建 `婚姻情感`；旧目录内容必须先快照、无覆盖迁移并重建索引后才能删除空目录。

- [ ] **Step 4: 运行文档测试**

Run:

```powershell
python -m unittest tests.test_skill_documentation -v
```

Expected: PASS。

- [ ] **Step 5: 提交文档**

```powershell
git add SKILL.md README.md tests/test_skill_documentation.py
git commit -m "补充关键词穷尽导出说明"
```

---

### Task 10: 全量自动化验证

**Files:**
- Modify only files implicated by verification failures.

**Interfaces:**
- Verifies all production, test, template and documentation contracts.

- [ ] **Step 1: 运行完整单元测试**

Run:

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: 0 failures，0 errors。

- [ ] **Step 2: 运行编译和差异检查**

Run:

```powershell
python -m compileall -q scripts tests
git diff --check
```

Expected: 两个命令退出码均为 0。

- [ ] **Step 3: 校验模板编码、关键词数量和任务解析**

Run:

```powershell
python -c "import json,pathlib; p=json.loads(pathlib.Path('templates/keyword-union-export-job.json').read_text(encoding='utf-8')); ks=[k for v in p['domains'].values() for k in v['keywords']]; assert len(ks)==63; assert len(set(ks))==63; print(len(ks))"
python -c "from scripts.export_multi_domain import load_job; from scripts.runtime import load_vault_root; print(load_job('templates/keyword-union-export-job.json', load_vault_root()))"
```

Expected: 第一条输出 `63`；第二条成功打印规范化任务，日期为 2026-01-01 和 2026-04-01，模式为 `keyword_union`。

- [ ] **Step 4: 校验无凭据或真实正文进入仓库**

Run:

```powershell
rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" .
git ls-files .env
git status --short
```

Expected: 真实令牌模式搜索无匹配，实际 `.env` 未被 Git 跟踪；Git 状态只包含本计划涉及的代码、测试、模板和文档。

- [ ] **Step 5: 提交验证修正**

只有验证产生实际修正时执行：

```powershell
git add scripts tests templates SKILL.md README.md
git commit -m "修正关键词导出验证问题"
```

---

### Task 11: 正式 Vault 预检和任务部署

**Files:**
- Create outside Git: `$job = Join-Path $vault ".state\yinxiang-notes\jobs\2026-01-01-to-2026-04-01-keyword-union.json"`
- Create outside Git at runtime: `$dbPath = Join-Path $vault ".state\yinxiang-notes\export-catalog.sqlite3"`
- Create outside Git at runtime: `$snapshotPath = Join-Path $vault ".state\yinxiang-notes\snapshots\$jobId-before.zip"`

**Interfaces:**
- Consumes: verified CLI and UTF-8 task template.
- Produces: device-local task, SQLite cache, snapshot, run state and report.

- [ ] **Step 1: 只读验证配置和 Vault**

Run:

```powershell
$env:PYTHONUTF8 = "1"
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
python -c "from scripts.runtime import load_config,load_vault_root; t,u=load_config(); v=load_vault_root(); assert t and u; assert (v/'.obsidian').is_dir(); print(v)"
```

Expected: 输出 `D:\OneDrive\文档\@_Obsidian`，不输出 Token 或 NoteStore URL。

- [ ] **Step 2: 确认没有活动写锁**

Run:

```powershell
$vault = python -c "from scripts.runtime import load_vault_root; print(load_vault_root())"
$lock = Join-Path $vault ".state\yinxiang-notes\active-run.lock"
if (Test-Path -LiteralPath $lock) {
  Get-Content -Raw -Encoding utf8 -LiteralPath $lock
  throw "检测到活动写锁，停止正式导出"
}
```

Expected: 锁文件不存在。若存在，停止，不覆盖、不删除。

- [ ] **Step 3: 部署 UTF-8 任务文件并逐字节校验**

Run:

```powershell
$jobDir = Join-Path $vault ".state\yinxiang-notes\jobs"
New-Item -ItemType Directory -Force -Path $jobDir | Out-Null
$job = Join-Path $jobDir "2026-01-01-to-2026-04-01-keyword-union.json"
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath "templates\keyword-union-export-job.json").Hash
if (Test-Path -LiteralPath $job) {
  $existingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $job).Hash
  if ($sourceHash -ne $existingHash) {
    throw "已有任务文件内容不同，未覆盖"
  }
} else {
  Copy-Item -LiteralPath "templates\keyword-union-export-job.json" -Destination $job
}
$targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $job).Hash
if ($sourceHash -ne $targetHash) {
  throw "任务文件复制后哈希不一致"
}
```

Expected: 两个 SHA-256 完全一致。

- [ ] **Step 4: 只解析任务，不访问 API**

Run:

```powershell
python -c "from pathlib import Path; from scripts.export_multi_domain import load_job; from scripts.runtime import load_vault_root; j=load_job(Path(r'$job'), load_vault_root()); assert j.selection_mode=='keyword_union'; assert j.since.isoformat()=='2026-01-01'; assert j.until.isoformat()=='2026-04-01'; assert len({k for v in j.domains.values() for k in v})==63; print('任务校验通过')"
```

Expected: 输出 `任务校验通过`。

- [ ] **Step 5: 只读盘点旧目录与目标目录**

解析并验证以下两个精确路径都位于 `$vault\30_精选资料` 内：

```powershell
$legacyDomain = Join-Path $vault "30_精选资料\婚姻情感"
$currentDomain = Join-Path $vault "30_精选资料\两性情感"
$legacyFiles = @(Get-ChildItem -LiteralPath $legacyDomain -Recurse -File -Force)
$currentFiles = @(Get-ChildItem -LiteralPath $currentDomain -Recurse -File -Force)
$legacyFiles.Count, $currentFiles.Count
```

Expected: 旧目录存在且内容完整；新目录允许已存在。逐相对路径检查冲突，除可重建的 `目录索引.md` 外，任何同路径不同内容文件都停止迁移，不覆盖。

---

### Task 12: 正式缓存、导出和可恢复运行

**Files:**
- Writes only inside the configured Vault.

**Interfaces:**
- Produces: SQLite keyword cache, Markdown, attachments, indexes, snapshot, run state and report.

- [ ] **Step 1: 为目录改名创建独立迁移快照**

使用 `create_domain_snapshot` 对 `婚姻情感` 和 `两性情感` 两个目录创建独立的确定性 ZIP 与 SHA-256 清单，任务 ID 后缀固定为 `-domain-rename`。快照完成且哈希校验通过前不得移动或删除任何文件：

```powershell
$renameSnapshotPath = python -c "from pathlib import Path; from scripts.export_multi_domain import load_job,_job_id; from scripts.export_snapshot import create_domain_snapshot; from scripts.runtime import load_vault_root; v=load_vault_root(); j=load_job(Path(r'$job'),v); r=create_domain_snapshot(v,('\u5a5a\u59fb\u60c5\u611f','\u4e24\u6027\u60c5\u611f'),v/'.state'/'yinxiang-notes'/'snapshots',_job_id(j)+'-domain-rename'); print(r.archive)"
```

Expected: ZIP 和相邻 `.sha256.json` 均存在，清单覆盖旧目录的全部 692 个文件以及新目录已有文件。

- [ ] **Step 2: 安全迁移旧目录内容并删除旧目录**

再次确认 `$legacyDomain` 与 `$currentDomain` 的解析后绝对路径都在 `$vault\30_精选资料` 内。把旧目录下除 `目录索引.md` 外的顶层文件和目录逐项移动到新目录；目标存在时先逐文件比较 SHA-256，完全相同才允许去除旧副本，不同则停止。旧 `目录索引.md` 已进入迁移快照，可删除并由正式导出重建。只有旧目录已空时才删除旧目录，不使用递归强制删除。

Expected: `30_精选资料\婚姻情感` 不再存在，`30_精选资料\两性情感` 包含原有 49 篇 Markdown 和全部 642 个图片资源；正式导出结束后重建 `目录索引.md`。

- [ ] **Step 3: 启动正式导出**

Run:

```powershell
python scripts/export_multi_domain.py `
  --job $job `
  --rate-limit-mode wait `
  --max-rate-limit-wait 3600
```

Expected: 每个查询项完整分页，所有中文关键词保持原文；进程只输出汇总和限流等待摘要。

- [ ] **Step 4: 处理限流退出**

若退出码为 75，保留当前 SQLite、快照、运行状态和已物化文件。服务端建议等待时间结束后重新执行 Step 3 的同一命令，不修改任务 JSON、不创建新任务文件、不删除写锁以外的状态。

- [ ] **Step 5: 处理验收退出**

若退出码为 1，读取终端输出给出的报告路径，按 `integrity.issues` 修复缺失附件、索引、重复或 SQLite/文件对账问题，再用同一任务命令续跑。不得通过手工把报告中的 `ok` 改为 `true`。

- [ ] **Step 6: 记录正式产物路径**

成功运行后先解析任务 ID：

```powershell
$jobId = python -c "from pathlib import Path; from scripts.export_multi_domain import load_job,_job_id; from scripts.runtime import load_vault_root; print(_job_id(load_job(Path(r'$job'),load_vault_root())))"
$dbPath = Join-Path $vault ".state\yinxiang-notes\export-catalog.sqlite3"
$runPath = Join-Path $vault ".state\yinxiang-notes\runs\multi-export-$jobId.json"
$reportPath = Join-Path $vault ".state\yinxiang-notes\reports\$jobId.json"
$snapshotPath = Join-Path $vault ".state\yinxiang-notes\snapshots\$jobId-before.zip"
$renameSnapshotPath = Join-Path $vault ".state\yinxiang-notes\snapshots\$jobId-domain-rename-before.zip"
$domainPaths = @(
  "软件工程", "AI", "Quant", "投资理财",
  "知识管理", "健康医学", "两性情感"
) | ForEach-Object {
  Join-Path $vault "30_精选资料\$_"
}
$dbPath, $job, $runPath, $reportPath, $snapshotPath, $renameSnapshotPath
$domainPaths
```

Expected: 所有输出路径均位于 `$vault` 内；数据库、任务、运行状态、报告、正式写入前快照和目录迁移快照存在，七个主题目录存在，旧 `婚姻情感` 目录不存在。

---

### Task 13: 完成审计和交付

**Files:**
- Read-only verification of Vault and report.

**Interfaces:**
- Proves every objective requirement from current files, SQLite and API reconciliation.

- [ ] **Step 1: 校验报告硬门禁**

```powershell
python -c "import json,pathlib; r=json.loads(pathlib.Path(r'$reportPath').read_text(encoding='utf-8')); assert r['ok'] is True; assert r['job']['since']=='2026-01-01'; assert r['job']['until']=='2026-04-01'; assert r['job']['selection_mode']=='keyword_union'; assert all(x['pulled']==x['total'] for x in r['searches']); assert r['cache']['rows_for_candidates']==r['candidates']['unique_guids']; assert all(v==0 for v in r['integrity_summary'].values()); print(json.dumps({'unique_guids':r['candidates']['unique_guids'],'accepted':r['candidates']['accepted'],'rejected':r['candidates']['rejected'],'duplicates':r['candidates']['duplicate_titles'],'written':r['materialization']['written']},ensure_ascii=False))"
```

Expected: 断言全部通过并输出候选、接受、拒绝、重复和写入数量。

- [ ] **Step 2: 校验 SQLite 候选覆盖**

```powershell
python -c "import json,sqlite3,pathlib; r=json.loads(pathlib.Path(r'$reportPath').read_text(encoding='utf-8')); db=sqlite3.connect(r'$dbPath'); h=r['selection']['hash']; current={(row[0],int(row[1])) for row in db.execute('select guid,updated_ms from keyword_analyses where selection_hash=?',(h,))}; expected={(item['guid'],int(item['updated_ms'])) for item in r['candidate_manifest']}; assert expected<=current; bad=db.execute(\"select count(*) from keyword_analyses where selection_hash=? and outcome not in ('accepted','rejected','duplicate_title')\",(h,)).fetchone()[0]; assert bad==0; print(len(expected))"
```

Expected: 输出值等于报告 `unique_guids`。

- [ ] **Step 3: 校验文件、附件、索引和重复项**

确认报告中以下 `integrity_summary` 字段均为零：

```text
integrity_summary.missing_attachments
integrity_summary.missing_index_targets
integrity_summary.index_missing_articles
integrity_summary.domain_duplicates
integrity_summary.cross_domain_guid_duplicates
integrity_summary.cross_domain_title_duplicates
integrity_summary.selection_hash_mismatches
integrity_summary.missing_keyword_cache
integrity_summary.out_of_range_articles
```

并确认七个领域目录各有 `目录索引.md`；本次新增文章位于 `2026年01月` 至 `2026年03月` 月份目录，旧 `婚姻情感` 中迁移的历史文章仍保留其原月份目录。

同时断言 `30_精选资料\婚姻情感` 不存在、`30_精选资料\两性情感` 存在，且 Vault Markdown 中不再包含指向 `30_精选资料/婚姻情感/` 的内部链接或 `domain: 婚姻情感` 审计字段。

- [ ] **Step 4: 校验用户关键词覆盖**

报告必须列出 63 个不同 `canonical_keyword`，且 `HugginFace` 至少对应三个查询项：`HugginFace`、`HuggingFace`、`Hugging Face`。对零命中关键词也保留 `total: 0`、`pulled: 0` 的记录，不能从报告中省略。

- [ ] **Step 5: 校验本地 Git 工作区与凭据安全**

Run:

```powershell
git status --short
git diff --check
rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" .
git ls-files .env
```

Expected: Vault 正文、SQLite、运行状态、快照和报告都不在 Git 工作区；真实令牌模式搜索无匹配，实际 `.env` 未被 Git 跟踪。

- [ ] **Step 6: 形成最终交付摘要**

最终回复只在前五步全部通过后给出：日期区间、63 个规范关键词、65 个查询项、唯一 GUID 数、接受数、拒绝数、同标题重复数、实际新增/更新 Markdown 数、附件数、SQLite 路径、报告路径、快照路径及 `ok: true`。任何断言失败都报告为未完成并继续修复或续跑。

---

## Self-Review Checklist

- [ ] 63 个规范关键词均在模板和测试的集合断言中。
- [ ] 日期语义在任务、代码测试、文档、正式命令和报告断言中一致。
- [ ] SQLite 历史回填、API 新分析、缓存命中、缓存失效和中断恢复均有独立测试。
- [ ] `keyword_analyses` 与 `parsed_notes` 分离，现有高精度领域模式不被覆盖。
- [ ] 旧 `婚姻情感` 目录已先快照、再迁移到 `两性情感`，冲突未覆盖，旧目录最终不存在。
- [ ] 一个 GUID 单次运行至多一次 `getNote`，接受项复用同一 Note 对象写正文和附件。
- [ ] 快照发生在第一次正式文件写入前。
- [ ] 中文配置只通过 UTF-8 文件传递。
- [ ] 完成条件同时覆盖服务端分页、SQLite、Markdown、附件、索引、日期和重复项。
- [ ] 正式运行不会修改印象笔记账户。
