# 印象笔记 Skill 全面加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前仓库从“部分脚本可运行”提升为配置一致、凭据安全、只读与破坏性操作边界清晰、Obsidian 同步不丢笔记和图片、文档与实际命令一致的可复用 skill。

**Architecture:** 新增共享运行时模块统一 `.env`、环境变量、UTF-8 控制台和 NoteStore 客户端构造；各命令只保留自身业务逻辑。同步与搜索导出继续复用同一套 ENML/附件转换函数，并以 GUID 和内容哈希作为持久身份，禁止使用标题或原始附件名做唯一键。

**Tech Stack:** Python 3.12、标准库 `argparse`/`unittest`、`evernote3`、Thrift、`html2text`、印象笔记中国版 NoteStore API。

## Global Constraints

- 使用简体中文编写文档、命令帮助和 Git 提交消息。
- 不打印、记录或提交 Developer Token；`.env` 必须保持 Git 忽略。
- 不在真实账号上执行创建、更新、删除、永久删除等破坏性回归。
- 所有行为修复先写失败测试，再写最小实现。
- 保留 `python scripts/<command>.py` 与 `python -m scripts.<command>` 两种运行方式。
- 不自动提交或推送，除非用户另行要求。

---

### Task 1: 共享运行时与配置安全

**Files:**
- Create: `scripts/runtime.py`
- Create: `tests/test_runtime.py`
- Modify: `scripts/list_notebooks.py`
- Modify: `scripts/list_tags.py`
- Modify: `scripts/create_note.py`
- Modify: `scripts/update_note.py`
- Modify: `scripts/delete_note.py`
- Modify: `scripts/list_trash.py`
- Modify: `scripts/empty_trash.py`
- Modify: `scripts/search_notes.py`
- Modify: `scripts/get_note_enml.py`
- Modify: `scripts/sync_to_obsidian.py`
- Modify: `scripts/export_search_results.py`

**Interfaces:**
- Produces: `load_config(env_path: Path | None = None) -> tuple[str | None, str | None]`
- Produces: `create_note_store(note_store_url: str) -> NoteStore.Client`
- Produces: `configure_utf8_output() -> None`

- [ ] **Step 1: 写配置优先级、模块导入无输出和 URL 缺失的失败测试**

```python
def test_environment_overrides_dotenv():
    with patch.dict(os.environ, {
        "EVERNOTE_TOKEN": "env-token",
        "EVERNOTE_NOTESTORE_URL": "https://app.yinxiang.com/shard/s27/notestore",
    }, clear=True):
        assert load_config(env_path=fixture_env) == (
            "env-token",
            "https://app.yinxiang.com/shard/s27/notestore",
        )
```

- [ ] **Step 2: 运行测试并确认旧的重复配置实现失败**

Run: `python -m unittest tests.test_runtime -v`
Expected: FAIL，因为 `scripts.runtime` 尚不存在，且 `list_tags` 导入会打印调试信息。

- [ ] **Step 3: 实现共享运行时并替换所有重复配置代码**

```python
def load_config(env_path=None):
    values = _read_dotenv(env_path or SKILL_ROOT / ".env")
    return (
        os.environ.get("EVERNOTE_TOKEN") or values.get("EVERNOTE_TOKEN"),
        os.environ.get("EVERNOTE_NOTESTORE_URL")
        or values.get("EVERNOTE_NOTESTORE_URL"),
    )
```

- [ ] **Step 4: 删除所有 Token 前缀输出并运行测试**

Run: `python -m unittest tests.test_runtime tests.test_config -v`
Expected: PASS，且导入任一 `scripts.*` 模块不产生标准输出。

### Task 2: 只读命令正确性与通用 CLI

**Files:**
- Modify: `scripts/list_notebooks.py`
- Modify: `scripts/list_tags.py`
- Modify: `scripts/search_notes.py`
- Modify: `scripts/get_note_enml.py`
- Create: `tests/test_read_commands.py`

**Interfaces:**
- Produces: `count_notebook_notes(note_store, token, notebook_guid) -> int`
- Produces: `analyze_enml(content: str) -> dict[str, object]`

- [ ] **Step 1: 写 `findNotesMetadata` 参数顺序和 ENML 命令参数化的失败测试**

```python
def test_count_notebook_uses_offset_then_limit_then_spec():
    count_notebook_notes(fake_store, "token", "notebook-guid")
    assert fake_store.call[2:4] == (0, 1)
```

- [ ] **Step 2: 运行测试确认 verbose 计数和硬编码 GUID 问题**

Run: `python -m unittest tests.test_read_commands -v`
Expected: FAIL，旧实现把 `NotesMetadataResultSpec` 放在 offset 位置。

- [ ] **Step 3: 改用 `argparse`，让 `get_note_enml.py` 接收 `--guid` 和 `--output`**

```powershell
python scripts/get_note_enml.py --guid "NOTE_GUID" --output ".\note.xml"
```

- [ ] **Step 4: 运行只读命令测试与帮助命令**

Run: `python -m unittest tests.test_read_commands -v`
Run: `python scripts/get_note_enml.py --help`
Expected: PASS，帮助文本为 UTF-8，且不含硬编码 GUID。

### Task 3: 废纸篓查询与永久删除安全边界

**Files:**
- Modify: `scripts/list_trash.py`
- Modify: `scripts/empty_trash.py`
- Create: `tests/test_trash.py`

**Interfaces:**
- Produces: `find_deleted_notes(note_store, token, max_count=None) -> list`
- Produces: `CONFIRMATION_TEXT = "DELETE_ALL"`

