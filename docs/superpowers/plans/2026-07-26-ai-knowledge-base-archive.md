# AI 知识库月度归档与索引 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让印象笔记搜索结果按创建月份归档到 Obsidian，在根目录生成包含位置和“首段正文 + 目录大纲”简介的 Markdown 索引，并消除标题完全一致的重复剪藏。

**Architecture:** 新增 `scripts/knowledge_base.py`，集中处理月度路径、Markdown 元数据、简介、迁移、去重和索引。`export_search_results.py` 仍负责搜索与下载，但在限制数量前按标题去重，并在全部导出成功后调用知识库整理流程；`sync_to_obsidian.py` 只扩展附件相对路径参数，默认同步行为不变。

**Tech Stack:** Python 3.12、标准库 `dataclasses/pathlib/re/json/urllib.parse`、Evernote EDAM、`unittest`、Obsidian Markdown。

## Global Constraints

- 月份只取笔记 `created`，目录格式固定为 `YYYY年MM月`。
- 标题完全一致时，依次比较 `updated`、`created`、GUID，保留排序最大的一篇。
- 去重必须发生在 `--limit` 之前。
- 附件保留在知识库根目录 `_attachments/`，月度文章使用 `../_attachments/`。
- 根目录索引固定为普通 Markdown 文件 `目录索引.md`，不得依赖 Dataview。
- 简介由首段有效正文和最多四个二、三级标题组合，不调用外部大模型。
- 真实开发者令牌不得写入代码、测试、文档或 Git。
- 规范来源：`docs/superpowers/specs/2026-07-26-ai-knowledge-base-archive-design.md`。

---

### Task 1: 搜索结果按完全一致标题去重

**Files:**
- Modify: `scripts/export_search_results.py:70-91`
- Modify: `tests/test_export_search_results.py:36-84`

**Interfaces:**
- Consumes: Evernote 元数据对象的 `guid`、`title`、`updated`、`created`。
- Produces: `select_top_notes(search_batches, keywords, limit)`，返回标题唯一且已排序的列表。

- [ ] **Step 1: 写入同标题保留规则的失败测试**

```python
def test_deduplicates_exact_titles_before_applying_limit(self):
    from scripts.export_search_results import select_top_notes

    older = SimpleNamespace(
        guid="same-old",
        title="Agent 重复剪藏",
        created=100,
        updated=200,
    )
    newer = SimpleNamespace(
        guid="same-new",
        title="Agent 重复剪藏",
        created=150,
        updated=300,
    )
    same_updated_newer_created = SimpleNamespace(
        guid="same-created",
        title="Agent 重复剪藏",
        created=180,
        updated=300,
    )
    unique = SimpleNamespace(
        guid="unique",
        title="AI 唯一文章",
        created=120,
        updated=250,
    )

    selected = select_top_notes(
        [[older, newer, unique, same_updated_newer_created]],
        keywords=["AI", "Agent"],
        limit=2,
    )

    self.assertEqual(
        [note.guid for note in selected],
        ["same-created", "unique"],
    )
    self.assertEqual(len({note.title for note in selected}), 2)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_search_results.SearchQueryTests.test_deduplicates_exact_titles_before_applying_limit -v
```

Expected: FAIL，旧实现按 GUID 保留三篇同标题候选，`limit=2` 后缺少 `unique`。

- [ ] **Step 3: 实现 GUID 去重后的标题胜出规则**

```python
def note_freshness_key(note):
    return (
        getattr(note, "updated", 0) or 0,
        getattr(note, "created", 0) or 0,
        str(getattr(note, "guid", "") or ""),
    )


def deduplicate_notes_by_title(notes):
    winners = {}
    for note in notes:
        title_key = (getattr(note, "title", "") or "").strip()
        existing = winners.get(title_key)
        if existing is None or note_freshness_key(note) > note_freshness_key(
            existing
        ):
            winners[title_key] = note
    return list(winners.values())
```

在 `select_top_notes` 中先构建 `notes_by_guid`，再调用 `deduplicate_notes_by_title(notes_by_guid.values())`，最后排序并应用 `[:limit]`。

