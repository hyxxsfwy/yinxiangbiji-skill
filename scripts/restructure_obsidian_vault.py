from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

try:
    from scripts.knowledge_base import write_knowledge_base_index
except ModuleNotFoundError:
    from knowledge_base import write_knowledge_base_index


CONFIRMATION = "MIGRATE_OBSIDIAN_VAULT"
DOMAINS = ("AI", "Quant", "软件工程", "投资理财", "个人成长")
OLD_DIRECTORIES = ("AI相关知识库", "Quant相关知识库", "HYXX个人知识库")
QUANT_FILENAME = "GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
CODEX_FILENAME = "Codex CLI 使用技巧记录.md"
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "data:")
FRONTMATTER_RE = re.compile(
    r"\A---\r?\n(.*?)\r?\n---",
    re.DOTALL,
)
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
AGENT_TITLES = {
    "Github 26.6k star，字节把 AI Agent 的记忆重做了一遍，不用向量数据库也能管上下文！",
    "一张图看懂 AI Agent 全流程",
    "删掉80%的Skill，Agent反而更听话了",
}


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


@dataclass(frozen=True)
class LinkIssue:
    source: Path
    target: str
    reason: str


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    issues: tuple[str, ...]
    markdown_files_before: int
    local_links_checked: int
    image_links_checked: int


