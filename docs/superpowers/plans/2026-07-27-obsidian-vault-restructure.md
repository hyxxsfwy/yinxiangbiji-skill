# Obsidian LLM Wiki 统一目录迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `D:\OneDrive\文档\@_Obsidian` 中三个现有知识库安全迁入统一的项目、知识笔记、精选资料和治理目录，并让后续印象笔记精选导出持续遵守新结构。

**Architecture:** 先增强现有精选资料索引和导出 Frontmatter 契约，再新增一个默认只预览、显式确认后才执行的迁移脚本。脚本负责清单、ZIP 快照、目标目录和治理文档生成、内容复制、Frontmatter 更新、链接验证与最终清理；任何验证失败都保留旧目录。最后同步 Skill 文档和测试，并对真实 vault 执行一次受控迁移。

**Tech Stack:** Python 3.12 标准库、`unittest`、Markdown、Obsidian Properties、PowerShell、ZIP、SHA-256、Git。

## Global Constraints

- 使用简体中文编写文档、命令输出和 Git Commit 消息。
- 真实 vault 固定为 `D:\OneDrive\文档\@_Obsidian`。
- 整个 vault 是 LLM Wiki；治理资产路径固定为 `90_系统/知识库治理`。
- 顶层目录固定为 `00_首页.md`、`01_收件箱`、`10_项目`、`20_知识笔记`、`30_精选资料`、`90_系统`、`99_归档`。
- `10_项目`不预建领域子目录，只创建根目录 `目录索引.md`。
- `20_知识笔记`只在根目录创建 `目录索引.md`和`知识地图.md`；领域目录中不创建重复索引。
- `30_精选资料`的每个领域目录都创建 `目录索引.md`。
- 领域固定为 `AI`、`Quant`、`软件工程`、`投资理财`和`个人成长`。
- 历史剪藏继续留在印象笔记；本计划不调用印象笔记创建、更新、删除或清空 API。
- 原始资料正文只读；迁移只允许补充或规范 Frontmatter，不改写正文结论。
- 迁移顺序固定为快照、复制、补充元数据、验证、删除旧文件。
- 默认命令只能预览；真实执行必须同时提供 `--apply`和 `--confirm MIGRATE_OBSIDIAN_VAULT`。
- 未生成迁移前 ZIP、文件清单和链接报告时，不得删除旧目录。
- 任一目标冲突、越界链接、缺失本地附件或哈希异常都必须阻止旧目录清理。
- `.env`只补充 `OBSIDIAN_VAULT_PATH`，不得输出、改写或提交真实 Developer Token。
- 初始正式主题标签只有 `主题/Agent`；每篇笔记最多三个主题标签。
- 本计划只处理现有 8 个 Markdown 文件和对应附件，不从印象笔记追加导出新文章。

---

### Task 1: 让精选资料导出支持领域索引与知识管理 Frontmatter

**Files:**
- Modify: `scripts/sync_to_obsidian.py`
- Modify: `scripts/export_search_results.py`
- Modify: `scripts/knowledge_base.py`
- Modify: `tests/test_sync_integrity.py`
- Modify: `tests/test_export_search_results.py`
- Modify: `tests/test_knowledge_base.py`

**Interfaces:**
- Consumes: 现有 `frontmatter()`、`export_note_to_obsidian()`、`write_knowledge_base_index()`和`finalize_knowledge_base()`。
- Produces: `yaml_value(value)`、`export_note_to_obsidian(note, notebook_name, target_dir, domain="AI")`、`write_knowledge_base_index(root, domain="AI")`和`finalize_knowledge_base(root, domain="AI")`，供迁移脚本和后续领域导出使用。

- [ ] **Step 1: 为类型化 Frontmatter 写失败测试**

在 `tests/test_sync_integrity.py` 的 `FrontmatterTests` 中新增：

```python
def test_frontmatter_supports_scalar_and_list_extra_fields(self):
    from scripts.sync_to_obsidian import frontmatter

    rendered = frontmatter(
        "标题",
        "微信",
        "guid-1",
        datetime(2026, 7, 21, 8, 0, 0),
        datetime(2026, 7, 22, 9, 0, 0),
        {
            "type": "资料",
            "domain": "AI",
            "status": "待提炼",
            "tags": ["主题/Agent"],
            "review_status": "pending",
            "llm_policy": "strict",
        },
        include_title=False,
    )

    self.assertIn('type: "资料"', rendered)
    self.assertIn('domain: "AI"', rendered)
    self.assertIn('tags: ["主题/Agent"]', rendered)
    self.assertNotIn('tags: "[', rendered)
```

同时在测试文件顶部导入：

```python
from datetime import datetime
```

- [ ] **Step 2: 运行类型化 Frontmatter 测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_sync_integrity.FrontmatterTests.test_frontmatter_supports_scalar_and_list_extra_fields -v
```

Expected: FAIL，当前列表被转换为普通字符串。

- [ ] **Step 3: 实现 `yaml_value()`并用于扩展字段**

在 `scripts/sync_to_obsidian.py` 的 `yaml_string()`后新增：

```python
def yaml_value(value):
    """把受控的 Python 标量和列表渲染为 YAML 兼容值。"""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return yaml_string(value)
```

把 `frontmatter()` 的扩展字段输出改为：

```python
for key, value in extra_items:
    fm += f"{key}: {yaml_value(value)}\n"
```

- [ ] **Step 4: 为领域导出和索引文件头写失败测试**

在 `tests/test_export_search_results.py` 的 `ExportNoteTests` 中，把现有导出调用补充
`domain="AI"`，并新增断言：

```python
self.assertIn('type: "资料"', markdown)
self.assertIn('domain: "AI"', markdown)
self.assertIn('status: "待提炼"', markdown)
self.assertIn('tags: []', markdown)
self.assertIn('review_status: "pending"', markdown)
self.assertIn('llm_policy: "strict"', markdown)
```

在 `tests/test_knowledge_base.py` 的 `IndexTests` 中新增：

```python
def test_index_header_documents_domain_function_and_rebuild_rules(self):
    from scripts.knowledge_base import write_knowledge_base_index

    with workspace_temp_dir() as root:
        index_path = write_knowledge_base_index(root, domain="Quant")
        index = index_path.read_text(encoding="utf-8")

    self.assertIn("type: 索引", index)
    self.assertIn("domain: Quant", index)
    self.assertIn("# Quant 精选资料目录", index)
    self.assertIn("> [!info] 功能", index)
    self.assertIn("> [!info] 构建规则", index)
    self.assertIn("可由导出脚本完整重建", index)

def test_index_accepts_uid_for_non_evernote_source(self):
    from scripts.knowledge_base import write_knowledge_base_index

    with workspace_temp_dir() as root:
        month = root / "2026年06月"
        month.mkdir()
        (month / "外部资料.md").write_text(
            "---\ncreated: \"2026-06-12\"\n"
            "updated: \"2026-06-12\"\n"
            "uid: \"source-quant-vibe-2026-06-12\"\n"
            "---\n\n# 外部资料\n\n正文。\n",
            encoding="utf-8",
        )
        index = write_knowledge_base_index(
            root,
            domain="Quant",
        ).read_text(encoding="utf-8")

    self.assertIn("[外部资料]", index)
```

- [ ] **Step 5: 运行领域契约测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_export_search_results.ExportNoteTests tests.test_knowledge_base.IndexTests -v
```

Expected: FAIL，`export_note_to_obsidian()`不接受`domain`，索引仍硬编码为 AI 标题且无规则文件头。

- [ ] **Step 6: 实现领域资料 Frontmatter**

把 `scripts/export_search_results.py` 签名改为：

```python
def export_note_to_obsidian(note, notebook_name, target_dir, domain="AI"):
```

删除 `extra = "type: webclip"`和`extra = "type: inline-images"`的分类写法，保留
`is_web_clip`与`contains_media`用于正文转换，统一使用：

```python
extra = {
    "type": "资料",
    "domain": domain,
    "status": "待提炼",
    "tags": [],
    "review_status": "pending",
    "llm_policy": "strict",
}
```

在命令行参数中新增：

```python
parser.add_argument(
    "--domain",
    choices=("AI", "Quant", "软件工程", "投资理财", "个人成长"),
    default="AI",
    help="精选资料所属领域（默认 AI）",
)
```

导出调用传入：

```python
domain=args.domain
```

- [ ] **Step 7: 实现分领域索引文件头**

把 `scripts/knowledge_base.py` 的签名改为：

```python
def write_knowledge_base_index(root, domain="AI"):
```

索引开头固定渲染为：