- [ ] **Step 4: 运行搜索选择测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_export_search_results.SearchQueryTests -v
```

Expected: 现有搜索测试和新增同标题测试全部 PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add scripts/export_search_results.py tests/test_export_search_results.py
git commit -m "实现印象笔记搜索结果按标题去重"
```

---

### Task 2: 月度输出路径与跨目录附件引用

**Files:**
- Create: `scripts/knowledge_base.py`
- Modify: `scripts/sync_to_obsidian.py:186-230,406-453`
- Modify: `scripts/export_search_results.py:128-181`
- Modify: `tests/test_export_search_results.py:144-266,399-408`
- Create: `tests/test_knowledge_base.py`

**Interfaces:**
- Produces: `month_folder_name(created: datetime) -> str`。
- Extends: `html_to_md(content, hash_to_file, attachment_prefix="_attachments")`。
- Extends: `make_attachment_link(fname, prefix="_attachments")`。
- Extends: `make_attachments_section(hash_to_file, exclude_filenames=None, prefix="_attachments")`。
- Extends: `referenced_attachment_filenames(markdown_body, hash_to_file, prefix="_attachments")`。

- [ ] **Step 1: 写入月份格式和月度导出的失败测试**

```python
def make_inline_image_note(title, guid, created):
    image_data = b"monthly-image"
    image_hash = hashlib.md5(image_data).hexdigest()
    resource = SimpleNamespace(
        data=SimpleNamespace(body=image_data),
        mime="image/png",
        attributes=SimpleNamespace(fileName="monthly.png"),
    )
    return SimpleNamespace(
        guid=guid,
        title=title,
        created=created,
        updated=created,
        content=(
            "<en-note><div>正文</div>"
            f'<en-media type="image/png" hash="{image_hash}"/>'
            "</en-note>"
        ),
        resources=[resource],
    )


class MonthFolderTests(unittest.TestCase):
    def test_formats_created_time_as_chinese_month_folder(self):
        from scripts.knowledge_base import month_folder_name

        self.assertEqual(
            month_folder_name(datetime(2026, 7, 24, 11, 0)),
            "2026年07月",
        )


class ExportNoteTests(unittest.TestCase):
    def test_exports_note_into_created_month_with_root_attachments(self):
        from scripts.export_search_results import export_note_to_obsidian

        note = make_inline_image_note(
            title="Agent 月度文章",
            guid="monthly-guid",
            created=1784852427000,
        )
        with workspace_temp_dir() as root:
            exported = export_note_to_obsidian(note, "微信", root)
            markdown = exported.read_text(encoding="utf-8")

            self.assertEqual(exported.parent.name, "2026年07月")
            self.assertTrue((root / "_attachments").is_dir())
            self.assertIn("../_attachments/", markdown)
            self.assertNotIn("](_attachments/", markdown)
```

测试中把现有图片笔记构造逻辑提取到 `make_inline_image_note`，避免复制资源对象。

- [ ] **Step 2: 运行月份和导出测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_knowledge_base.MonthFolderTests tests.test_export_search_results.ExportNoteTests -v
```

Expected: ERROR，`scripts.knowledge_base` 不存在；导出文件仍位于根目录且图片引用仍为 `_attachments/`。

- [ ] **Step 3: 创建月份函数并给附件辅助函数增加前缀**

```python
# scripts/knowledge_base.py
from datetime import datetime


INDEX_FILENAME = "目录索引.md"


def month_folder_name(created: datetime) -> str:
    return created.strftime("%Y年%m月")
```

```python
# scripts/sync_to_obsidian.py
def make_attachment_link(fname, prefix="_attachments"):
    ext = os.path.splitext(fname)[1].lower()
    label = fname.replace("[", r"\[").replace("]", r"\]")
    url = attachment_url(fname, prefix=prefix)
    if ext in IMAGE_EXTS:
        return f"![{label}]({url})"
    return f"[{label}]({url})"


def html_to_md(content, hash_to_file, attachment_prefix="_attachments"):
    def en_media_to_img(match):
        resource_hash = match.group(1).lower()
        if hash_to_file and resource_hash in hash_to_file:
            filename = hash_to_file[resource_hash]
            url = html_module.escape(
                attachment_url(filename, prefix=attachment_prefix),
                quote=True,
            )
            alt = html_module.escape(filename, quote=True)
            return f'<img src="{url}" alt="{alt}">'
        url = attachment_url(resource_hash, prefix=attachment_prefix)
        return f'<img src="{url}" alt="{resource_hash}">'