- [ ] **Step 1: 写 inactive 过滤和强确认文本的失败测试**

```python
def test_deleted_search_sets_inactive_filter():
    find_deleted_notes(fake_store, "token", max_count=100)
    assert fake_store.filters[0].inactive is True
```

- [ ] **Step 2: 运行测试确认旧实现查不到废纸篓且 Enter 即永久删除**

Run: `python -m unittest tests.test_trash -v`
Expected: FAIL，因为旧 `NoteFilter()` 未设置 `inactive=True`。

- [ ] **Step 3: 共享分页查询，并要求 `--confirm DELETE_ALL` 才调用 `expungeNote`**

```powershell
python scripts/empty_trash.py --confirm DELETE_ALL
```

- [ ] **Step 4: 运行测试；只在真实账号执行只读 `list_trash.py`**

Run: `python -m unittest tests.test_trash -v`
Run: `python scripts/list_trash.py --max-count 20`
Expected: 测试通过；真实命令只列出数据，不永久删除。

### Task 4: Obsidian 同步数据完整性

**Files:**
- Modify: `scripts/sync_to_obsidian.py`
- Modify: `scripts/export_search_results.py`
- Modify: `tests/test_export_search_results.py`
- Create: `tests/test_sync_integrity.py`

**Interfaces:**
- Produces: `resolve_note_path(folder, title, guid, existing_guid_map) -> Path`
- Produces: `frontmatter(...) -> str`，所有字符串使用 JSON/YAML 兼容双引号
- Produces: CLI `--vault`、`--state-file`、`--max-sync`、`--api-delay`

- [ ] **Step 1: 写同标题不同 GUID、YAML 特殊字符和内嵌图片不重复展示的失败测试**

```python
def test_same_title_different_guid_uses_distinct_markdown_paths():
    first = resolve_note_path(folder, "同名", "aaaaaaaa-...", {})
    second = resolve_note_path(folder, "同名", "bbbbbbbb-...", {})
    assert first != second
```

- [ ] **Step 2: 运行测试确认标题去重会丢笔记、frontmatter 未转义、图片重复**

Run: `python -m unittest tests.test_sync_integrity -v`
Expected: FAIL。

- [ ] **Step 3: 删除按标题跳过逻辑，按 source GUID 复用文件，冲突时追加 GUID 前八位**

```text
同名.md
同名_bbbbbbbb.md
```

- [ ] **Step 4: 把 vault 和 state 路径改为 CLI/环境配置，不再硬编码旧用户名**

```powershell
python scripts/sync_to_obsidian.py --vault "D:\OneDrive\文档\@_Obsidian" --max-sync 50
```

- [ ] **Step 5: 运行同步完整性测试和现有图片碰撞回归**

Run: `python -m unittest tests.test_sync_integrity tests.test_export_search_results -v`
Expected: PASS。

### Task 5: 文档、依赖和示例配置

**Files:**
- Create: `.env.example`
- Create: `requirements.txt`
- Modify: `README.md`
- Modify: `SKILL.md`

**Interfaces:**
- `.env.example` 提供 `EVERNOTE_TOKEN`、`EVERNOTE_NOTESTORE_URL`、`OBSIDIAN_VAULT_PATH`
- `requirements.txt` 声明 `evernote3`、`thrift`、`html2text`

- [ ] **Step 1: 更新独立仓库命令路径和新增搜索导出命令**

```powershell
python scripts/export_search_results.py --since 2025-07-26 --keywords AI Agent 人工智能 --limit 3 --target "D:\vault\AI相关知识库"
```

- [ ] **Step 2: 删除旧机器硬编码路径和不准确的“自动处理限流”表述**

Run: `rg -n "C:\\Users\\adun|skills/yinxiang-notes|自动处理" README.md SKILL.md`
Expected: 无匹配。

- [ ] **Step 3: 校验文档 UTF-8、示例无真实 Token**

Run: `rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" README.md SKILL.md .env.example`
Expected: 无真实 Token 匹配。

### Task 6: 全量与真实只读验证

**Files:**
- Modify as needed based on verification failures.

- [ ] **Step 1: 运行全部单元测试和编译检查**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Run: `python -m compileall -q scripts tests`
Expected: 全部通过。

- [ ] **Step 2: 运行差异与凭据检查**

Run: `git diff --check`
Run: `rg -n --glob "*.py" "S=s[0-9]+:U=[0-9a-f]+:E=" scripts tests`
Expected: 无错误、无真实 Token。

- [ ] **Step 3: 在国内版真实 API 上执行只读冒烟**

Run: `python scripts/list_notebooks.py`
Run: `python scripts/list_tags.py`
Run: `python scripts/search_notes.py "intitle:Agent" --max-results 3`
Run: `python scripts/list_trash.py --max-count 20`
Expected: 均成功连接 `app.yinxiang.com`，不显示 Token，不修改账号数据。

- [ ] **Step 4: 重新导出三篇 AI 笔记并核对引用**

Run: `python scripts/export_search_results.py --since 2025-07-26 --keywords AI Agent 人工智能 --limit 3 --target "D:\OneDrive\文档\@_Obsidian\AI相关知识库"`
Expected: 3 篇 Markdown、20 个唯一图片引用、20 个有效附件、0 个缺失引用。

- [ ] **Step 5: 完成需求逐项审计并报告未执行的破坏性验证**

明确记录：创建、更新、删除、清空废纸篓只经过单元测试和 CLI 验证，未在真实账号执行。