```python
lines = [
    "---",
    "type: 索引",
    f"domain: {domain}",
    "status: 常青",
    "tags: []",
    "review_status: human-approved",
    "llm_policy: standard",
    "---",
    "",
    f"# {domain} 精选资料目录",
    "",
    "> [!info] 功能",
    f"> 本文件列出 {domain} 领域的全部精选资料，提供位置和简要说明。",
    "",
    "> [!info] 构建规则",
    "> 扫描本目录的年月归档，按创建月份和创建时间倒序排列。",
    "> 简介由首段有效正文和目录大纲综合生成；本文件可由导出脚本完整重建，不保存人工评论。",
    "",
]
```

把 `finalize_knowledge_base()`签名改为：

```python
def finalize_knowledge_base(root, domain="AI"):
```

并调用：

```python
index_path = write_knowledge_base_index(root, domain=domain)
```

把 `extract_note_metadata()`的身份字段改为：

```python
identity = fields.get("source_guid") or fields.get("uid")
if not identity:
    raise ValueError(f"{markdown_path} 缺少 source_guid 或 uid")
```

并在返回值中使用：

```python
guid=identity
```

`export_search_results.py`最终调用：

```python
finalization = finalize_knowledge_base(args.target, domain=args.domain)
```

- [ ] **Step 8: 运行定向和完整测试**

Run:

```powershell
python -m unittest tests.test_sync_integrity tests.test_export_search_results tests.test_knowledge_base -v
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS；当前基线 70 项测试，加新增测试后总数不少于 72。

- [ ] **Step 9: 提交 Task 1**

```powershell
git add -- scripts/sync_to_obsidian.py scripts/export_search_results.py scripts/knowledge_base.py tests/test_sync_integrity.py tests/test_export_search_results.py tests/test_knowledge_base.py
git diff --cached --check
git commit -m "支持分领域精选资料导出与索引"
```

---

### Task 2: 建立默认预览的 vault 迁移清单与快照工具

**Files:**
- Create: `scripts/restructure_obsidian_vault.py`
- Create: `tests/test_vault_restructure.py`

**Interfaces:**
- Consumes: `Path`、`zipfile`、`hashlib`、`json`和真实 vault 固定旧目录名。
- Produces: `MigrationItem`、`MigrationPlan`、`build_migration_plan(vault)`、`sha256_file(path)`、`create_backup(plan, backup_path)`和默认 dry-run CLI。

- [ ] **Step 1: 写迁移映射和安全门禁失败测试**

创建 `tests/test_vault_restructure.py`，使用现有 `tests.support.workspace_temp_dir`：

```python
import json
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

from tests.support import workspace_temp_dir


def seed_old_vault(vault):
    (vault / ".obsidian").mkdir(parents=True)
    ai = vault / "AI相关知识库"
    (ai / "2026年07月").mkdir(parents=True)
    (ai / "_attachments").mkdir()
    (ai / "目录索引.md").write_text("# 旧索引\n", encoding="utf-8")
    (ai / "2026年07月" / "一张图看懂 AI Agent 全流程.md").write_text(
        "---\ncreated: \"2026-07-21 08:00:00\"\n"
        "updated: \"2026-07-22 08:00:00\"\n"
        "source: \"Evernote\"\nsource_guid: \"agent-guid\"\n"
        "notebook: \"微信\"\ntype: \"webclip\"\n---\n\n"
        "# 一张图看懂 AI Agent 全流程\n\n"
        "![图](../_attachments/agent.png)\n",
        encoding="utf-8",
    )
    (ai / "_attachments" / "agent.png").write_bytes(b"image")

    quant = vault / "Quant相关知识库"
    quant.mkdir()
    (quant / "GPT-6也救不了平庸策略：Vibe Quant 的反思.md").write_text(
        "# [GPT-6也救不了平庸策略：Vibe Quant 的反思]"
        "(https://mp.weixin.qq.com/example)\n\n正文。\n",
        encoding="utf-8",
    )

    personal = vault / "HYXX个人知识库"
    personal.mkdir()
    (personal / ".obsidian").mkdir()
    (personal / "Codex CLI 使用技巧记录.md").write_text(
        "1. 进入翻页模式：CTRL + T\n",
        encoding="utf-8",
    )
```

新增测试：

```python
class MigrationPlanTests(unittest.TestCase):
    def test_builds_exact_current_to_target_mapping(self):
        from scripts.restructure_obsidian_vault import build_migration_plan

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)

        mappings = {
            item.source.relative_to(vault).as_posix():
            item.destination.relative_to(vault).as_posix()
            for item in plan.items
        }
        self.assertEqual(
            mappings["AI相关知识库"],
            "30_精选资料/AI",
        )
        self.assertEqual(
            mappings["Quant相关知识库/GPT-6也救不了平庸策略：Vibe Quant 的反思.md"],
            "30_精选资料/Quant/2026年06月/GPT-6也救不了平庸策略：Vibe Quant 的反思.md",
        )
        self.assertEqual(
            mappings["HYXX个人知识库/Codex CLI 使用技巧记录.md"],
            "20_知识笔记/软件工程/Codex CLI 使用技巧记录.md",
        )
        self.assertNotIn(
            "HYXX个人知识库/.obsidian",
            mappings,
        )

    def test_requires_real_vault_marker(self):
        from scripts.restructure_obsidian_vault import build_migration_plan

        with workspace_temp_dir() as vault:
            with self.assertRaisesRegex(ValueError, r"\.obsidian"):
                build_migration_plan(vault)
```

- [ ] **Step 2: 运行迁移计划测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_vault_restructure.MigrationPlanTests -v
```

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 实现迁移数据结构与精确映射**

在 `scripts/restructure_obsidian_vault.py` 中定义：

```python
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


CONFIRMATION = "MIGRATE_OBSIDIAN_VAULT"
DOMAINS = ("AI", "Quant", "软件工程", "投资理财", "个人成长")
OLD_DIRECTORIES = ("AI相关知识库", "Quant相关知识库", "HYXX个人知识库")
QUANT_FILENAME = "GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
CODEX_FILENAME = "Codex CLI 使用技巧记录.md"


@dataclass(frozen=True)
class MigrationItem:
    source: Path
    destination: Path
    operation: str


@dataclass(frozen=True)
class MigrationPlan:
    vault: Path
    items: tuple[MigrationItem, ...]
    old_directories: tuple[Path, ...]


def assert_vault(vault: Path) -> Path:
    resolved = Path(vault).resolve()
    if not (resolved / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault，缺少 .obsidian: {resolved}")
    return resolved


def build_migration_plan(vault: Path) -> MigrationPlan:
    vault = assert_vault(vault)
    items = (
        MigrationItem(
            vault / "AI相关知识库",
            vault / "30_精选资料" / "AI",
            "copy_tree",
        ),
        MigrationItem(
            vault / "Quant相关知识库" / QUANT_FILENAME,
            vault / "30_精选资料" / "Quant" / "2026年06月" / QUANT_FILENAME,
            "copy_file",
        ),
        MigrationItem(
            vault / "HYXX个人知识库" / CODEX_FILENAME,
            vault / "20_知识笔记" / "软件工程" / CODEX_FILENAME,
            "copy_file",
        ),
    )
    missing = [str(item.source) for item in items if not item.source.exists()]
    if missing:
        raise FileNotFoundError("缺少迁移源:\n" + "\n".join(missing))
    return MigrationPlan(
        vault=vault,
        items=items,
        old_directories=tuple(vault / name for name in OLD_DIRECTORIES),
    )
```

- [ ] **Step 4: 为哈希、快照和清单写失败测试**

继续新增：

```python
class SnapshotTests(unittest.TestCase):
    def test_backup_contains_all_old_directories_and_manifest_has_hashes(self):
        from scripts.restructure_obsidian_vault import (
            build_migration_plan,
            create_backup,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            records_dir = vault / "90_系统" / "迁移记录"
            backup = records_dir / "2026-07-27-迁移前备份.zip"
            manifest = records_dir / "2026-07-27-文件清单.json"
            create_backup(plan, backup)
            write_manifest(plan, manifest)

            with zipfile.ZipFile(backup) as archive:
                names = set(archive.namelist())
            payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertIn(
            "AI相关知识库/2026年07月/一张图看懂 AI Agent 全流程.md",
            names,
        )
        self.assertIn(
            "HYXX个人知识库/.obsidian/",
            names,
        )
        self.assertTrue(all(record["sha256"] for record in payload["files"]))
```

- [ ] **Step 5: 实现哈希、文件枚举、ZIP 和 JSON 清单**

实现：