```

`make_attachments_section` 和 `referenced_attachment_filenames` 同样把 `prefix` 传给 `make_attachment_link`、`attachment_url`，默认参数保持现有整库同步行为。

- [ ] **Step 4: 把单篇导出目标改为月度目录**

```python
created = datetime.fromtimestamp(note.created / 1000)
month_dir = target_dir / month_folder_name(created)
month_dir.mkdir(parents=True, exist_ok=True)
attachment_prefix = "../_attachments"

body = html_to_md(
    content,
    hash_to_file,
    attachment_prefix=attachment_prefix,
)

output_path = resolve_note_path(
    month_dir,
    note.title,
    note.guid,
    {},
)
```

附件仍保存到 `target_dir / "_attachments"`；附件 section 和已引用附件判断统一传入 `attachment_prefix`。

- [ ] **Step 5: 更新旧断言并运行导出相关测试**

Run:

```powershell
python -m unittest tests.test_knowledge_base.MonthFolderTests tests.test_export_search_results.ExportNoteTests tests.test_export_search_results.HtmlConversionTests tests.test_export_search_results.AttachmentLinkTests -v
```

Expected: 全部 PASS；默认 `html_to_md` 测试继续得到 `_attachments/`，月度导出得到 `../_attachments/`。

- [ ] **Step 6: 提交本任务**

```powershell
git add scripts/knowledge_base.py scripts/sync_to_obsidian.py scripts/export_search_results.py tests/test_knowledge_base.py tests/test_export_search_results.py
git commit -m "实现 AI 知识库按创建月份导出"
```

---

### Task 3: Markdown 元数据、综合简介与目录索引

**Files:**
- Modify: `scripts/knowledge_base.py`
- Modify: `tests/test_knowledge_base.py`

**Interfaces:**
- Produces: `KnowledgeBaseNote(path, title, created, updated, guid)`。
- Produces: `extract_note_metadata(markdown_path: Path) -> KnowledgeBaseNote`。
- Produces: `build_note_summary(markdown_text: str, title: str) -> str`。
- Produces: `write_knowledge_base_index(root: Path) -> Path`。

- [ ] **Step 1: 写入综合简介的失败测试**

```python
def write_note(path, title, created, updated, guid, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'created: "{created}"\n'
            f'updated: "{updated}"\n'
            f'source_guid: "{guid}"\n'
            "---\n\n"
            f"# {title}\n\n"
            f"{body}\n"
        ),
        encoding="utf-8",
    )
    return path


class SummaryTests(unittest.TestCase):
    def test_combines_first_effective_paragraph_with_outline(self):
        from scripts.knowledge_base import build_note_summary

        markdown = """---
created: "2026-07-24 11:00:27"
updated: "2026-07-26 09:00:00"
source_guid: "summary-guid"
---

# Agent 文章

原文链接: [来源](https://example.com)

关注公众号获取更多内容

这篇文章解释 Agent 为什么会在长上下文中遗漏关键规则。第二句不进入首句摘要。

## 01 注意力机制

### 1.1 中间位置衰减

## 02 工程化解法
"""
        summary = build_note_summary(markdown, "Agent 文章")

        self.assertIn(
            "这篇文章解释 Agent 为什么会在长上下文中遗漏关键规则。",
            summary,
        )
        self.assertIn("“注意力机制”", summary)
        self.assertIn("“中间位置衰减”", summary)
        self.assertIn("“工程化解法”", summary)
        self.assertNotIn("原文链接", summary)
        self.assertLessEqual(summary.count("。"), 2)
```

再增加纯图片回退测试，断言结果等于：

```python
"该笔记主要以图片形式呈现“一张图看懂 AI Agent 全流程”相关内容。"
```

- [ ] **Step 2: 运行简介测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_knowledge_base.SummaryTests -v
```

Expected: ImportError，简介函数尚不存在。

- [ ] **Step 3: 实现 Markdown 扫描和简介组合**

