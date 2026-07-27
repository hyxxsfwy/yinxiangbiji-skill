# 精选资料逐篇审阅与双向链接实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用完整审阅清单安全整理 `30_精选资料`，把错域文档移入 `99_废纸篓`，并为有明确关联的保留文档建立每篇不超过三条的双向自动链接。

**Architecture:** 新增独立脚本读取显式 JSON 审阅清单，先验证 216 篇正文全覆盖，再生成可预览的移动与互链计划。执行阶段先创建 ZIP 与 SHA-256 清单，再复制附件、移动 Markdown、写入受控链接区块、重建索引并输出审核日志。

**Tech Stack:** Python 3.12、`pathlib`、`json`、`zipfile`、`hashlib`、`unittest`、Obsidian Markdown

## Global Constraints

- 只有实际内容与所在领域明显不符的文档进入 `99_废纸篓`。
- 审阅清单必须完整覆盖执行时 `30_精选资料`中的全部正文。
- 自动链接必须双向，每篇最多三条，不得指向待删除或不存在文档。
- 没有强关联的文档不创建自动链接区块。
- 不改写自动链接区块之外的正文。
- 废纸篓文章引用的本地附件必须继续可解析。
- 执行前必须创建 ZIP 与 SHA-256 清单；目标冲突时不得写入。
- 真实 vault 写入要求固定确认词 `CURATE_SELECTED_MATERIALS`。

---

### Task 1: 审阅清单加载与完整性预检

**Files:**
- Create: `scripts/curate_selected_materials.py`
- Create: `tests/test_curate_selected_materials.py`

**Interfaces:**
- Produces: `ReviewItem`、`load_review_manifest(Path) -> tuple[ReviewItem, ...]`
- Produces: `discover_documents(Path) -> tuple[Path, ...]`
- Produces: `validate_review_manifest(Path, tuple[ReviewItem, ...]) -> tuple[str, ...]`

- [ ] **Step 1: Write failing tests**

```python
def test_manifest_requires_exact_document_coverage():
    # 两篇正文，清单漏一篇时报告缺项；多出路径时报告不存在路径。

def test_manifest_rejects_duplicate_paths_invalid_decisions_and_four_links():
    # 重复路径、非 keep/trash、四条 links 都必须返回明确问题。

def test_manifest_requires_symmetric_links_and_keep_targets():
    # A→B 但 B 未链接 A，以及链接到 trash 文档时必须失败。
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m unittest tests.test_curate_selected_materials.ReviewManifestTests -v
```

Expected: FAIL，因为模块和接口尚不存在。

- [ ] **Step 3: Implement minimal schema and validation**

`ReviewItem`字段固定为：

```python
@dataclass(frozen=True)
class ReviewItem:
    path: PurePosixPath
    decision: str
    reason: str
    topic: str
    links: tuple[PurePosixPath, ...]
```

正文发现规则为 `30_精选资料/**/*.md`，排除所有名为 `目录索引.md` 的文件。清单验证比较相对 `30_精选资料` 的 POSIX 路径集合，并逐项验证原因非空、链接不重复、最多三条、双向且两端均为 `keep`。

- [ ] **Step 4: Run focused tests**

```powershell
python -m unittest tests.test_curate_selected_materials.ReviewManifestTests -v
```

Expected: PASS。

### Task 2: 受控自动链接区块

**Files:**
- Modify: `scripts/curate_selected_materials.py`
- Modify: `tests/test_curate_selected_materials.py`

**Interfaces:**
- Produces: `render_auto_links(markdown: str, links: tuple[ReviewItem, ...]) -> str`
- Produces: `extract_auto_link_targets(markdown: str) -> tuple[str, ...]`

- [ ] **Step 1: Write failing tests**

```python
def test_adds_sorted_links_without_changing_existing_body():
    # 原正文逐字保留，在末尾增加一个相关笔记区块。

def test_replaces_existing_managed_block_idempotently():
    # 重复执行不产生第二个标题或第二组标记。

def test_removes_managed_section_when_links_become_empty():
    # 没有链接时完整删除自动生成的标题和标记区块。
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m unittest tests.test_curate_selected_materials.AutoLinkTests -v
```

Expected: FAIL，因为链接渲染接口尚不存在。

- [ ] **Step 3: Implement deterministic rendering**

固定标记：

```python
AUTO_LINKS_START = "<!-- llmwiki:auto-links:start -->"
AUTO_LINKS_END = "<!-- llmwiki:auto-links:end -->"
```

链接格式为 `[[30_精选资料/<path-without-.md>|<stem>]]`。替换时只操作 `## 相关笔记`及两标记覆盖的受控区块；区块外文本字节内容不变。

- [ ] **Step 4: Run focused tests**

```powershell
python -m unittest tests.test_curate_selected_materials.AutoLinkTests -v
```

Expected: PASS。

### Task 3: 备份、附件保全、移动与验证

**Files:**
- Modify: `scripts/curate_selected_materials.py`
- Modify: `tests/test_curate_selected_materials.py`