```python
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_old_files(plan: MigrationPlan):
    for old_directory in plan.old_directories:
        for path in sorted(old_directory.rglob("*")):
            if path.is_file():
                yield path


def destination_for_source(
    plan: MigrationPlan,
    source: Path,
) -> Path | None:
    relative = source.relative_to(plan.vault)
    parts = relative.parts
    if parts[0] == "AI相关知识库":
        return (
            plan.vault
            / "30_精选资料"
            / "AI"
            / Path(*parts[1:])
        )
    if relative.as_posix() == (
        "Quant相关知识库/"
        "GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
    ):
        return (
            plan.vault
            / "30_精选资料"
            / "Quant"
            / "2026年06月"
            / QUANT_FILENAME
        )
    if relative.as_posix() == (
        "HYXX个人知识库/Codex CLI 使用技巧记录.md"
    ):
        return (
            plan.vault
            / "20_知识笔记"
            / "软件工程"
            / CODEX_FILENAME
        )
    return None


def create_backup(plan: MigrationPlan, backup_path: Path) -> Path:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        raise FileExistsError(f"备份已存在，拒绝覆盖: {backup_path}")
    with zipfile.ZipFile(
        backup_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for old_directory in plan.old_directories:
            for path in sorted(old_directory.rglob("*")):
                relative = path.relative_to(plan.vault).as_posix()
                if path.is_dir():
                    archive.writestr(relative.rstrip("/") + "/", b"")
                else:
                    archive.write(path, relative)
    return backup_path


def write_manifest(plan: MigrationPlan, manifest_path: Path) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "vault": str(plan.vault),
        "created_at": datetime.now().astimezone().isoformat(),
        "files": [
            {
                "source": path.relative_to(plan.vault).as_posix(),
                "destination": (
                    destination_for_source(plan, path)
                    .relative_to(plan.vault)
                    .as_posix()
                    if destination_for_source(plan, path) is not None
                    else None
                ),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "preserve_hash": path.suffix.lower() != ".md",
            }
            for path in iter_old_files(plan)
        ],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
```

- [ ] **Step 6: 为 dry-run 写失败测试**

新增命令行测试：

```python
class CommandLineTests(unittest.TestCase):
    def test_default_command_only_prints_plan(self):
        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/restructure_obsidian_vault.py",
                    "--vault",
                    str(vault),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("预览模式", result.stdout)
            self.assertFalse((vault / "20_知识笔记").exists())
```

- [ ] **Step 7: 实现只支持预览的 Task 2 CLI**

新增：

```python
def print_plan(plan: MigrationPlan):
    print("预览模式：不会修改 vault")
    for item in plan.items:
        print(
            f"- {item.source.relative_to(plan.vault)}"
            f" -> {item.destination.relative_to(plan.vault)}"
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="安全重组 HYXX Obsidian LLM Wiki"
    )
    parser.add_argument("--vault", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    plan = build_migration_plan(args.vault)
    print_plan(plan)
    return 0
```

文件结尾使用：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: 运行 Task 2 测试**

Run:

```powershell
python -m unittest tests.test_vault_restructure.MigrationPlanTests tests.test_vault_restructure.SnapshotTests tests.test_vault_restructure.CommandLineTests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS。

- [ ] **Step 9: 提交 Task 2**

```powershell
git add -- scripts/restructure_obsidian_vault.py tests/test_vault_restructure.py
git diff --cached --check
git commit -m "增加 Obsidian vault 迁移预览与快照工具"
```

---

### Task 3: 生成统一目录、治理资产并复制规范化内容

**Files:**
- Modify: `scripts/restructure_obsidian_vault.py`
- Modify: `tests/test_vault_restructure.py`
- Read: `templates/obsidian-source-note.md`
- Read: `templates/obsidian-knowledge-note.md`
- Read: `templates/obsidian-knowledge-map.md`

**Interfaces:**
- Consumes: Task 2 的 `MigrationPlan`、清单和快照函数，以及 Task 1 的领域索引函数。
- Produces: `ensure_target_structure()`、`merge_frontmatter()`、`copy_mapped_content()`、`write_vault_documents()`和可重复执行的 apply 阶段；本任务不删除旧目录。

- [ ] **Step 1: 写目标目录和索引文件失败测试**

新增：

```python
class ScaffoldTests(unittest.TestCase):
    def test_creates_exact_lifecycle_tree_and_index_contracts(self):
        from scripts.restructure_obsidian_vault import (
            build_migration_plan,
            ensure_target_structure,
            write_vault_documents,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            ensure_target_structure(plan)
            write_vault_documents(plan)

            expected = (
                "00_首页.md",
                "10_项目/目录索引.md",
                "20_知识笔记/目录索引.md",
                "20_知识笔记/知识地图.md",
                "20_知识笔记/AI",
                "20_知识笔记/Quant",
                "20_知识笔记/软件工程",
                "20_知识笔记/投资理财",
                "20_知识笔记/个人成长",
                "30_精选资料/AI/目录索引.md",
                "30_精选资料/Quant/目录索引.md",
                "30_精选资料/软件工程/目录索引.md",
                "30_精选资料/投资理财/目录索引.md",
                "30_精选资料/个人成长/目录索引.md",
                "90_系统/知识库治理/管理规则.md",
                "90_系统/知识库治理/主题词表.md",
                "90_系统/知识库治理/别名词典.md",
            )
            for relative in expected:
                self.assertTrue(vault.joinpath(relative).exists(), relative)

            self.assertFalse((vault / "10_项目" / "AI").exists())
            self.assertFalse(
                (vault / "20_知识笔记" / "AI" / "目录索引.md").exists()
            )

            catalog = (
                vault / "20_知识笔记" / "目录索引.md"
            ).read_text(encoding="utf-8")
            knowledge_map = (
                vault / "20_知识笔记" / "知识地图.md"
            ).read_text(encoding="utf-8")
            self.assertIn("> [!info] 功能", catalog)
            self.assertIn("> [!info] 构建规则", catalog)
            self.assertIn("可由脚本或 AI 完整重建", catalog)
            self.assertIn("<!-- llmwiki:auto:start -->", knowledge_map)
            self.assertIn("<!-- llmwiki:auto:end -->", knowledge_map)
```

- [ ] **Step 2: 运行目录结构测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_vault_restructure.ScaffoldTests -v
```

Expected: FAIL，结构和文档函数尚不存在。

- [ ] **Step 3: 实现精确目录创建**

定义：

```python
def ensure_target_structure(plan: MigrationPlan):
    vault = plan.vault
    fixed_directories = (
        "01_收件箱",
        "10_项目",
        "20_知识笔记",
        "30_精选资料",
        "90_系统/模板",
        "90_系统/Bases",
        "90_系统/知识库治理/审核队列",
        "90_系统/知识库治理/审核日志",
        "90_系统/知识库治理/变更快照",
        "90_系统/迁移记录",
        "99_归档",
    )
    for relative in fixed_directories:
        (vault / relative).mkdir(parents=True, exist_ok=True)
    for domain in DOMAINS:
        (vault / "20_知识笔记" / domain).mkdir(parents=True, exist_ok=True)
        (vault / "30_精选资料" / domain).mkdir(parents=True, exist_ok=True)
```

禁止在 `10_项目`下预建领域目录，禁止在知识笔记领域目录创建索引。

- [ ] **Step 4: 实现首页、项目索引、知识索引、知识地图和治理文档**

定义纯渲染函数：

```python
def render_home() -> str:
    return """---
type: 索引
domain:
status: 常青
tags: []
review_status: human-approved
llm_policy: strict
---

# HYXX LLM Wiki

> 本仓库是由人工与 AI 共同维护的个人知识系统。文件夹表示内容所处阶段，
> Properties 表示内容性质，标签表达主题，内部链接表达知识关系。

## 工作台

- [[10_项目/目录索引|当前项目]]
- 收件箱目录：`01_收件箱/`

## 知识

- [[20_知识笔记/目录索引|全部知识笔记]]
- [[20_知识笔记/知识地图|知识地图]]

## 精选资料

- [[30_精选资料/AI/目录索引|AI]]
- [[30_精选资料/Quant/目录索引|Quant]]
- [[30_精选资料/软件工程/目录索引|软件工程]]
- [[30_精选资料/投资理财/目录索引|投资理财]]
- [[30_精选资料/个人成长/目录索引|个人成长]]

## 系统

- [[90_系统/知识库治理/管理规则|管理规则]]
- [[90_系统/知识库治理/主题词表|主题词表]]
"""


def render_project_index() -> str:
    return """---
type: 索引
domain:
status: 常青
tags: []
review_status: human-approved
llm_policy: strict
---

# 项目目录索引

> [!info] 功能
> 本目录只存放有明确目标、交付物和结束条件的工作项目。

> [!info] 构建规则
> 暂不预建领域目录；出现实际项目后按项目名称建文件夹。
> 项目完成后，通用认识提炼到 `20_知识笔记`，原始资料进入
> `30_精选资料`，其余过程材料进入 `99_归档`。
> AI 可以补充状态摘要，但不得自动移动、归档或删除项目。

## 当前项目

- 暂无
"""


def render_knowledge_catalog(vault: Path) -> str:
    lines = [
        "---",
        "type: 索引",
        "domain:",
        "status: 常青",
        "tags: []",
        "review_status: human-approved",
        "llm_policy: standard",
        "---",
        "",
        "# 知识笔记目录索引",
        "",
        "> [!info] 功能",
        "> 本文件提供全部知识笔记的确定性目录，用于按领域查找已有知识。",
        "",
        "> [!info] 构建规则",
        "> 扫描 `20_知识笔记` 下 `type: 知识` 的文件，按 `domain` 分组、",
        "> 按 `updated` 倒序排列。每项包含链接、摘要、状态和更新时间。",
        "> 本文件可由脚本或 AI 完整重建，不保存人工评论。",
        "",
    ]
    root = vault / "20_知识笔记"
    for domain in DOMAINS:
        lines.extend([f"## {domain}", ""])
        notes = []
        for path in sorted((root / domain).glob("*.md")):
            fields, body = split_frontmatter(
                path.read_text(encoding="utf-8")
            )
            if fields.get("type") != "知识":
                continue
            notes.append(
                (
                    str(fields.get("updated", fields.get("created", ""))),
                    path,
                    str(fields.get("summary", "")).strip()
                    or first_effective_line(body),
                    str(fields.get("status", "")),
                )
            )
        if not notes:
            lines.extend(["- 暂无", ""])
            continue
        for updated, path, summary, status in sorted(
            notes,
            key=lambda row: (row[0], row[1].as_posix()),
            reverse=True,
        ):
            relative = path.relative_to(root).with_suffix("").as_posix()
            lines.append(
                f"- [[{relative}|{path.stem}]]"
                f"｜{summary}｜{status}｜{updated or '未记录'}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_knowledge_map() -> str:
    domain_sections = "\n\n".join(
        f"### {domain}\n" for domain in DOMAINS
    )
    return f"""---
type: 索引
domain:
status: 常青
tags: []
review_status: human-approved
llm_policy: standard
---

# 知识地图

> [!info] 功能
> 本文件展示核心知识、重要关系和跨领域连接，不作为完整文件清单。

> [!info] 构建规则
> 人工维护核心概念和关键入口；AI 只能在自动维护区域补充有明确依据、
> 已完成链接消歧的推荐关系。每篇知识笔记只保留 3 至 7 个高价值链接，
> 仅关键词相同不足以建立关系。

## 人工精选

{domain_sections}

<!-- llmwiki:auto:start -->

## AI 推荐关系

- 暂无

<!-- llmwiki:auto:end -->
"""


def render_management_rules() -> str:
    return """# 知识库管理规则

整个 `@_Obsidian` vault 是 LLM Wiki，本目录只保存治理资产。

1. 历史剪藏继续留在印象笔记，Obsidian 只迁移持续有用的内容。
2. 原始资料正文只读；AI 只能生成摘要、属性和链接建议。
3. 自动审批必须具有可定位证据、受控词表、链接消歧、独立审核、
   确定性校验、日志和可回滚快照。
4. 创建永久标签、修改人工结论、合并、移动、重命名、删除、
   提升常青状态和修改知识地图人工区必须人工审批。
5. 每篇笔记最多三个主题标签；每篇知识笔记保留三至七个高价值链接。
"""


def render_topic_vocabulary() -> str:
    candidates = (
        "OpenAI",
        "AI编程",
        "AI安全",
        "量化研究",
        "Codex",
        "PKM",
        "信息安全",
        "区块链",
    )
    lines = [
        "# 主题词表",
        "",
        "## 正式主题",
        "",
        "- 主题/Agent",
        "",
        "## 候选主题",
        "",
    ]
    lines.extend(f"- 主题/{name}" for name in candidates)
    lines.extend(
        [
            "",
            "候选主题预计至少被三篇笔记复用，且通过人工审批后才能转为正式主题。",
            "",
        ]
    )
    return "\n".join(lines)


def render_alias_dictionary() -> str:
    return """# 别名词典

| 旧名称或别名 | 规范名称 | 用途 |
| --- | --- | --- |
| ML&AI | AI | domain |
| CS_IT | 软件工程 | domain |
| 智能体Agent | Agent | 主题或内部链接 |
"""


def first_effective_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith(("#", "![", ">", "---"))
        ):
            return stripped[:120]
    return "暂无摘要"
```

以上文本必须满足设计文档第 7、8 节。还要实现：

- 首页标题为 `# HYXX LLM Wiki`；
- 项目索引说明不预建领域目录；
- 知识目录说明按 `domain`分组、按 `updated`倒序、可完整重建且不保存人工评论；
- 知识地图包含五个领域人工区和唯一一组 `llmwiki:auto`标记；
- `主题词表.md`正式主题只有 `主题/Agent`，八个候选主题放入“候选主题”；
- `管理规则.md`声明整个 vault 是 LLM Wiki，人工审批高风险操作；
- `first_effective_line(body)`跳过空行、标题、图片和引用标记，取首个有效正文行；
- `别名词典.md`固定记录 `ML&AI -> AI`、`CS_IT -> 软件工程`和
  `智能体Agent -> Agent`。

`write_vault_documents(plan)`只使用以上渲染函数写入固定路径。若文件已存在且内容
不同，先比较；除本计划明确管理的索引和治理文件外，不覆盖用户文件。

实现固定映射：

```python
def write_vault_documents(plan: MigrationPlan):
    vault = plan.vault
    documents = {
        vault / "00_首页.md": render_home(),
        vault / "10_项目" / "目录索引.md": render_project_index(),
        vault / "20_知识笔记" / "知识地图.md": render_knowledge_map(),
        (
            vault / "90_系统" / "知识库治理" / "管理规则.md"
        ): render_management_rules(),
        (
            vault / "90_系统" / "知识库治理" / "主题词表.md"
        ): render_topic_vocabulary(),
        (
            vault / "90_系统" / "知识库治理" / "别名词典.md"
        ): render_alias_dictionary(),
    }
    for destination, content in documents.items():
        write_expected_text(destination, content)
    (
        vault / "20_知识笔记" / "目录索引.md"
    ).write_text(
        render_knowledge_catalog(vault),
        encoding="utf-8",
    )
    for domain in DOMAINS:
        write_knowledge_base_index(
            vault / "30_精选资料" / domain,
            domain=domain,
        )
```

`目录索引.md`和`知识地图.md`是本计划声明的受管文件；其他已有用户文件不得被
`write_vault_documents()`覆盖。

- [ ] **Step 5: 为 Frontmatter 合并和内容复制写失败测试**

新增：

```python
class CopyAndMetadataTests(unittest.TestCase):
    def test_copies_content_with_required_properties_and_preserves_body(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            original_body = (
                vault
                / "AI相关知识库"
                / "2026年07月"
                / "一张图看懂 AI Agent 全流程.md"
            ).read_text(encoding="utf-8").split("---", 2)[2]
            apply_copy_phase(plan)

            agent = (
                vault
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / "一张图看懂 AI Agent 全流程.md"
            ).read_text(encoding="utf-8")
            codex = (
                vault
                / "20_知识笔记"
                / "软件工程"
                / "Codex CLI 使用技巧记录.md"
            ).read_text(encoding="utf-8")

        self.assertIn('type: "资料"', agent)
        self.assertIn('domain: "AI"', agent)
        self.assertIn('status: "待提炼"', agent)
        self.assertIn("主题/Agent", agent)
        self.assertIn(original_body.strip(), agent)
        self.assertIn('type: "知识"', codex)
        self.assertIn('domain: "软件工程"', codex)
        self.assertIn('status: "常青"', codex)
        self.assertIn('review_status: "human-approved"', codex)

    def test_does_not_copy_nested_personal_obsidian_config(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            apply_copy_phase(build_migration_plan(vault))
            self.assertFalse(
                (vault / "20_知识笔记" / "软件工程" / ".obsidian").exists()
            )
```

- [ ] **Step 6: 实现受控 Frontmatter 合并**

定义：

```python
FRONTMATTER_RE = re.compile(
    r"\A---\r?\n(.*?)\r?\n---(?:\r?\n)?",
    re.DOTALL,
)


def parse_frontmatter_value(value: str):
    stripped = value.strip()
    if not stripped:
        return ""
    if (
        (stripped.startswith('"') and stripped.endswith('"'))
        or (stripped.startswith("[") and stripped.endswith("]"))
    ):
        return json.loads(stripped)
    return stripped


def split_frontmatter(markdown: str) -> tuple[dict[str, object], str]:
    """读取简单 YAML Frontmatter；无 Frontmatter 时返回空字段和完整正文。"""
    match = FRONTMATTER_RE.match(markdown)
    if match is None:
        return {}, markdown
    fields = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_-]*",
            key,
        ):
            raise ValueError(f"不支持的 Frontmatter 行: {line!r}")
        fields[key] = parse_frontmatter_value(value)
    return fields, markdown[match.end():]


def render_frontmatter(fields: dict[str, object]) -> str:
    """按固定字段顺序渲染本计划允许的标量和列表。"""
    known = [key for key in FRONTMATTER_ORDER if key in fields]
    extra = sorted(key for key in fields if key not in FRONTMATTER_ORDER)
    lines = ["---"]
    for key in known + extra:
        lines.append(f"{key}: {yaml_value(fields[key])}")
    lines.extend(["---", ""])
    return "\n".join(lines) + "\n"


def merge_frontmatter(
    markdown: str,
    required: dict[str, object],
) -> str:
    fields, body = split_frontmatter(markdown)
    fields.update(required)
    return render_frontmatter(fields) + body.lstrip("\r\n")
```

字段顺序固定为：

```python
FRONTMATTER_ORDER = (
    "type",
    "domain",
    "status",
    "created",
    "updated",
    "source",
    "source_guid",
    "source_url",
    "notebook",
    "tags",
    "uid",
    "summary",
    "aliases",
    "review_status",
    "reviewed_by",
    "reviewed_at",
    "llm_policy",
)
```

不能修改 Frontmatter 结束标记之后的正文。

- [ ] **Step 7: 实现无覆盖复制和三类元数据规则**

定义：

```python
def copy_file_without_overwrite(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) == sha256_file(destination):
            return
        raise FileExistsError(f"目标已存在且内容不同: {destination}")
    shutil.copy2(source, destination)
```

AI 目录先逐文件复制，随后只处理月份目录中的 Markdown。Agent 标签判定使用精确
标题集合：

```python
AGENT_TITLES = {
    "Github 26.6k star，字节把 AI Agent 的记忆重做了一遍，不用向量数据库也能管上下文！",
    "一张图看懂 AI Agent 全流程",
    "删掉80%的Skill，Agent反而更听话了",
}
```

AI 必填字段：

```python
{
    "type": "资料",
    "domain": "AI",
    "status": "待提炼",
    "tags": ["主题/Agent"] if title in AGENT_TITLES else [],
    "review_status": "pending",
    "llm_policy": "strict",
}
```

Quant 必填字段使用设计文档中的精确 `source_url`、`created: "2026-06-12"`，
`updated: "2026-06-12"`、`uid: "source-quant-vibe-2026-06-12"`、
`type: 资料`、`domain: Quant`、`status: 待提炼`、空标签、`pending`和`strict`。

Codex 必填字段为 `type: 知识`、`domain: 软件工程`、`status: 常青`、
`created: "2026-07-04"`、空标签、`human-approved`和`standard`。

实现幂等文本写入和复制阶段：

```python
def write_expected_text(destination: Path, expected: str):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual = destination.read_text(encoding="utf-8")
        if actual == expected:
            return
        raise FileExistsError(f"目标文本已存在且内容不同: {destination}")
    destination.write_text(expected, encoding="utf-8")


def title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            if title.startswith("[") and "](" in title:
                title = title[1:title.index("](")]
            return title
    return fallback


def apply_copy_phase(plan: MigrationPlan):
    ensure_target_structure(plan)

    old_ai = plan.vault / "AI相关知识库"
    new_ai = plan.vault / "30_精选资料" / "AI"
    for source in sorted(old_ai.rglob("*")):
        if not source.is_file() or source.name == "目录索引.md":
            continue
        destination = new_ai / source.relative_to(old_ai)
        if source.suffix.lower() != ".md":
            copy_file_without_overwrite(source, destination)
            continue
        original = source.read_text(encoding="utf-8")
        title = title_from_markdown(original, source.stem)
        expected = merge_frontmatter(
            original,
            {
                "type": "资料",
                "domain": "AI",
                "status": "待提炼",
                "tags": (
                    ["主题/Agent"]
                    if title in AGENT_TITLES
                    else []
                ),
                "review_status": "pending",
                "llm_policy": "strict",
            },
        )
        write_expected_text(destination, expected)

    quant_source = plan.vault / "Quant相关知识库" / QUANT_FILENAME
    quant_destination = (
        plan.vault
        / "30_精选资料"
        / "Quant"
        / "2026年06月"
        / QUANT_FILENAME
    )
    quant_expected = merge_frontmatter(
        quant_source.read_text(encoding="utf-8"),
        {
            "type": "资料",
            "domain": "Quant",
            "status": "待提炼",
            "created": "2026-06-12",
            "updated": "2026-06-12",
            "source": "微信",
            "source_url": (
                "https://mp.weixin.qq.com/s?__biz=Mzg2MzAwNzM0NQ=="
                "&mid=2247494007&idx=1"
                "&sn=cc89b84a7928baddf755d58e867cc99a"
                "&chksm=cfa518120a5d72b4845ecac9547a37b2"
                "ab716be7ac6831e782cf6bb4c9f4a75ea3ea15c44f79#rd"
            ),
            "tags": [],
            "uid": "source-quant-vibe-2026-06-12",
            "review_status": "pending",
            "llm_policy": "strict",
        },
    )
    write_expected_text(quant_destination, quant_expected)

    codex_source = (
        plan.vault / "HYXX个人知识库" / CODEX_FILENAME
    )
    codex_destination = (
        plan.vault / "20_知识笔记" / "软件工程" / CODEX_FILENAME
    )
    codex_expected = merge_frontmatter(
        codex_source.read_text(encoding="utf-8"),
        {
            "type": "知识",
            "domain": "软件工程",
            "status": "常青",
            "created": "2026-07-04",
            "tags": [],
            "review_status": "human-approved",
            "llm_policy": "standard",
        },
    )
    write_expected_text(codex_destination, codex_expected)

    install_templates(plan)
    write_vault_documents(plan)
```

`write_vault_documents(plan)`在内容复制后调用
`render_knowledge_catalog(plan.vault)`，并对五个资料领域分别调用
`write_knowledge_base_index(root, domain=domain)`。复制阶段不得删除旧目录。

- [ ] **Step 8: 安装三个现有模板**

从仓库根目录的 `templates/`读取三个模板，分别写入：

```text
90_系统/模板/精选资料模板.md
90_系统/模板/知识笔记模板.md
90_系统/模板/知识地图模板.md
```

模板目标存在且内容不同时必须报冲突，不能静默覆盖用户修改。

实现：

```python
def install_templates(plan: MigrationPlan):
    repo_root = Path(__file__).resolve().parent.parent
    mappings = {
        "obsidian-source-note.md": "精选资料模板.md",
        "obsidian-knowledge-note.md": "知识笔记模板.md",
        "obsidian-knowledge-map.md": "知识地图模板.md",
    }
    for source_name, destination_name in mappings.items():
        source = repo_root / "templates" / source_name
        destination = (
            plan.vault / "90_系统" / "模板" / destination_name
        )
        write_expected_text(
            destination,
            source.read_text(encoding="utf-8"),
        )
```

- [ ] **Step 9: 增加 apply 确认门禁并串联安全复制阶段**

在 `CommandLineTests` 新增：

```python
def test_apply_requires_exact_confirmation(self):
    with workspace_temp_dir() as vault:
        seed_old_vault(vault)
        result = subprocess.run(
            [
                sys.executable,
                "scripts/restructure_obsidian_vault.py",
                "--vault",
                str(vault),
                "--apply",
                "--confirm",
                "WRONG",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MIGRATE_OBSIDIAN_VAULT", result.stderr)
        self.assertFalse((vault / "20_知识笔记").exists())

def test_confirmed_apply_creates_snapshot_and_keeps_old_directories(self):
    with workspace_temp_dir() as vault:
        seed_old_vault(vault)
        result = subprocess.run(
            [
                sys.executable,
                "scripts/restructure_obsidian_vault.py",
                "--vault",
                str(vault),
                "--apply",
                "--confirm",
                "MIGRATE_OBSIDIAN_VAULT",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-迁移前备份.zip"
            ).is_file()
        )
        self.assertTrue((vault / "AI相关知识库").exists())
        self.assertTrue((vault / "30_精选资料" / "AI").exists())
```

把 Task 2 的参数解析扩展为：

```python
parser.add_argument("--apply", action="store_true")
parser.add_argument("--confirm")
```

Task 3 的 `main()`在确认词正确后执行：

```python
records = plan.vault / "90_系统" / "迁移记录"
create_backup(plan, records / "2026-07-27-迁移前备份.zip")
write_manifest(plan, records / "2026-07-27-文件清单.json")
apply_copy_phase(plan)
print("复制阶段完成；旧目录保持不变，等待完整验证")
return 0
```

确认词不等于 `MIGRATE_OBSIDIAN_VAULT`时必须在任何写入前退出。

- [ ] **Step 10: 运行 Task 3 测试**

Run:

```powershell
python -m unittest tests.test_vault_restructure.ScaffoldTests tests.test_vault_restructure.CopyAndMetadataTests -v
python -m unittest tests.test_vault_restructure -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS；旧目录仍然存在。

- [ ] **Step 11: 提交 Task 3**

```powershell
git add -- scripts/restructure_obsidian_vault.py tests/test_vault_restructure.py
git diff --cached --check
git commit -m "生成 Obsidian LLM Wiki 目录与治理资产"
```

---

### Task 4: 增加链接验证、迁移报告和验证后清理

**Files:**
- Modify: `scripts/restructure_obsidian_vault.py`
- Modify: `tests/test_vault_restructure.py`

**Interfaces:**
- Consumes: Task 2 的清单与备份、Task 3 的复制结果。
- Produces: `LinkIssue`、`ValidationReport`、`scan_local_links()`、`validate_migration()`、`write_link_report()`、`cleanup_old_directories()`和完整 apply/verify CLI。

- [ ] **Step 1: 写链接解析与 vault 边界失败测试**

新增：

```python
class LinkValidationTests(unittest.TestCase):
    def test_reports_missing_local_target_and_ignores_http(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            note = vault / "note.md"
            note.write_text(
                "![缺图](assets/missing.png)\n"
                "[外部](https://example.com)\n",
                encoding="utf-8",
            )
            issues = scan_local_links(vault)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].source.name, "note.md")
        self.assertEqual(issues[0].target, "assets/missing.png")
        self.assertEqual(issues[0].reason, "目标不存在")

    def test_rejects_link_resolving_outside_vault(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "note.md").write_text(
                "[越界](../../secret.txt)\n",
                encoding="utf-8",
            )
            issues = scan_local_links(vault)

        self.assertEqual(issues[0].reason, "目标越出 vault")

    def test_decodes_percent_encoded_local_paths(self):
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "2026年07月").mkdir()
            (vault / "2026年07月" / "文章.md").write_text(
                "# 正文\n",
                encoding="utf-8",
            )
            (vault / "index.md").write_text(
                "[文章](2026%E5%B9%B407%E6%9C%88/%E6%96%87%E7%AB%A0.md)\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_local_links(vault), ())
```

- [ ] **Step 2: 运行链接测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_vault_restructure.LinkValidationTests -v
```

Expected: FAIL，链接扫描接口尚不存在。

- [ ] **Step 3: 实现 Markdown 链接扫描**

定义：

```python
@dataclass(frozen=True)
class LinkIssue:
    source: Path
    target: str
    reason: str


MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "data:")


def iter_managed_markdown(vault: Path):
    for path in sorted(Path(vault).rglob("*.md")):
        relative = path.relative_to(vault)
        if ".obsidian" in relative.parts:
            continue
        if relative.parts and relative.parts[0] in OLD_DIRECTORIES:
            continue
        yield path


def scan_local_links(vault: Path) -> tuple[LinkIssue, ...]:
    vault = assert_vault(vault)
    issues = []
    for source in iter_managed_markdown(vault):
        markdown = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(markdown):
            raw_target = match.group(1).strip()
            target_without_anchor = raw_target.split("#", 1)[0]
            if (
                not target_without_anchor
                or target_without_anchor.lower().startswith(EXTERNAL_SCHEMES)
            ):
                continue
            decoded = unquote(target_without_anchor)
            resolved = (source.parent / decoded).resolve()
            try:
                resolved.relative_to(vault)
            except ValueError:
                issues.append(LinkIssue(source, raw_target, "目标越出 vault"))
                continue
            if not resolved.exists():
                issues.append(LinkIssue(source, raw_target, "目标不存在"))
    return tuple(issues)
```

导入 `re`和`urllib.parse.unquote`。

- [ ] **Step 4: 写验证门禁和清理失败测试**

新增：

```python
class CleanupGateTests(unittest.TestCase):
    def test_validation_failure_keeps_all_old_directories(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            cleanup_old_directories,
            create_backup,
            validate_migration,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            plan = build_migration_plan(vault)
            manifest = (
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            create_backup(
                plan,
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-迁移前备份.zip",
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            (
                vault / "30_精选资料" / "AI" / "_attachments" / "agent.png"
            ).unlink()
            report = validate_migration(vault, manifest)
            with self.assertRaisesRegex(RuntimeError, "验证未通过"):
                cleanup_old_directories(plan, report)
            self.assertTrue((vault / "AI相关知识库").exists())
            self.assertTrue((vault / "Quant相关知识库").exists())
            self.assertTrue((vault / "HYXX个人知识库").exists())

    def test_successful_validation_removes_only_three_old_directories(self):
        from scripts.restructure_obsidian_vault import (
            apply_copy_phase,
            build_migration_plan,
            cleanup_old_directories,
            create_backup,
            validate_migration,
            write_link_report,
            write_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_old_vault(vault)
            keep = vault / "用户目录"
            keep.mkdir()
            plan = build_migration_plan(vault)
            manifest = (
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-文件清单.json"
            )
            create_backup(
                plan,
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-迁移前备份.zip",
            )
            write_manifest(plan, manifest)
            apply_copy_phase(plan)
            report = validate_migration(vault, manifest)
            write_link_report(
                report,
                vault
                / "90_系统"
                / "迁移记录"
                / "2026-07-27-链接检查.md",
            )
            self.assertTrue(report.passed, report.issues)
            cleanup_old_directories(plan, report)

            self.assertFalse((vault / "AI相关知识库").exists())
            self.assertFalse((vault / "Quant相关知识库").exists())
            self.assertFalse((vault / "HYXX个人知识库").exists())
            self.assertTrue(keep.exists())
```

- [ ] **Step 5: 实现验证报告**

定义：

```python
@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    issues: tuple[str, ...]
    markdown_files_before: int
    local_links_checked: int
    image_links_checked: int


def validate_migration(
    vault: Path,
    manifest_path: Path,
) -> ValidationReport:
    vault = assert_vault(vault)
    manifest = json.loads(
        Path(manifest_path).read_text(encoding="utf-8")
    )
    issues = []
    required_paths = [
        vault / "00_首页.md",
        vault / "10_项目" / "目录索引.md",
        vault / "20_知识笔记" / "目录索引.md",
        vault / "20_知识笔记" / "知识地图.md",
        vault / "90_系统" / "知识库治理" / "管理规则.md",
        vault / "90_系统" / "知识库治理" / "主题词表.md",
        vault / "90_系统" / "知识库治理" / "别名词典.md",
    ]
    required_paths.extend(
        vault / "30_精选资料" / domain / "目录索引.md"
        for domain in DOMAINS
    )
    for path in required_paths:
        if not path.exists():
            issues.append(f"缺少必需路径: {path}")

    for record in manifest["files"]:
        destination_text = record.get("destination")
        if destination_text is None:
            continue
        destination = vault / Path(destination_text)
        if not destination.is_file():
            issues.append(f"缺少迁移目标: {destination_text}")
            continue
        if (
            record.get("preserve_hash")
            and sha256_file(destination) != record["sha256"]
        ):
            issues.append(f"二进制文件哈希不一致: {destination_text}")

    issues.extend(
        f"{issue.source}: {issue.target}: {issue.reason}"
        for issue in scan_local_links(vault)
    )

    for markdown_path in iter_managed_markdown(vault):
        text = markdown_path.read_text(encoding="utf-8")
        for old_name in OLD_DIRECTORIES:
            if old_name in text:
                issues.append(
                    f"新结构仍引用旧目录: "
                    f"{markdown_path.relative_to(vault)}: {old_name}"
                )

    return ValidationReport(
        passed=not issues,
        issues=tuple(issues),
        markdown_files_before=sum(
            1
            for record in manifest["files"]
            if record["source"].lower().endswith(".md")
        ),
        local_links_checked=count_local_markdown_links(vault),
        image_links_checked=count_markdown_images(vault),
    )
```

基于 Step 3 已实现的`iter_managed_markdown()`增加统计：

```python
def count_markdown_images(vault: Path) -> int:
    return sum(
        len(re.findall(r"!\[[^\]]*\]\([^)]+\)", path.read_text(
            encoding="utf-8"
        )))
        for path in iter_managed_markdown(vault)
    )


def count_local_markdown_links(vault: Path) -> int:
    count = 0
    for path in iter_managed_markdown(vault):
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip().lower()
            if (
                not match.group(0).startswith("!")
                and target
                and not target.startswith(EXTERNAL_SCHEMES)
            ):
                count += 1
    return count
```

这样`scan_local_links()`、统计和验证都会只检查新结构。清理前还要断言三个
`plan.old_directories`均存在；清理后由`--verify`确认它们均不存在。

- [ ] **Step 6: 实现 Markdown 链接报告与迁移说明**

`write_link_report(report, path)`使用实际结果生成：

```python
def write_link_report(report: ValidationReport, path: Path) -> Path:
    issue_lines = (
        [f"- {issue}" for issue in report.issues]
        if report.issues
        else ["- 无"]
    )
    lines = [
        "# Obsidian vault 迁移链接检查",
        "",
        f"- 结果：{'通过' if report.passed else '失败'}",
        f"- 迁移前 Markdown：{report.markdown_files_before}",
        f"- 检查的 Markdown 链接：{report.local_links_checked}",
        f"- 检查的图片引用：{report.image_links_checked}",
        "",
        "## 问题",
        "",
        *issue_lines,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
```

`write_migration_summary(plan, report, path)`列出旧路径、目标路径、快照、清单、
执行时间、验证结果和旧目录清理结果。实际数量由报告写入，不能硬编码为通过。

实现：

```python
def write_migration_summary(
    plan: MigrationPlan,
    report: ValidationReport,
    path: Path,
    old_directories_removed: bool,
) -> Path:
    lines = [
        "# Obsidian vault 迁移说明",
        "",
        f"- 执行时间：{datetime.now().astimezone().isoformat()}",
        f"- vault：`{plan.vault}`",
        f"- 验证结果：{'通过' if report.passed else '失败'}",
        f"- 旧目录已清理：{'是' if old_directories_removed else '否'}",
        "- 快照：`2026-07-27-迁移前备份.zip`",
        "- 清单：`2026-07-27-文件清单.json`",
        "- 链接报告：`2026-07-27-链接检查.md`",
        "",
        "## 路径映射",
        "",
    ]
    for item in plan.items:
        lines.append(
            f"- `{item.source.relative_to(plan.vault)}`"
            f" → `{item.destination.relative_to(plan.vault)}`"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
```

- [ ] **Step 7: 实现严格限定的旧目录清理**

定义：

```python
def cleanup_old_directories(
    plan: MigrationPlan,
    report: ValidationReport,
):
    if not report.passed:
        raise RuntimeError("迁移验证未通过，保留全部旧目录")
    records = plan.vault / "90_系统" / "迁移记录"
    required_records = (
        records / "2026-07-27-迁移前备份.zip",
        records / "2026-07-27-文件清单.json",
        records / "2026-07-27-链接检查.md",
    )
    if not all(path.is_file() for path in required_records):
        raise RuntimeError("缺少迁移快照或文件清单，保留全部旧目录")
    for old_directory in plan.old_directories:
        resolved = old_directory.resolve()
        if resolved.parent != plan.vault:
            raise RuntimeError(f"拒绝删除非 vault 直接子目录: {resolved}")
        if resolved.name not in OLD_DIRECTORIES:
            raise RuntimeError(f"拒绝删除非白名单目录: {resolved}")
    for old_directory in plan.old_directories:
        shutil.rmtree(old_directory)
```

不得使用通配符、未解析变量或递归删除 vault 根目录。

- [ ] **Step 8: 串联完整 apply 和 verify 模式**

在参数解析器中新增：

```python
parser.add_argument(
    "--verify",
    action="store_true",
    help="只验证已迁移结构，不执行复制或删除",
)
```

`--apply`执行顺序固定为：

```python
plan = build_migration_plan(args.vault)
records = plan.vault / "90_系统" / "迁移记录"
backup = records / "2026-07-27-迁移前备份.zip"
manifest = records / "2026-07-27-文件清单.json"
link_report_path = records / "2026-07-27-链接检查.md"
summary_path = records / "2026-07-27-迁移说明.md"

create_backup(plan, backup)
write_manifest(plan, manifest)
apply_copy_phase(plan)
report = validate_migration(plan.vault, manifest)
write_link_report(report, link_report_path)
if not report.passed:
    return 1
cleanup_old_directories(plan, report)
write_migration_summary(
    plan,
    report,
    summary_path,
    old_directories_removed=True,
)
return 0
```

`--verify`必须支持旧目录已经删除的状态，直接从新结构和迁移清单构建验证上下文，
不再要求 `build_migration_plan()`找到旧源。实现：

```python
def verify_completed_vault(vault: Path) -> ValidationReport:
    vault = assert_vault(vault)
    manifest = (
        vault
        / "90_系统"
        / "迁移记录"
        / "2026-07-27-文件清单.json"
    )
    report = validate_migration(vault, manifest)
    remaining = [
        name for name in OLD_DIRECTORIES if (vault / name).exists()
    ]
    if not remaining:
        return report
    issues = report.issues + tuple(
        f"旧目录仍存在: {name}" for name in remaining
    )
    return ValidationReport(
        passed=False,
        issues=issues,
        markdown_files_before=report.markdown_files_before,
        local_links_checked=report.local_links_checked,
        image_links_checked=report.image_links_checked,
    )
```

`main()`必须优先判断`--verify`，调用`verify_completed_vault()`并按
`report.passed`返回 0 或 1。verify 模式不创建、修改或删除任何文件。

- [ ] **Step 9: 运行完整迁移测试**

Run:

```powershell
python -m unittest tests.test_vault_restructure -v
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS。

- [ ] **Step 10: 提交 Task 4**

```powershell
git add -- scripts/restructure_obsidian_vault.py tests/test_vault_restructure.py
git diff --cached --check
git commit -m "增加 Obsidian 迁移验证与安全清理"
```

---

### Task 5: 同步 Skill 规则、命令文档与契约测试

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `references/obsidian-knowledge-management.md`
- Modify: `tests/test_skill_documentation.py`

**Interfaces:**
- Consumes: 已确认设计文档与 Task 1–4 的命令行接口。
- Produces: 与真实 vault 一致的 Skill 决策规则、迁移命令说明和文档契约测试。

- [ ] **Step 1: 写新目录和迁移命令失败测试**

在 `tests/test_skill_documentation.py` 新增：

```python
def test_documents_final_vault_structure_and_migration_command(self):
    reference = (
        REPO_ROOT / "references" / "obsidian-knowledge-management.md"
    ).read_text(encoding="utf-8")
    combined = self.skill + self.readme + reference

    for phrase in (
        "10_项目",
        "20_知识笔记",
        "30_精选资料",
        "90_系统/知识库治理",
        "整个 vault 是 LLM Wiki",
        "20_知识笔记/目录索引.md",
        "20_知识笔记/知识地图.md",
        "scripts/restructure_obsidian_vault.py",
        "--confirm MIGRATE_OBSIDIAN_VAULT",
        r"30_精选资料\AI",
    ):
        with self.subTest(phrase=phrase):
            self.assertIn(phrase, combined)

    for obsolete in (
        "10_知识库",
        "20_项目",
        "90_系统/LLM Wiki/",
    ):
        with self.subTest(obsolete=obsolete):
            self.assertNotIn(obsolete, reference)
```

新增索引职责断言：

```python
def test_documents_distinct_catalog_map_and_source_index_rules(self):
    reference = (
        REPO_ROOT / "references" / "obsidian-knowledge-management.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "按 `domain` 分组",
        "可由脚本或 AI 完整重建",
        "不保存人工评论",
        "人工维护核心概念",
        "仅关键词相同不足以建立关系",
        "每个领域保留一份独立的 `目录索引.md`",
    ):
        self.assertIn(phrase, reference)
```

- [ ] **Step 2: 运行文档测试并确认 RED**

Run:

```powershell
python -m unittest tests.test_skill_documentation -v
```

Expected: FAIL，参考文档仍使用旧目录编号和旧治理路径。

- [ ] **Step 3: 更新知识管理参考文档**

按设计文档逐项修改：

- 目标目录改为最终目录树；
- `10_项目`说明不预建领域目录；
- `20_知识笔记`说明只有两份根索引；
- `30_精选资料`说明每个领域有独立索引；
- `90_系统/LLM Wiki`改为`90_系统/知识库治理`；
- 明确整个 vault 是 LLM Wiki；
- 增加四类旧根标签映射；
- 正式主题只有 `主题/Agent`，其余八项为候选；
- 补充迁移快照、清单、链接报告和验证后清理规则。

- [ ] **Step 4: 更新 SKILL 和 README 命令**

在 `SKILL.md`快速参考中增加：

```markdown
| 预览 vault 重组 | `python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian"` | 只读本地 |
| 执行 vault 重组 | `python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --apply --confirm MIGRATE_OBSIDIAN_VAULT` | 修改本地 vault |
| 验证 vault 结构 | `python scripts/restructure_obsidian_vault.py --vault "D:\OneDrive\文档\@_Obsidian" --verify` | 只读本地 |
```

在 `README.md`增加“统一 LLM Wiki 结构”章节，记录相同的预览、执行和验证命令，
以及后续精选导出命令：

```powershell
python scripts/export_search_results.py `
  --since 2025-07-27 `
  --keywords AI Agent 人工智能 `
  --domain AI `
  --limit 3 `
  --target "D:\OneDrive\文档\@_Obsidian\30_精选资料\AI"
```

明确执行命令会创建 ZIP 快照，验证失败不会删除旧目录。

- [ ] **Step 5: 更新 `.env.example`**

保留占位 Token 和 NoteStore URL，只把 vault 示例改为：

```dotenv
OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian
```

不得把真实 `.env`加入 Git。

- [ ] **Step 6: 运行文档测试和完整测试**

Run:

```powershell
python -m unittest tests.test_skill_documentation -v
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交 Task 5**

```powershell
git add -- SKILL.md README.md .env.example references/obsidian-knowledge-management.md tests/test_skill_documentation.py
git diff --cached --check
git commit -m "同步 Obsidian LLM Wiki 最终目录规则"
```

---

### Task 6: 对真实 Obsidian vault 执行受控迁移

**Files:**
- Modify, ignored: `.env`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\00_首页.md`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\01_收件箱\`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\10_项目\`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\20_知识笔记\`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\30_精选资料\`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\90_系统\`
- Create outside Git: `D:\OneDrive\文档\@_Obsidian\99_归档\`
- Remove after validation: `D:\OneDrive\文档\@_Obsidian\AI相关知识库\`
- Remove after validation: `D:\OneDrive\文档\@_Obsidian\Quant相关知识库\`
- Remove after validation: `D:\OneDrive\文档\@_Obsidian\HYXX个人知识库\`

**Interfaces:**
- Consumes: Task 4 的 dry-run/apply/verify CLI。
- Produces: 已迁移且验证通过的真实 vault、迁移 ZIP、JSON 清单、链接报告和迁移说明。

- [ ] **Step 1: 在真实执行前运行完整测试**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS。若失败，停止，不触碰真实 vault。

- [ ] **Step 2: 验证真实 vault 和旧目录现状**

Run:

```powershell
$vault = [System.IO.Path]::GetFullPath('D:\OneDrive\文档\@_Obsidian')
$expected = [System.IO.Path]::GetFullPath('D:\OneDrive\文档\@_Obsidian')
if ($vault -ne $expected) { throw "vault 路径不一致" }
Get-Item -LiteralPath (Join-Path $vault '.obsidian')
Get-Item -LiteralPath (Join-Path $vault 'AI相关知识库')
Get-Item -LiteralPath (Join-Path $vault 'Quant相关知识库')
Get-Item -LiteralPath (Join-Path $vault 'HYXX个人知识库')
```

Expected: 四个路径均存在，且 `$vault`为精确目标。

- [ ] **Step 3: 运行预览并人工核对映射**

Run:

```powershell
python scripts/restructure_obsidian_vault.py `
  --vault "D:\OneDrive\文档\@_Obsidian"
```

Expected: 输出“预览模式”，列出三项精确映射；不创建`20_知识笔记`、
`30_精选资料`或迁移记录。

- [ ] **Step 4: 补充本地 `.env` vault 路径**

只在被 Git 忽略的 `.env`末尾增加：

```dotenv
OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian
```

先确认不存在同名键；如已存在，只替换该键的值。不得打印或修改其他配置。

- [ ] **Step 5: 执行真实迁移**

Run:

```powershell
python scripts/restructure_obsidian_vault.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --apply `
  --confirm MIGRATE_OBSIDIAN_VAULT
```

Expected:

- 生成 ZIP、JSON 清单、链接报告和迁移说明；
- 创建最终目录树、首页、索引、治理文件和模板；
- 复制并规范现有内容；
- 验证通过后只删除三个白名单旧目录；
- 返回退出码 0。

如退出码非 0，停止。不得手工删除旧目录；读取链接报告定位问题。

- [ ] **Step 6: 运行只读验证模式**

Run:

```powershell
python scripts/restructure_obsidian_vault.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --verify
```

Expected: PASS；验证模式能在旧目录已删除的状态下工作。

- [ ] **Step 7: 核对真实验收条件**

Run:

```powershell
$vault = 'D:\OneDrive\文档\@_Obsidian'
$required = @(
  '00_首页.md',
  '10_项目\目录索引.md',
  '20_知识笔记\目录索引.md',
  '20_知识笔记\知识地图.md',
  '20_知识笔记\软件工程\Codex CLI 使用技巧记录.md',
  '30_精选资料\AI\目录索引.md',
  '30_精选资料\Quant\目录索引.md',
  '90_系统\知识库治理\管理规则.md',
  '90_系统\迁移记录\2026-07-27-迁移前备份.zip',
  '90_系统\迁移记录\2026-07-27-文件清单.json',
  '90_系统\迁移记录\2026-07-27-链接检查.md',
  '90_系统\迁移记录\2026-07-27-迁移说明.md'
)
foreach ($relative in $required) {
  if (-not (Test-Path -LiteralPath (Join-Path $vault $relative))) {
    throw "缺少验收路径: $relative"
  }
}
foreach ($old in @('AI相关知识库','Quant相关知识库','HYXX个人知识库')) {
  if (Test-Path -LiteralPath (Join-Path $vault $old)) {
    throw "旧目录仍存在: $old"
  }
}
```

Expected: 无异常。

- [ ] **Step 8: 检查迁移报告结论**

读取：

```powershell
Get-Content -LiteralPath 'D:\OneDrive\文档\@_Obsidian\90_系统\迁移记录\2026-07-27-链接检查.md' -Encoding UTF8
Get-Content -LiteralPath 'D:\OneDrive\文档\@_Obsidian\90_系统\迁移记录\2026-07-27-迁移说明.md' -Encoding UTF8
```

Expected: 结果为通过；不存在缺失本地链接、越界目标、旧目录引用或附件哈希异常。

---

### Task 7: 最终回归、范围审计与交付

**Files:**
- Verify only: repository and real vault

**Interfaces:**
- Consumes: Task 1–6 的提交和真实迁移结果。
- Produces: 可交付的本地 `main`工作区与验收证据。

- [ ] **Step 1: 运行仓库完整回归**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Expected: 全部 PASS。

- [ ] **Step 2: 审计 Git 范围**

Run:

```powershell
git status --short
git log --oneline fc2d03e..HEAD
git diff --name-only fc2d03e..HEAD
```

Expected:

- `.env`不出现在 Git 变更中；
- 只修改计划列出的脚本、测试、Skill、README、`.env.example`和参考文档；
- 不提交真实 vault 内容、ZIP、迁移清单或账号配置。

- [ ] **Step 3: 对真实 vault 做最终只读验证**

Run:

```powershell
python scripts/restructure_obsidian_vault.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --verify
```

Expected: PASS。

- [ ] **Step 4: 检查敏感信息**

Run:

```powershell
rg -n "S=s[0-9]+:U=[0-9a-f]+:E=[0-9a-f]+:" `
  SKILL.md README.md .env.example references templates scripts tests
```

Expected: 无真实 Developer Token 命中。

- [ ] **Step 5: 请求最终代码审查**

最终审查范围使用：

```powershell
git diff fc2d03e..HEAD
```

审查重点：

- 默认预览与固定确认词是否可靠；
- ZIP 和清单是否先于复制与删除；
- 删除目标是否严格限定为三个 vault 直接子目录；
- 验证失败是否保留旧目录；
- Frontmatter 是否只修改允许字段且保留正文；
- 索引、知识地图和治理规则是否与设计一致；
- 真实 vault 验收证据是否完整。

- [ ] **Step 6: 处理 Critical/Important 发现并重新验证**

只修复审查确认的 Critical/Important 问题。每次修复后运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
python scripts/restructure_obsidian_vault.py `
  --vault "D:\OneDrive\文档\@_Obsidian" `
  --verify
```

Expected: 全部 PASS。