```python
HEADING_PATTERN = re.compile(r"^#{2,3}\s+(?:\d+(?:\.\d+)*\s+)?(.+?)\s*$")
SENTENCE_PATTERN = re.compile(r"^(.+?[。！？!?])(?:\s|$)")


def build_note_summary(markdown_text, title):
    body_lines = markdown_body_lines(markdown_text)
    paragraph = first_effective_paragraph(body_lines)
    outline = unique_outline_titles(body_lines, limit=4)
    if not paragraph:
        return f"该笔记主要以图片形式呈现“{title}”相关内容。"

    first_sentence = first_complete_sentence(paragraph, max_length=180)
    if not outline:
        return first_sentence
    quoted = "、".join(f"“{heading}”" for heading in outline)
    return f"{first_sentence}本文目录包括{quoted}等内容。"
```

`first_effective_paragraph` 必须跳过 frontmatter、一级标题、`原文链接`、包含“关注”且长度少于 80 的推广行、图片、表格、代码块、分隔线和纯标题。`unique_outline_titles` 去掉 `01`、`1.1` 等编号并保持首次出现顺序。

- [ ] **Step 4: 写入索引顺序、路径和简介的失败测试**

```python
class IndexTests(unittest.TestCase):
    def test_writes_months_and_notes_in_descending_order(self):
        from scripts.knowledge_base import write_knowledge_base_index

        with workspace_temp_dir() as root:
            write_note(
                root / "2026年06月" / "六月文章.md",
                title="六月文章",
                created="2026-06-30 09:00:00",
                updated="2026-07-01 09:00:00",
                guid="june",
                body="六月正文内容足够形成文章简介。",
            )
            write_note(
                root / "2026年07月" / "七月文章.md",
                title="七月文章",
                created="2026-07-24 11:00:27",
                updated="2026-07-26 09:00:00",
                guid="july",
                body="七月正文内容足够形成文章简介。\n\n## 章节主题",
            )

            index_path = write_knowledge_base_index(root)
            index = index_path.read_text(encoding="utf-8")

        self.assertLess(index.index("## 2026年07月"), index.index("## 2026年06月"))
        self.assertIn("位置：`2026年07月/七月文章.md`", index)
        self.assertIn(
            "[七月文章](2026%E5%B9%B407%E6%9C%88/%E4%B8%83%E6%9C%88%E6%96%87%E7%AB%A0.md)",
            index,
        )
        self.assertIn("简介：七月正文内容足够形成文章简介。", index)
```

- [ ] **Step 5: 运行索引测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_knowledge_base.IndexTests -v
```

Expected: ImportError，索引函数尚不存在。

- [ ] **Step 6: 实现元数据解析和原子索引写入**

```python
@dataclass(frozen=True)
class KnowledgeBaseNote:
    path: Path
    title: str
    created: datetime
    updated: datetime
    guid: str


def write_knowledge_base_index(root):
    root = Path(root)
    notes = [
        extract_note_metadata(path)
        for path in root.glob("[0-9][0-9][0-9][0-9]年[0-9][0-9]月/*.md")
    ]
    notes.sort(key=lambda note: (note.created, note.title), reverse=True)
    grouped = {}
    for note in notes:
        grouped.setdefault(note.path.parent.name, []).append(note)

    lines = ["# AI 相关知识库目录", ""]
    for month in sorted(grouped, reverse=True):
        lines.extend([f"## {month}", ""])
        for note in grouped[month]:
            relative = note.path.relative_to(root).as_posix()
            encoded = quote(relative, safe="/-._~")
            markdown = note.path.read_text(encoding="utf-8")
            summary = build_note_summary(markdown, note.title)
            lines.extend(
                [
                    f"- [{note.title}]({encoded})",
                    f"  - 位置：`{relative}`",
                    f"  - 简介：{summary}",
                ]
            )
        lines.append("")

    rendered_index = "\n".join(lines).rstrip() + "\n"
    temporary = root / ".目录索引.md.tmp"
    temporary.write_text(rendered_index, encoding="utf-8")
    temporary.replace(root / INDEX_FILENAME)
    return root / INDEX_FILENAME