def assert_vault(vault: Path) -> Path:
    resolved = Path(vault).resolve()
    if not (resolved / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault，缺少 .obsidian: {resolved}")
    return resolved


def iter_managed_markdown(vault: Path):
    for path in sorted(Path(vault).rglob("*.md")):
        if not path.is_file():
            continue
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


def count_markdown_images(vault: Path) -> int:
    return sum(
        len(
            re.findall(
                r"!\[[^\]]*\]\([^)]+\)",
                path.read_text(encoding="utf-8"),
            )
        )
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


def destination_for_source(plan: MigrationPlan, source: Path) -> Path | None:
    relative = source.relative_to(plan.vault)
    parts = relative.parts
    if parts[0] == "AI相关知识库":
        return plan.vault / "30_精选资料" / "AI" / Path(*parts[1:])
    if relative.as_posix() == (
        "Quant相关知识库/GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
    ):
        return plan.vault / "30_精选资料" / "Quant" / "2026年06月" / QUANT_FILENAME
    if relative.as_posix() == "HYXX个人知识库/Codex CLI 使用技巧记录.md":
        return plan.vault / "20_知识笔记" / "软件工程" / CODEX_FILENAME
    return None


def backup_entries(plan: MigrationPlan):
    for old_directory in plan.old_directories:
        for path in sorted(old_directory.rglob("*")):
            relative = path.relative_to(plan.vault).as_posix()
            if path.is_dir():
                yield relative.rstrip("/") + "/", None
            else:
                yield relative, path


def backup_matches_sources(plan: MigrationPlan, backup_path: Path) -> bool:
    expected_entries = tuple(backup_entries(plan))
    expected_names = tuple(name for name, _ in expected_entries)
    try:
        with zipfile.ZipFile(backup_path) as archive:
            actual_names = tuple(archive.namelist())
            if (
                len(actual_names) != len(expected_names)
                or set(actual_names) != set(expected_names)
                or archive.testzip() is not None
            ):
                return False
            for name, source in expected_entries:
                info = archive.getinfo(name)
                if source is None:
                    if not info.is_dir():
                        return False
                    continue
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != sha256_file(source):
                    return False
    except (OSError, KeyError, zipfile.BadZipFile):
        return False
    return True


def create_backup(plan: MigrationPlan, backup_path: Path) -> Path:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        if backup_matches_sources(plan, backup_path):
            return backup_path
        raise FileExistsError(
            f"备份已存在但与当前迁移源不匹配，拒绝复用: {backup_path}"
        )
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, source in backup_entries(plan):
            if source is None:
                archive.writestr(relative, b"")
            else:
                archive.write(source, relative)
    return backup_path


def manifest_source_state(plan: MigrationPlan) -> dict[str, object]:
    return {
        "vault": str(plan.vault),
        "files": [
            {
                "source": path.relative_to(plan.vault).as_posix(),
                "destination": (
                    destination.relative_to(plan.vault).as_posix()
                    if (destination := destination_for_source(plan, path)) is not None
                    else None
                ),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "preserve_hash": path.suffix.lower() != ".md",
            }
            for path in iter_old_files(plan)
        ],
    }


def write_manifest(plan: MigrationPlan, manifest_path: Path) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source_state = manifest_source_state(plan)
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            created_at = existing["created_at"]
            datetime.fromisoformat(created_at)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FileExistsError(
                f"清单已存在但格式无效，拒绝复用: {manifest_path}"
            ) from exc
        if (
            set(existing) == {"vault", "created_at", "files"}
            and existing["vault"] == source_state["vault"]
            and existing["files"] == source_state["files"]
        ):
            return manifest_path
        raise FileExistsError(
            f"清单已存在但与当前迁移源不匹配，拒绝复用: {manifest_path}"
        )
    payload = {
        "vault": source_state["vault"],
        "created_at": datetime.now().astimezone().isoformat(),
        "files": source_state["files"],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


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
            fields, body = split_frontmatter(path.read_text(encoding="utf-8"))
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
    domain_sections = "\n\n".join(f"### {domain}\n" for domain in DOMAINS)
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
        if stripped and not stripped.startswith(("#", "![", ">", "---")):
            return stripped[:120]
    return "暂无摘要"


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


def yaml_value(value) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


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
    had_frontmatter = FRONTMATTER_RE.match(markdown) is not None
    fields, body = split_frontmatter(markdown)
    fields.update(required)
    rendered = render_frontmatter(fields).rstrip("\n")
    if had_frontmatter:
        return rendered + body
    return rendered + "\n\n" + body


def write_expected_text(destination: Path, expected: str):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with destination.open("r", encoding="utf-8", newline="") as stream:
            actual = stream.read()
        if actual == expected:
            return
        raise FileExistsError(f"目标文本已存在且内容不同: {destination}")
    with destination.open("w", encoding="utf-8", newline="") as stream:
        stream.write(expected)


def copy_file_without_overwrite(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) == sha256_file(destination):
            return
        raise FileExistsError(f"目标已存在且内容不同: {destination}")
    shutil.copy2(source, destination)


def title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            if title.startswith("[") and "](" in title:
                title = title[1:title.index("](")]
            return title
    return fallback


def install_templates(plan: MigrationPlan):
    repo_root = Path(__file__).resolve().parent.parent
    mappings = {
        "obsidian-source-note.md": "精选资料模板.md",
        "obsidian-knowledge-note.md": "知识笔记模板.md",
        "obsidian-knowledge-map.md": "知识地图模板.md",
    }
    for source_name, destination_name in mappings.items():
        source = repo_root / "templates" / source_name
        destination = plan.vault / "90_系统" / "模板" / destination_name
        write_expected_text(
            destination,
            source.read_text(encoding="utf-8"),
        )


def copy_mapped_content(plan: MigrationPlan):
    old_ai = plan.vault / "AI相关知识库"
    new_ai = plan.vault / "30_精选资料" / "AI"
    for source in sorted(old_ai.rglob("*")):
        if not source.is_file() or source.name == "目录索引.md":
            continue
        destination = new_ai / source.relative_to(old_ai)
        if source.suffix.lower() != ".md":
            copy_file_without_overwrite(source, destination)
            continue
        with source.open("r", encoding="utf-8", newline="") as stream:
            original = stream.read()
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
    with quant_source.open("r", encoding="utf-8", newline="") as stream:
        quant_original = stream.read()
    quant_expected = merge_frontmatter(
        quant_original,
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

    codex_source = plan.vault / "HYXX个人知识库" / CODEX_FILENAME
    codex_destination = (
        plan.vault / "20_知识笔记" / "软件工程" / CODEX_FILENAME
    )
    with codex_source.open("r", encoding="utf-8", newline="") as stream:
        codex_original = stream.read()
    codex_expected = merge_frontmatter(
        codex_original,
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


def apply_copy_phase(plan: MigrationPlan):
    ensure_target_structure(plan)
    copy_mapped_content(plan)
    install_templates(plan)
    write_vault_documents(plan)


def write_vault_documents(plan: MigrationPlan):
    vault = plan.vault
    documents = {
        vault / "00_首页.md": render_home(),
        vault / "10_项目" / "目录索引.md": render_project_index(),
        vault / "20_知识笔记" / "知识地图.md": render_knowledge_map(),
        vault / "90_系统" / "知识库治理" / "管理规则.md": render_management_rules(),
        vault / "90_系统" / "知识库治理" / "主题词表.md": render_topic_vocabulary(),
        vault / "90_系统" / "知识库治理" / "别名词典.md": render_alias_dictionary(),
    }
    for destination, content in documents.items():
        write_expected_text(destination, content)
    (vault / "20_知识笔记" / "目录索引.md").write_text(
        render_knowledge_catalog(vault),
        encoding="utf-8",
    )
    for domain in DOMAINS:
        write_knowledge_base_index(vault / "30_精选资料" / domain, domain=domain)


def validate_migration(
    vault: Path,
    manifest_path: Path,
) -> ValidationReport:
    vault = assert_vault(vault)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
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
        if not path.is_file():
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
        relative = markdown_path.relative_to(vault)
        if relative.parts[:2] == ("90_系统", "迁移记录"):
            continue
        text = markdown_path.read_text(encoding="utf-8")
        for old_name in OLD_DIRECTORIES:
            if old_name in text:
                issues.append(
                    f"新结构仍引用旧目录: "
                    f"{relative}: {old_name}"
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
    if not all(path.is_dir() for path in plan.old_directories):
        raise RuntimeError("旧目录不完整，保留全部旧目录")
    for old_directory in plan.old_directories:
        resolved = old_directory.resolve()
        if resolved.parent != plan.vault:
            raise RuntimeError(f"拒绝删除非 vault 直接子目录: {resolved}")
        if resolved.name not in OLD_DIRECTORIES:
            raise RuntimeError(f"拒绝删除非白名单目录: {resolved}")
    for old_directory in plan.old_directories:
        shutil.rmtree(old_directory)


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


def print_plan(plan: MigrationPlan):
    print("预览模式：不会修改 vault")
    for item in plan.items:
        print(
            f"- {item.source.relative_to(plan.vault)}"
            f" -> {item.destination.relative_to(plan.vault)}"
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="安全重组 HYXX Obsidian LLM Wiki")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只验证已迁移结构，不执行复制或删除",
    )
    parser.add_argument("--confirm")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if args.verify:
        report = verify_completed_vault(args.vault)
        return 0 if report.passed else 1
    if args.apply and args.confirm != CONFIRMATION:
        print(
            f"--apply 必须同时提供 --confirm {CONFIRMATION}",
            file=sys.stderr,
        )
        return 2
    plan = build_migration_plan(args.vault)
    if args.apply:
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
    print_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