**Interfaces:**
- Produces: `build_curation_plan(vault: Path, reviews: tuple[ReviewItem, ...]) -> CurationPlan`
- Produces: `create_snapshot(CurationPlan, zip_path: Path, manifest_path: Path) -> None`
- Produces: `apply_curation(CurationPlan) -> None`
- Produces: `validate_completed_curation(CurationPlan) -> tuple[str, ...]`

- [ ] **Step 1: Write failing integration tests**

```python
def test_apply_moves_trash_markdown_and_copies_referenced_asset():
    # Markdown 进入废纸篓镜像路径，附件在镜像 _attachments 中存在且哈希一致。

def test_preflight_rejects_different_existing_destination_before_snapshot():
    # 同路径异内容时不产生 ZIP、清单或正文修改。

def test_snapshot_contains_every_modified_markdown_and_trash_asset():
    # ZIP 条目与 SHA-256 清单一致。

def test_completed_validation_checks_count_links_reciprocity_and_assets():
    # 人为删除附件或反向链接后必须报告失败。
```

- [ ] **Step 2: Run integration tests and verify RED**

```powershell
python -m unittest tests.test_curate_selected_materials.CurationIntegrationTests -v
```

Expected: FAIL，因为计划、快照、迁移和完成验证接口尚不存在。

- [ ] **Step 3: Implement transactional curation**

计划包含所有会被移动或写入自动链接的 Markdown，以及待移动文章引用的 vault 内非 Markdown 文件。ZIP 使用 vault 相对路径；JSON 清单逐文件记录 `path`、`size`、`sha256`。

执行顺序固定为附件复制、Markdown 移动、自动链接写入、领域索引重建、审核日志写入。异常时从 ZIP 恢复所有快照文件，并删除本次新建但快照中不存在的废纸篓 Markdown。

- [ ] **Step 4: Run complete curation tests**

```powershell
python -m unittest tests.test_curate_selected_materials -v
```

Expected: PASS。

### Task 4: 完成 216 篇显式审阅清单

**Files:**
- Create: `reviews/2026-07-27-selected-materials-review.json`
- Modify: `tests/test_curate_selected_materials.py`

**Interfaces:**
- Consumes: 当前真实 vault 的 216 篇正文
- Produces: 每篇唯一的 `decision`、`reason`、`topic`和最多三条对称链接

- [ ] **Step 1: Add repository contract test**

```python
def test_real_review_manifest_has_explicit_unique_entries():
    # JSON 每个对象都显式包含五个字段，不允许依靠默认 keep。
```

- [ ] **Step 2: Generate and manually review the manifest**

以标题、frontmatter、首段、目录和图片型笔记为证据，为当前 216 篇正文逐项填写。错域判断使用设计文档中的三个领域定义；链接只使用人工确认的主题组和显式跨域关系。

- [ ] **Step 3: Run read-only preview against the real vault**

```powershell
python scripts/curate_selected_materials.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --review "reviews\2026-07-27-selected-materials-review.json"
```

Expected: 返回 0，输出总数 216、保留数、废纸篓数、双向边数和零冲突；真实 vault 文件时间不变。

### Task 5: 执行真实 vault 整理并完成审计

**Files:**
- Modify: `D:\OneDrive\文档\@_Obsidian\30_精选资料\**`
- Create: `D:\OneDrive\文档\@_Obsidian\99_废纸篓\30_精选资料\**`
- Create: `D:\OneDrive\文档\@_Obsidian\80_系统\知识库治理\变更快照\2026-07-27-精选资料整理前.*`
- Create: `D:\OneDrive\文档\@_Obsidian\80_系统\知识库治理\审核日志\2026-07-27-精选资料逐篇审阅.md`

**Interfaces:**
- Consumes: 通过 Task 4 预检的审阅清单
- Produces: 整理后的真实 vault、备份、清单和逐篇审阅日志

- [ ] **Step 1: Execute with exact confirmation**

```powershell
python scripts/curate_selected_materials.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --review "reviews\2026-07-27-selected-materials-review.json" `
  --apply `
  --confirm CURATE_SELECTED_MATERIALS
```

- [ ] **Step 2: Run curation-specific verification**

```powershell
python scripts/curate_selected_materials.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --review "reviews\2026-07-27-selected-materials-review.json" `
  --verify
```

Expected: 216 篇全部可追踪；自动链接双向且每篇不超过三条；图片和附件完整。

- [ ] **Step 3: Run repository and vault verification**

```powershell
python -m unittest discover -s tests
python -m compileall -q scripts tests
git diff --check
python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --verify
```

Expected: 所有命令返回 0。

- [ ] **Step 4: Commit repository artifacts**

```powershell
git add scripts/curate_selected_materials.py tests/test_curate_selected_materials.py reviews/2026-07-27-selected-materials-review.json docs/superpowers/plans/2026-07-27-selected-materials-domain-and-links.md
git commit -m "整理精选资料领域并建立双向链接"
```