```

frontmatter 的字符串值用 `json.loads` 解析双引号，日期统一用 `datetime.strptime(value, "%Y-%m-%d %H:%M:%S")`。标题从正文唯一 H1 读取，找不到时使用文件名。

- [ ] **Step 7: 运行知识库模块测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_knowledge_base -v
```

Expected: 月份、简介、图片回退和索引测试全部 PASS。

- [ ] **Step 8: 提交本任务**

```powershell
git add scripts/knowledge_base.py tests/test_knowledge_base.py
git commit -m "生成 AI 知识库 Markdown 目录索引"
```

---

### Task 4: 迁移现有文章、清理重复版本并接入导出主流程

**Files:**
- Modify: `scripts/knowledge_base.py`
- Modify: `scripts/export_search_results.py:238-277`
- Modify: `tests/test_knowledge_base.py`
- Modify: `tests/test_export_search_results.py`

**Interfaces:**
- Produces: `ArchiveResult(moved: tuple[Path, ...], errors: tuple[str, ...])`。
- Produces: `archive_root_notes(root: Path) -> ArchiveResult`。
- Produces: `deduplicate_archived_notes(root: Path) -> list[Path]`。
- Produces: `FinalizationResult(moved, removed, index_path, errors)`。
- Produces: `finalize_knowledge_base(root: Path) -> FinalizationResult`。
- Consumes: Task 3 的 `extract_note_metadata` 与 `write_knowledge_base_index`。

- [ ] **Step 1: 写入根目录迁移和附件改写的失败测试**

```python
class ArchiveTests(unittest.TestCase):
    def test_moves_root_note_to_created_month_and_rewrites_attachments(self):
        from scripts.knowledge_base import archive_root_notes

        with workspace_temp_dir() as root:
            source = write_note(
                root / "现有文章.md",
                title="现有文章",
                created="2026-07-24 11:00:27",
                updated="2026-07-25 11:00:27",
                guid="existing-guid",
                body="正文\n\n![图](_attachments/image.png)",
            )

            result = archive_root_notes(root)
            destination = root / "2026年07月" / "现有文章.md"
            markdown = destination.read_text(encoding="utf-8")

            self.assertEqual(result.moved, (destination,))
            self.assertEqual(result.errors, ())
            self.assertFalse(source.exists())
            self.assertIn("![图](../_attachments/image.png)", markdown)
```

增加一个缺少 `created` 的根目录文件，断言它保持原位、其他有效文章仍完成迁移，并且 `result.errors` 包含该文件名。

- [ ] **Step 2: 运行迁移测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_knowledge_base.ArchiveTests.test_moves_root_note_to_created_month_and_rewrites_attachments -v
```

Expected: ImportError，迁移函数尚不存在。

- [ ] **Step 3: 实现根目录迁移**

```python
@dataclass(frozen=True)
class ArchiveResult:
    moved: tuple[Path, ...]
    errors: tuple[str, ...]


def archive_root_notes(root):
    root = Path(root)
    moved = []
    errors = []
    for source in sorted(root.glob("*.md")):
        if source.name == INDEX_FILENAME:
            continue
        try:
            metadata = extract_note_metadata(source)
        except (OSError, ValueError) as exc:
            errors.append(f"{source}: {exc}")
            continue
        month_dir = root / month_folder_name(metadata.created)
        month_dir.mkdir(parents=True, exist_ok=True)
        destination = month_dir / source.name
        if destination.exists():
            destination_metadata = extract_note_metadata(destination)
            if destination_metadata.guid == metadata.guid:
                source.unlink()
                moved.append(destination)
                continue
            destination = resolve_note_path(
                month_dir,
                metadata.title,
                metadata.guid,
                {},
            )
        content = source.read_text(encoding="utf-8")
        content = content.replace("](_attachments/", "](../_attachments/")
        content = content.replace('src="_attachments/', 'src="../_attachments/')
        destination.write_text(content, encoding="utf-8")
        source.unlink()
        moved.append(destination)
    return ArchiveResult(tuple(moved), tuple(errors))
```

`scripts/knowledge_base.py` 从 `sync_to_obsidian.py` 导入 `resolve_note_path` 和 `safe_filename`。测试同时覆盖相同 GUID 和不同 GUID 的目标冲突，确保不会静默覆盖。

- [ ] **Step 4: 写入归档文件按标题去重和规范命名的失败测试**

```python
def test_keeps_freshest_same_title_and_restores_canonical_filename(self):
    from scripts.knowledge_base import deduplicate_archived_notes

    with workspace_temp_dir() as root:
        older = write_note(
            root / "2026年07月" / "重复文章.md",
            title="重复文章",
            created="2026-07-20 10:00:00",
            updated="2026-07-21 10:00:00",
            guid="older",
            body="旧正文。",
        )
        newer = write_note(
            root / "2026年07月" / "重复文章_newer.md",
            title="重复文章",
            created="2026-07-22 10:00:00",
            updated="2026-07-25 10:00:00",
            guid="newer",
            body="新正文。",
        )

        removed = deduplicate_archived_notes(root)
        canonical = root / "2026年07月" / "重复文章.md"

        self.assertIn(older, removed)
        self.assertTrue(canonical.exists())
        self.assertIn('source_guid: "newer"', canonical.read_text(encoding="utf-8"))
        self.assertFalse(newer.exists())
```

- [ ] **Step 5: 运行归档去重测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_knowledge_base.ArchiveTests.test_keeps_freshest_same_title_and_restores_canonical_filename -v
```

Expected: ImportError，归档去重函数尚不存在。

- [ ] **Step 6: 实现归档去重和最终整理**

```python
def archived_freshness_key(note):
    return (note.updated, note.created, note.guid)


def deduplicate_archived_notes(root):
    groups = {}
    for path in Path(root).glob(
        "[0-9][0-9][0-9][0-9]年[0-9][0-9]月/*.md"
    ):
        note = extract_note_metadata(path)
        groups.setdefault(note.title.strip(), []).append(note)

    removed = []
    for title, notes in groups.items():
        winner = max(notes, key=archived_freshness_key)
        losers = [note for note in notes if note.path != winner.path]
        for loser in losers:
            loser.path.unlink()
            removed.append(loser.path)

        canonical = winner.path.parent / f"{safe_filename(title)}.md"
        if winner.path != canonical:
            winner.path.replace(canonical)
    return removed


@dataclass(frozen=True)
class FinalizationResult:
    moved: tuple[Path, ...]
    removed: tuple[Path, ...]
    index_path: Path
    errors: tuple[str, ...]


def finalize_knowledge_base(root):
    archive = archive_root_notes(root)
    removed = tuple(deduplicate_archived_notes(root))
    index_path = write_knowledge_base_index(root)
    return FinalizationResult(
        moved=archive.moved,
        removed=removed,
        index_path=index_path,
        errors=archive.errors,
    )
```

规范化文件名之前，增加断言或显式检查：若 `canonical` 已存在，它必须属于当前 `notes` 分组，否则抛出 `FileExistsError`，禁止覆盖无关文章。

- [ ] **Step 7: 接入导出主流程并确保失败时不清理**

```python
exported_paths = []
for metadata in selected:
    notebook_name = notebook_map.get(metadata.notebookGuid, "未知笔记本")
    note = note_store.getNote(
        token,
        metadata.guid,
        True,
        True,
        True,
        True,
    )
    exported_paths.append(
        export_note_to_obsidian(
            note,
            notebook_name=notebook_name,
            target_dir=args.target,
        )
    )

finalization = finalize_knowledge_base(args.target)
print(f"- 目录索引: {finalization.index_path}")
if finalization.errors:
    for error in finalization.errors:
        print(f"迁移失败: {error}")
    return 1
```

只有 for 循环全部完成后才调用 `finalize_knowledge_base`。任何 `getNote` 或写文件异常都会在调用整理函数前退出，因此不会删除旧版本。

- [ ] **Step 8: 运行知识库和导出测试并确认 GREEN**

Run:

```powershell
python -m unittest tests.test_knowledge_base tests.test_export_search_results -v
```

Expected: 迁移、同标题清理、规范命名、主流程调用和既有导出测试全部 PASS。

- [ ] **Step 9: 提交本任务**

```powershell
git add scripts/knowledge_base.py scripts/export_search_results.py tests/test_knowledge_base.py tests/test_export_search_results.py
git commit -m "迁移并去重 AI 知识库现有文章"
```

---

### Task 5: 写入 Skill 规则并迁移真实知识库

**Files:**
- Modify: `SKILL.md:36-53,63-71`
- Modify: `README.md:45-90`
- Modify: `tests/test_skill_documentation.py`
- Include: `docs/superpowers/plans/2026-07-26-ai-knowledge-base-archive.md`

**Interfaces:**
- Documents: 月度归档、标题去重、综合简介、索引和附件校验规则。
- Verifies: 真实 `AI相关知识库` 的 5 篇文章、索引和附件完整性。

- [ ] **Step 1: 写入 Skill 规则的失败测试**

```python
def test_documents_monthly_archive_deduplication_and_index_rules(self):
    required_phrases = [
        "YYYY年MM月",
        "created",
        "标题完全一致",
        "updated",
        "目录索引.md",
        "首段有效正文",
        "目录大纲",
        "../_attachments/",
    ]
    for phrase in required_phrases:
        self.assertIn(phrase, self.skill)
```

- [ ] **Step 2: 运行 Skill 文档测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_documents_monthly_archive_deduplication_and_index_rules -v
```

Expected: FAIL，现有 `SKILL.md` 未包含月度归档和综合简介规则。

- [ ] **Step 3: 更新 Skill 和 README**

在 `SKILL.md` 的“搜索并导出”段落写入以下输出契约：

```markdown
- 文章按笔记 `created` 归入 `YYYY年MM月/`。
- 标题完全一致时依次按 `updated`、`created`、GUID 保留一篇，且在 `--limit` 前去重。
- 根目录生成 `目录索引.md`；简介综合首段有效正文和二、三级目录大纲。
- 附件保留在根目录 `_attachments/`，月度文章使用 `../_attachments/`。
```

把完成后核对项改为：根目录无散落文章、索引条目数等于唯一标题数、位置可打开、简介非空、每个本地附件引用存在。

README 增加最终目录树示例和重复运行幂等说明。

- [ ] **Step 4: 运行完整自动化验证**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 所有测试 PASS，编译退出码 0，`git diff --check` 无错误。

- [ ] **Step 5: 对真实知识库执行新版导出与迁移**

Run:

```powershell
python scripts/export_search_results.py `
  --since 2025-07-26 `
  --keywords AI Agent 人工智能 `
  --limit 3 `
  --max-per-keyword 25 `
  --target "D:\OneDrive\文档\@_Obsidian\AI相关知识库"
```

Expected: 三个不同标题被导出；现有五篇文章全部归入 `2026年07月/`；根目录生成 `目录索引.md`。

- [ ] **Step 6: 审计真实目录、索引和附件**

Run:

```powershell
$root = "D:\OneDrive\文档\@_Obsidian\AI相关知识库"
$rootArticles = Get-ChildItem -LiteralPath $root -Filter "*.md" -File |
  Where-Object Name -ne "目录索引.md"
$monthArticles = Get-ChildItem -LiteralPath (Join-Path $root "2026年07月") -Filter "*.md" -File
$index = Get-Content -LiteralPath (Join-Path $root "目录索引.md") -Raw -Encoding UTF8

if ($rootArticles.Count -ne 0) { throw "根目录仍有未归档文章" }
if ($monthArticles.Count -ne 5) { throw "2026年07月文章数不是 5" }
if ([regex]::Matches($index, "(?m)^- \\[").Count -ne 5) { throw "索引条目数不是 5" }
```

再扫描全部 Markdown 本地图片引用，使用 `[uri]::UnescapeDataString` 解析相对路径，并断言对应文件全部存在。

- [ ] **Step 7: 提交文档、测试和计划**

```powershell
git add SKILL.md README.md tests/test_skill_documentation.py docs/superpowers/plans/2026-07-26-ai-knowledge-base-archive.md
git commit -m "记录 AI 知识库月度归档规则"
```

- [ ] **Step 8: 最终状态检查**

Run:

```powershell
git status --short --branch
git log -5 --oneline --decorate
```

Expected: 工作区干净，最近提交依次覆盖标题去重、月度导出、索引、迁移和 Skill 规则。
