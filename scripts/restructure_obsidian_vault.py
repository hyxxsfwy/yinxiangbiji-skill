from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

try:
    from scripts.domain_taxonomy import MANAGED_DOMAINS
    from scripts.knowledge_base import write_knowledge_base_index
    from scripts.runtime import load_vault_root
    from scripts.vault_state import (
        VaultStatePaths,
        migrate_legacy_state,
        runtime_write_lock,
    )
except ModuleNotFoundError:
    from domain_taxonomy import MANAGED_DOMAINS
    from knowledge_base import write_knowledge_base_index
    from runtime import load_vault_root
    from vault_state import (
        VaultStatePaths,
        migrate_legacy_state,
        runtime_write_lock,
    )


CONFIRMATION = "MIGRATE_OBSIDIAN_VAULT"
REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAINS = MANAGED_DOMAINS
LEGACY_CONTENT_DIRECTORIES = (
    "AI相关知识库",
    "Quant相关知识库",
    "HYXX个人知识库",
)
LEGACY_LIFECYCLE_MAPPINGS = {
    "90_系统": "80_系统",
    "99_归档": "90_归档",
}
OLD_DIRECTORIES = (
    *LEGACY_CONTENT_DIRECTORIES,
    *LEGACY_LIFECYCLE_MAPPINGS,
)
QUANT_FILENAME = "GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
CODEX_FILENAME = "Codex CLI 使用技巧记录.md"
INLINE_LINK_START = re.compile(r"(!?)\[[^\]\n]*\]\(")
WIKILINK = re.compile(r"(!?)\[\[([^\]\n]+)\]\](?!\()")
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "data:")
MIGRATION_RECORD_NAMES = {
    "backup": "2026-07-27-迁移前备份.zip",
    "manifest": "2026-07-27-文件清单.json",
    "link_report": "2026-07-27-链接检查.md",
    "summary": "2026-07-27-迁移说明.md",
}
LEGACY_MANIFEST_KEYS = {"vault", "created_at", "files"}
CURRENT_MANIFEST_KEYS = {
    "schema_version",
    "vault",
    "created_at",
    "migration_result",
    "link_check_result",
    "files",
}
MANIFEST_FILE_KEYS = {
    "source",
    "destination",
    "size",
    "sha256",
    "preserve_hash",
}
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
class MarkdownReference:
    target: str
    is_image: bool
    is_wikilink: bool


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    issues: tuple[str, ...]
    markdown_files_before: int
    local_links_checked: int
    image_links_checked: int
    wiki_links_checked: int = 0


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


def _inline_destination(markdown: str, start: int) -> tuple[str, int] | None:
    depth = 0
    escaped = False
    for index in range(start, len(markdown)):
        character = markdown[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "(":
            depth += 1
            continue
        if character == ")":
            if depth:
                depth -= 1
                continue
            return markdown[start:index], index + 1
    return None


def _destination_without_title(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<"):
        escaped = False
        for index, character in enumerate(value[1:], 1):
            if escaped:
                escaped = False
                continue
            if character == "\\":
                escaped = True
                continue
            if character == ">":
                return value[1:index]
        return value

    depth = 0
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "(":
            depth += 1
            continue
        if character == ")" and depth:
            depth -= 1
            continue
        if character.isspace() and depth == 0:
            return value[:index]
    return value


def _without_markdown_code_blocks(markdown: str) -> str:
    """移除围栏和缩进代码块，避免把示例链接当成真实引用。"""
    rendered = []
    fence = None
    for line in markdown.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = (value[0], len(value))
            elif value[0] == fence[0] and len(value) >= fence[1]:
                fence = None
            rendered.append("\n" if line.endswith(("\n", "\r")) else "")
            continue
        if fence is not None or line.startswith(("    ", "\t")):
            rendered.append("\n" if line.endswith(("\n", "\r")) else "")
            continue
        rendered.append(line)
    return "".join(rendered)


def iter_markdown_references(markdown: str):
    markdown = _without_markdown_code_blocks(markdown)
    for match in INLINE_LINK_START.finditer(markdown):
        parsed = _inline_destination(markdown, match.end())
        if parsed is None:
            continue
        raw, _ = parsed
        target = _destination_without_title(raw).replace(r"\(", "(").replace(
            r"\)", ")"
        )
        yield MarkdownReference(
            target=target,
            is_image=bool(match.group(1)),
            is_wikilink=False,
        )
    for match in WIKILINK.finditer(markdown):
        yield MarkdownReference(
            target=match.group(2).strip(),
            is_image=bool(match.group(1)),
            is_wikilink=True,
        )


def _inside_vault(vault: Path, path: Path) -> bool:
    try:
        path.relative_to(vault)
    except ValueError:
        return False
    return True


def _resolve_wikilink(
    vault: Path,
    source: Path,
    target: str,
) -> tuple[Path | None, str | None]:
    link_path = PurePosixPath(unquote(target.replace("\\", "/")))
    if link_path.is_absolute() or ".." in link_path.parts:
        return None, "目标越出 vault"
    candidates = []
    requested = Path(*link_path.parts)
    if not requested.suffix:
        requested = requested.with_suffix(".md")
    for candidate in (
        (source.parent / requested).resolve(),
        (vault / requested).resolve(),
    ):
        if _inside_vault(vault, candidate) and candidate not in candidates:
            candidates.append(candidate)
    regular_files = [candidate for candidate in candidates if candidate.is_file()]
    if regular_files:
        return regular_files[0], None
    if any(candidate.exists() for candidate in candidates):
        return None, "目标不是普通文件"
    if len(link_path.parts) == 1 and not link_path.suffix:
        matches = [
            path
            for path in iter_managed_markdown(vault)
            if path.stem == link_path.name
        ]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "目标不唯一"
    return None, "目标不存在"


def scan_local_links(vault: Path) -> tuple[LinkIssue, ...]:
    vault = assert_vault(vault)
    issues = []
    for source in iter_managed_markdown(vault):
        markdown = source.read_text(encoding="utf-8")
        for reference in iter_markdown_references(markdown):
            raw_target = reference.target.strip()
            if reference.is_wikilink:
                target_without_alias = raw_target.split("|", 1)[0].strip()
                target_without_anchor = re.split(
                    r"[#^]",
                    target_without_alias,
                    maxsplit=1,
                )[0].strip()
            else:
                target_without_anchor = raw_target.split("#", 1)[0].strip()
            if (
                not target_without_anchor
                or target_without_anchor.lower().startswith(EXTERNAL_SCHEMES)
            ):
                continue
            if reference.is_wikilink:
                _, reason = _resolve_wikilink(
                    vault,
                    source,
                    target_without_anchor,
                )
                if reason:
                    issues.append(LinkIssue(source, raw_target, reason))
                continue
            decoded = unquote(target_without_anchor)
            resolved = (source.parent / decoded).resolve()
            if not _inside_vault(vault, resolved):
                issues.append(LinkIssue(source, raw_target, "目标越出 vault"))
            elif not resolved.exists():
                issues.append(LinkIssue(source, raw_target, "目标不存在"))
            elif not resolved.is_file():
                issues.append(LinkIssue(source, raw_target, "目标不是普通文件"))
    return tuple(issues)


def count_markdown_images(vault: Path) -> int:
    return sum(
        1
        for path in iter_managed_markdown(vault)
        for reference in iter_markdown_references(
            path.read_text(encoding="utf-8")
        )
        if reference.is_image
    )


def count_local_markdown_links(vault: Path) -> int:
    return sum(
        1
        for path in iter_managed_markdown(vault)
        for reference in iter_markdown_references(
            path.read_text(encoding="utf-8")
        )
        if not reference.is_image
        and not reference.is_wikilink
        and reference.target
        and not reference.target.lower().startswith(EXTERNAL_SCHEMES)
    )


def count_wikilinks(vault: Path) -> int:
    return sum(
        1
        for path in iter_managed_markdown(vault)
        for reference in iter_markdown_references(
            path.read_text(encoding="utf-8")
        )
        if reference.is_wikilink
    )


def build_migration_plan(vault: Path) -> MigrationPlan:
    vault = assert_vault(vault)
    content_items = (
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
            vault / "20_知识笔记" / "信息技术" / CODEX_FILENAME,
            "copy_file",
        ),
    )
    items = []
    if any((vault / name).exists() for name in LEGACY_CONTENT_DIRECTORIES):
        missing = [
            str(item.source)
            for item in content_items
            if not item.source.exists()
        ]
        if missing:
            raise FileNotFoundError("缺少迁移源:\n" + "\n".join(missing))
        items.extend(content_items)
    for source_name, destination_name in LEGACY_LIFECYCLE_MAPPINGS.items():
        source = vault / source_name
        if source.exists():
            items.append(
                MigrationItem(
                    source,
                    vault / destination_name,
                    "copy_tree",
                )
            )
    return MigrationPlan(
        vault=vault,
        items=tuple(items),
        old_directories=tuple(
            vault / name
            for name in OLD_DIRECTORIES
            if (vault / name).exists()
        ),
    )


def find_migration_conflicts(plan: MigrationPlan) -> tuple[str, ...]:
    conflicts = []
    for item in plan.items:
        if item.source.name not in LEGACY_LIFECYCLE_MAPPINGS:
            continue
        if item.operation == "copy_file":
            candidates = ((item.source, item.destination),)
        else:
            candidates = tuple(
                (
                    source,
                    item.destination / source.relative_to(item.source),
                )
                for source in sorted(item.source.rglob("*"))
            )
            if item.destination.exists() and not item.destination.is_dir():
                conflicts.append(
                    f"目标类型冲突: {item.destination.relative_to(plan.vault).as_posix()}"
                )
        for source, destination in candidates:
            if not destination.exists():
                continue
            relative = destination.relative_to(plan.vault).as_posix()
            if source.is_dir():
                if not destination.is_dir():
                    conflicts.append(f"目标类型冲突: {relative}")
                continue
            if not destination.is_file():
                conflicts.append(f"目标类型冲突: {relative}")
            elif (
                expected_migration_bytes(plan, source)
                != destination.read_bytes()
            ):
                conflicts.append(f"目标内容冲突: {relative}")
    return tuple(dict.fromkeys(conflicts))


def expected_migration_bytes(plan: MigrationPlan, source: Path) -> bytes:
    content = source.read_bytes()
    relative = source.relative_to(plan.vault)
    if (
        relative.parts
        and relative.parts[0] in LEGACY_LIFECYCLE_MAPPINGS
        and source.suffix.lower() == ".md"
    ):
        return (
            content
            .replace("90_系统/".encode(), "80_系统/".encode())
            .replace("99_归档/".encode(), "90_归档/".encode())
        )
    return content


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
    if parts[0] in LEGACY_LIFECYCLE_MAPPINGS:
        return (
            plan.vault
            / LEGACY_LIFECYCLE_MAPPINGS[parts[0]]
            / Path(*parts[1:])
        )
    if parts[0] == "AI相关知识库":
        return plan.vault / "30_精选资料" / "AI" / Path(*parts[1:])
    if relative.as_posix() == (
        "Quant相关知识库/GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
    ):
        return plan.vault / "30_精选资料" / "Quant" / "2026年06月" / QUANT_FILENAME
    if relative.as_posix() == "HYXX个人知识库/Codex CLI 使用技巧记录.md":
        return plan.vault / "20_知识笔记" / "信息技术" / CODEX_FILENAME
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
            set(existing) in (LEGACY_MANIFEST_KEYS, CURRENT_MANIFEST_KEYS)
            and existing["vault"] == source_state["vault"]
            and existing["files"] == source_state["files"]
        ):
            return manifest_path
        raise FileExistsError(
            f"清单已存在但与当前迁移源不匹配，拒绝复用: {manifest_path}"
        )
    payload = {
        "schema_version": 2,
        "vault": source_state["vault"],
        "created_at": datetime.now().astimezone().isoformat(),
        "migration_result": "pending",
        "link_check_result": {
            "result": "pending",
            "issues": None,
            "markdown_links_checked": None,
            "image_links_checked": None,
            "wiki_links_checked": None,
        },
        "files": source_state["files"],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def record_manifest_results(
    manifest_path: Path,
    report: ValidationReport,
) -> Path:
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(payload) != CURRENT_MANIFEST_KEYS or payload.get("schema_version") != 2:
        raise ValueError("只有新版清单可以记录迁移完成结果")
    payload["migration_result"] = "completed" if report.passed else "failed"
    payload["link_check_result"] = {
        "result": "passed" if report.passed else "failed",
        "issues": len(report.issues),
        "markdown_links_checked": report.local_links_checked,
        "image_links_checked": report.image_links_checked,
        "wiki_links_checked": report.wiki_links_checked,
    }
    temporary = manifest_path.with_name(f".{manifest_path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest_path


def migration_record_paths(
    vault: Path,
    plan: MigrationPlan | None = None,
) -> dict[str, Path]:
    records = Path(vault) / "80_系统" / "迁移记录"
    if plan is not None and any(
        path.name == "90_系统"
        for path in plan.old_directories
    ):
        records = records / "目录重编号"
    elif plan is None:
        renumbered = records / "目录重编号"
        if all(
            (renumbered / filename).is_file()
            for filename in MIGRATION_RECORD_NAMES.values()
        ):
            records = renumbered
    return {
        key: records / filename
        for key, filename in MIGRATION_RECORD_NAMES.items()
    }


def expected_destination_for_source(source: str) -> str | None:
    relative = PurePosixPath(source)
    if (
        relative.parts
        and relative.parts[0] in LEGACY_LIFECYCLE_MAPPINGS
    ):
        return PurePosixPath(
            LEGACY_LIFECYCLE_MAPPINGS[relative.parts[0]],
            *relative.parts[1:],
        ).as_posix()
    if relative.parts and relative.parts[0] == "AI相关知识库":
        return PurePosixPath(
            "30_精选资料",
            "AI",
            *relative.parts[1:],
        ).as_posix()
    if source == f"Quant相关知识库/{QUANT_FILENAME}":
        return PurePosixPath(
            "30_精选资料",
            "Quant",
            "2026年06月",
            QUANT_FILENAME,
        ).as_posix()
    if source == f"HYXX个人知识库/{CODEX_FILENAME}":
        return PurePosixPath(
            "20_知识笔记",
            "信息技术",
            CODEX_FILENAME,
        ).as_posix()
    return None


def _safe_manifest_relative(value, label: str) -> tuple[PurePosixPath | None, str | None]:
    if not isinstance(value, str) or not value or "\\" in value:
        return None, f"{label}不是规范的 POSIX 相对路径: {value!r}"
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        return None, f"{label}越出 vault: {value!r}"
    return relative, None


def load_manifest_strict(
    vault: Path,
    manifest_path: Path,
    *,
    completed: bool,
) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    vault = Path(vault).resolve()
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        return None, (f"迁移记录不是普通文件: {manifest_path.name}",)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, (f"迁移清单无法读取: {exc}",)
    if not isinstance(payload, dict):
        return None, ("迁移清单根节点必须是对象",)

    issues = []
    keys = set(payload)
    is_legacy = keys == LEGACY_MANIFEST_KEYS
    is_current = keys == CURRENT_MANIFEST_KEYS
    if not (is_legacy or is_current):
        issues.append(f"迁移清单 schema 不受支持: {sorted(keys)}")

    manifest_vault = payload.get("vault")
    try:
        manifest_vault_path = Path(manifest_vault).resolve()
    except (TypeError, ValueError, OSError):
        manifest_vault_path = None
    if manifest_vault_path != vault:
        issues.append(
            f"迁移清单 vault 不匹配: {manifest_vault!r} != {str(vault)!r}"
        )
    try:
        datetime.fromisoformat(payload.get("created_at"))
    except (TypeError, ValueError):
        issues.append("迁移清单 created_at 无效")

    if is_current:
        if payload.get("schema_version") != 2:
            issues.append("迁移清单 schema_version 必须为 2")
        migration_result = payload.get("migration_result")
        link_result = payload.get("link_check_result")
        if migration_result not in ("pending", "completed", "failed"):
            issues.append("迁移清单 migration_result 无效")
        if not isinstance(link_result, dict) or set(link_result) != {
            "result",
            "issues",
            "markdown_links_checked",
            "image_links_checked",
            "wiki_links_checked",
        }:
            issues.append("迁移清单 link_check_result schema 无效")
        elif completed:
            if migration_result != "completed":
                issues.append("迁移清单未记录完成迁移")
            if link_result.get("result") != "passed":
                issues.append("迁移清单未记录链接检查通过")
            for key in (
                "issues",
                "markdown_links_checked",
                "image_links_checked",
                "wiki_links_checked",
            ):
                if not isinstance(link_result.get(key), int) or link_result[key] < 0:
                    issues.append(f"迁移清单 link_check_result.{key} 无效")

    files = payload.get("files")
    if not isinstance(files, list) or not files:
        issues.append("迁移清单 files 必须是非空数组")
        return payload, tuple(issues)

    seen_sources = set()
    seen_destinations = set()
    for index, record in enumerate(files):
        prefix = f"迁移清单 files[{index}]"
        if not isinstance(record, dict) or set(record) != MANIFEST_FILE_KEYS:
            issues.append(f"{prefix} schema 无效")
            continue
        source = record.get("source")
        source_path, source_issue = _safe_manifest_relative(
            source,
            f"{prefix}.source",
        )
        if source_issue:
            issues.append(source_issue)
        elif source_path.parts[0] not in OLD_DIRECTORIES:
            issues.append(f"{prefix}.source 不属于白名单旧目录: {source}")
        elif source in seen_sources:
            issues.append(f"迁移清单包含重复来源: {source}")
        else:
            seen_sources.add(source)

        destination = record.get("destination")
        if destination is not None:
            _, destination_issue = _safe_manifest_relative(
                destination,
                f"{prefix}.destination",
            )
            if destination_issue:
                issues.append(destination_issue)
            elif destination in seen_destinations:
                issues.append(f"迁移清单包含重复目标: {destination}")
            else:
                seen_destinations.add(destination)
        if source_path is not None:
            expected = expected_destination_for_source(source)
            if destination != expected:
                issues.append(
                    f"{prefix}.destination 与迁移映射不一致: "
                    f"{destination!r} != {expected!r}"
                )
        if not isinstance(record.get("size"), int) or record["size"] < 0:
            issues.append(f"{prefix}.size 无效")
        if not isinstance(record.get("sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}",
            record["sha256"],
        ):
            issues.append(f"{prefix}.sha256 无效")
        if not isinstance(record.get("preserve_hash"), bool):
            issues.append(f"{prefix}.preserve_hash 无效")
        elif isinstance(source, str):
            expected_preserve_hash = not source.lower().endswith(".md")
            if record["preserve_hash"] != expected_preserve_hash:
                issues.append(f"{prefix}.preserve_hash 与文件类型不一致")
    return payload, tuple(issues)


def inspect_backup(
    backup_path: Path,
) -> tuple[dict[str, tuple[int, str]], tuple[str, ...]]:
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        return {}, (f"迁移记录不是普通文件: {backup_path.name}",)
    files = {}
    issues = []
    seen_names = set()
    try:
        with zipfile.ZipFile(backup_path) as archive:
            for info in archive.infolist():
                name = info.filename
                if name in seen_names:
                    issues.append(f"ZIP 包含重复条目: {name}")
                    continue
                seen_names.add(name)
                normalized = name.rstrip("/")
                relative, path_issue = _safe_manifest_relative(
                    normalized,
                    "ZIP 条目",
                )
                if path_issue:
                    issues.append(path_issue)
                    continue
                if relative.parts[0] not in OLD_DIRECTORIES:
                    issues.append(f"ZIP 条目不属于白名单旧目录: {name}")
                    continue
                if info.is_dir():
                    continue
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                files[name] = (info.file_size, digest.hexdigest())
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        return {}, (f"迁移 ZIP 无效: {exc}",)
    return files, tuple(issues)


def validate_manifest_and_backup(
    vault: Path,
    manifest_path: Path,
    backup_path: Path,
    *,
    completed: bool,
) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    payload, manifest_issues = load_manifest_strict(
        vault,
        manifest_path,
        completed=completed,
    )
    backup_files, backup_issues = inspect_backup(backup_path)
    issues = [*manifest_issues, *backup_issues]
    if payload is None or not isinstance(payload.get("files"), list):
        return payload, tuple(issues)

    manifest_files = {
        record["source"]: (record["size"], record["sha256"])
        for record in payload["files"]
        if isinstance(record, dict)
        and set(record) == MANIFEST_FILE_KEYS
        and isinstance(record.get("source"), str)
        and isinstance(record.get("size"), int)
        and isinstance(record.get("sha256"), str)
    }
    if set(manifest_files) != set(backup_files):
        missing = sorted(set(manifest_files) - set(backup_files))
        extra = sorted(set(backup_files) - set(manifest_files))
        if missing:
            issues.append(f"ZIP 缺少清单来源: {missing}")
        if extra:
            issues.append(f"ZIP 包含清单外来源，清单不完整: {extra}")
    for source in sorted(set(manifest_files) & set(backup_files)):
        if manifest_files[source] != backup_files[source]:
            issues.append(f"ZIP 与清单的大小或 SHA-256 不一致: {source}")
    return payload, tuple(issues)


def validate_source_snapshot(
    plan: MigrationPlan,
    manifest_path: Path,
    backup_path: Path,
) -> tuple[str, ...]:
    payload, issues = validate_manifest_and_backup(
        plan.vault,
        manifest_path,
        backup_path,
        completed=False,
    )
    issue_list = list(issues)
    if payload is None or not isinstance(payload.get("files"), list):
        return tuple(issue_list)
    for old_directory in plan.old_directories:
        if not old_directory.is_dir():
            issue_list.append(f"迁移源目录不完整: {old_directory.name}")
    expected = {
        record["source"]: (record["size"], record["sha256"])
        for record in payload["files"]
        if isinstance(record, dict) and set(record) == MANIFEST_FILE_KEYS
    }
    actual = {
        path.relative_to(plan.vault).as_posix(): (
            path.stat().st_size,
            sha256_file(path),
        )
        for path in iter_old_files(plan)
    }
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            issue_list.append(f"当前迁移源缺少清单文件: {missing}")
        if extra:
            issue_list.append(f"当前迁移源包含快照后文件: {extra}")
    for source in sorted(set(actual) & set(expected)):
        if actual[source] != expected[source]:
            issue_list.append(f"当前迁移源与清单/ZIP 不一致: {source}")
    return tuple(issue_list)


def assert_source_snapshot_consistent(
    plan: MigrationPlan,
    manifest_path: Path,
    backup_path: Path,
):
    issues = validate_source_snapshot(plan, manifest_path, backup_path)
    if issues:
        raise RuntimeError(
            "迁移源、清单与 ZIP 快照不一致，保留全部旧目录:\n"
            + "\n".join(issues)
        )


def ensure_target_structure(plan: MigrationPlan):
    vault = plan.vault
    fixed_directories = (
        "01_收件箱",
        "10_项目",
        "20_知识笔记",
        "30_精选资料",
        "80_系统/模板",
        "80_系统/Bases",
        "80_系统/知识库治理/审核队列",
        "80_系统/知识库治理/审核日志",
        "80_系统/知识库治理/变更快照",
        "80_系统/迁移记录",
        "90_归档",
        "99_废纸篓",
    )
    for relative in fixed_directories:
        (vault / relative).mkdir(parents=True, exist_ok=True)
    for domain in DOMAINS:
        (vault / "20_知识笔记" / domain).mkdir(parents=True, exist_ok=True)
        (vault / "30_精选资料" / domain).mkdir(parents=True, exist_ok=True)


def render_home() -> str:
    domain_links = "\n".join(
        f"- [[30_精选资料/{domain}/目录索引|{domain}]]"
        for domain in MANAGED_DOMAINS
    )
    return f"""---
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

{domain_links}

## 系统

- [[80_系统/知识库治理/管理规则|管理规则]]
- [[80_系统/知识库治理/主题词表|主题词表]]
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
> `30_精选资料`，其余过程材料进入 `90_归档`。
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
            relative = path.relative_to(root).as_posix()
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
| CS_IT | 信息技术 | domain |
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
        destination = plan.vault / "80_系统" / "模板" / destination_name
        write_expected_text(
            destination,
            source.read_text(encoding="utf-8"),
        )


def copy_mapped_content(plan: MigrationPlan):
    old_ai = plan.vault / "AI相关知识库"
    if not old_ai.exists():
        return
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
        plan.vault / "20_知识笔记" / "信息技术" / CODEX_FILENAME
    )
    with codex_source.open("r", encoding="utf-8", newline="") as stream:
        codex_original = stream.read()
    codex_expected = merge_frontmatter(
        codex_original,
        {
            "type": "知识",
            "domain": "信息技术",
            "status": "常青",
            "created": "2026-07-04",
            "tags": [],
            "review_status": "human-approved",
            "llm_policy": "standard",
        },
    )
    write_expected_text(codex_destination, codex_expected)


def copy_lifecycle_content(plan: MigrationPlan):
    for old_name in LEGACY_LIFECYCLE_MAPPINGS:
        source_root = plan.vault / old_name
        if not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*")):
            destination = destination_for_source(plan, source)
            if destination is None:
                continue
            if source.is_dir():
                if destination.exists() and not destination.is_dir():
                    raise FileExistsError(
                        f"目标已存在且不是目录: {destination}"
                    )
                destination.mkdir(parents=True, exist_ok=True)
            elif source.is_file():
                expected = expected_migration_bytes(plan, source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if not destination.is_file():
                        raise FileExistsError(
                            f"目标已存在且不是文件: {destination}"
                        )
                    if destination.read_bytes() == expected:
                        continue
                    raise FileExistsError(
                        f"目标已存在且内容不同: {destination}"
                    )
                destination.write_bytes(expected)


def apply_copy_phase(plan: MigrationPlan):
    ensure_target_structure(plan)
    copy_lifecycle_content(plan)
    copy_mapped_content(plan)
    install_templates(plan)
    write_vault_documents(plan)


def write_vault_documents(plan: MigrationPlan):
    vault = plan.vault
    documents = {
        vault / "00_首页.md": render_home(),
        vault / "10_项目" / "目录索引.md": render_project_index(),
        vault / "20_知识笔记" / "知识地图.md": render_knowledge_map(),
        vault / "80_系统" / "知识库治理" / "管理规则.md": render_management_rules(),
        vault / "80_系统" / "知识库治理" / "主题词表.md": render_topic_vocabulary(),
        vault / "80_系统" / "知识库治理" / "别名词典.md": render_alias_dictionary(),
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
    manifest, manifest_issues = load_manifest_strict(
        vault,
        manifest_path,
        completed=False,
    )
    issues = list(manifest_issues)
    required_files = [
        vault / "00_首页.md",
        vault / "10_项目" / "目录索引.md",
        vault / "20_知识笔记" / "目录索引.md",
        vault / "20_知识笔记" / "知识地图.md",
        vault / "80_系统" / "知识库治理" / "管理规则.md",
        vault / "80_系统" / "知识库治理" / "主题词表.md",
        vault / "80_系统" / "知识库治理" / "别名词典.md",
    ]
    required_files.extend(
        vault / "30_精选资料" / domain / "目录索引.md"
        for domain in DOMAINS
    )
    for path in required_files:
        if not path.is_file():
            issues.append(f"缺少必需路径: {path}")
    required_directories = [
        vault / "01_收件箱",
        vault / "10_项目",
        vault / "20_知识笔记",
        vault / "30_精选资料",
        vault / "80_系统",
        vault / "90_归档",
        vault / "99_废纸篓",
    ]
    for path in required_directories:
        if not path.is_dir():
            issues.append(f"缺少必需目录: {path}")

    records = (
        manifest.get("files", [])
        if isinstance(manifest, dict)
        and isinstance(manifest.get("files"), list)
        else []
    )
    for record in records:
        if not isinstance(record, dict) or set(record) != MANIFEST_FILE_KEYS:
            continue
        destination_text = record.get("destination")
        if destination_text is None:
            continue
        _, destination_issue = _safe_manifest_relative(
            destination_text,
            "迁移目标",
        )
        if destination_issue:
            continue
        destination = (vault / Path(destination_text)).resolve()
        if not _inside_vault(vault, destination):
            issues.append(f"迁移目标越出 vault: {destination_text}")
        elif not destination.is_file():
            issues.append(f"缺少迁移目标: {destination_text}")
        elif (
            record.get("preserve_hash")
            and sha256_file(destination) != record.get("sha256")
        ):
            issues.append(f"二进制文件哈希不一致: {destination_text}")

    issues.extend(
        f"{issue.source}: {issue.target}: {issue.reason}"
        for issue in scan_local_links(vault)
    )

    for markdown_path in iter_managed_markdown(vault):
        relative = markdown_path.relative_to(vault)
        if relative.parts[:2] == ("80_系统", "迁移记录"):
            continue
        text = markdown_path.read_text(encoding="utf-8")
        for old_name in LEGACY_CONTENT_DIRECTORIES:
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
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("source"), str)
            and record["source"].lower().endswith(".md")
        ),
        local_links_checked=count_local_markdown_links(vault),
        image_links_checked=count_markdown_images(vault),
        wiki_links_checked=count_wikilinks(vault),
    )


def render_link_report(
    report: ValidationReport,
    *,
    include_wikilinks: bool,
) -> str:
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
    ]
    if include_wikilinks:
        lines.append(f"- 检查的 WikiLink：{report.wiki_links_checked}")
    lines.extend(["", "## 问题", "", *issue_lines, ""])
    return "\n".join(lines)


def write_link_report(report: ValidationReport, path: Path) -> Path:
    path.write_text(
        render_link_report(report, include_wikilinks=True),
        encoding="utf-8",
    )
    return path


def render_migration_summary(
    vault: Path,
    report: ValidationReport,
    *,
    executed_at: str,
    old_directories_removed: bool,
    include_lifecycle_mappings: bool = True,
) -> str:
    lines = [
        "# Obsidian vault 迁移说明",
        "",
        f"- 执行时间：{executed_at}",
        f"- vault：`{vault}`",
        f"- 验证结果：{'通过' if report.passed else '失败'}",
        f"- 旧目录已清理：{'是' if old_directories_removed else '否'}",
        "- 快照：`2026-07-27-迁移前备份.zip`",
        "- 清单：`2026-07-27-文件清单.json`",
        "- 链接报告：`2026-07-27-链接检查.md`",
        "",
        "## 路径映射",
        "",
    ]
    mappings = [
        (
            Path("AI相关知识库"),
            Path("30_精选资料") / "AI",
        ),
        (
            Path("Quant相关知识库") / QUANT_FILENAME,
            Path("30_精选资料") / "Quant" / "2026年06月" / QUANT_FILENAME,
        ),
        (
            Path("HYXX个人知识库") / CODEX_FILENAME,
            Path("20_知识笔记") / "信息技术" / CODEX_FILENAME,
        ),
    ]
    if include_lifecycle_mappings:
        mappings.extend(
            (
                (Path("90_系统"), Path("80_系统")),
                (Path("99_归档"), Path("90_归档")),
            )
        )
    for source, destination in mappings:
        lines.append(
            f"- `{source}` → `{destination}`"
        )
    lines.append("")
    return "\n".join(lines)


def write_migration_summary(
    plan: MigrationPlan,
    report: ValidationReport,
    path: Path,
    old_directories_removed: bool,
) -> Path:
    path.write_text(
        render_migration_summary(
            plan.vault,
            report,
            executed_at=datetime.now().astimezone().isoformat(),
            old_directories_removed=old_directories_removed,
        ),
        encoding="utf-8",
    )
    return path


def retry_readonly_removal(function, path, exception):
    if not isinstance(exception, PermissionError):
        raise exception
    target = Path(path)
    target.chmod(target.stat().st_mode | stat.S_IWRITE)
    function(path)


def restore_old_directories_from_backup(
    plan: MigrationPlan,
    manifest_path: Path,
    backup_path: Path,
):
    payload, issues = validate_manifest_and_backup(
        plan.vault,
        manifest_path,
        backup_path,
        completed=False,
    )
    if issues or payload is None:
        raise RuntimeError(
            "清理失败后无法验证恢复源:\n" + "\n".join(issues)
        )
    with zipfile.ZipFile(backup_path) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename.rstrip("/"))
            destination = plan.vault.joinpath(*relative.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not destination.is_file():
                raise RuntimeError(f"恢复目标不是普通文件: {destination}")
            if destination.is_file():
                destination.chmod(destination.stat().st_mode | stat.S_IWRITE)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    restored_issues = validate_source_snapshot(
        plan,
        manifest_path,
        backup_path,
    )
    if restored_issues:
        raise RuntimeError(
            "清理失败后的自动恢复不完整:\n" + "\n".join(restored_issues)
        )


def cleanup_old_directories(
    plan: MigrationPlan,
    report: ValidationReport,
):
    if not report.passed:
        raise RuntimeError("迁移验证未通过，保留全部旧目录")
    record_paths = migration_record_paths(plan.vault, plan)
    backup = record_paths["backup"]
    manifest = record_paths["manifest"]
    link_report = record_paths["link_report"]
    required_records = (backup, manifest, link_report)
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
    assert_source_snapshot_consistent(plan, manifest, backup)
    try:
        for old_directory in plan.old_directories:
            shutil.rmtree(old_directory, onexc=retry_readonly_removal)
    except Exception:
        restore_old_directories_from_backup(plan, manifest, backup)
        raise


def verify_completed_vault(vault: Path) -> ValidationReport:
    vault = assert_vault(vault)
    record_paths = migration_record_paths(vault)
    issues = [
        f"迁移记录不是普通文件: {path.name}"
        for path in record_paths.values()
        if not path.is_file()
    ]
    report = validate_migration(vault, record_paths["manifest"])
    issues.extend(report.issues)
    manifest, strict_issues = validate_manifest_and_backup(
        vault,
        record_paths["manifest"],
        record_paths["backup"],
        completed=True,
    )
    issues.extend(strict_issues)

    is_current_manifest = (
        isinstance(manifest, dict)
        and set(manifest) == CURRENT_MANIFEST_KEYS
    )
    if is_current_manifest:
        link_result = manifest.get("link_check_result")
        expected_link_result = {
            "result": "passed" if report.passed else "failed",
            "issues": len(report.issues),
            "markdown_links_checked": report.local_links_checked,
            "image_links_checked": report.image_links_checked,
            "wiki_links_checked": report.wiki_links_checked,
        }
        if link_result != expected_link_result:
            issues.append("迁移清单记录的链接检查结果与重新计算结果不一致")

    link_report_path = record_paths["link_report"]
    if link_report_path.is_file():
        try:
            actual_link_report = link_report_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"链接检查报告无法读取: {exc}")
        else:
            expected_link_report = render_link_report(
                report,
                include_wikilinks=is_current_manifest,
            )
            if actual_link_report != expected_link_report:
                issues.append("链接检查报告与重新计算结果不一致")

    summary_path = record_paths["summary"]
    if summary_path.is_file():
        try:
            actual_summary = summary_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"迁移说明无法读取: {exc}")
        else:
            match = re.search(
                r"(?m)^- 执行时间：(.+)$",
                actual_summary,
            )
            if match is None:
                issues.append("迁移说明缺少执行时间")
            else:
                executed_at = match.group(1)
                try:
                    datetime.fromisoformat(executed_at)
                except ValueError:
                    issues.append("迁移说明执行时间无效")
                expected_summary = render_migration_summary(
                    vault,
                    report,
                    executed_at=executed_at,
                    old_directories_removed=True,
                )
                legacy_summary = render_migration_summary(
                    vault,
                    report,
                    executed_at=executed_at,
                    old_directories_removed=True,
                    include_lifecycle_mappings=False,
                )
                if actual_summary not in (expected_summary, legacy_summary):
                    issues.append("迁移说明与当前 vault 验证结果不一致")

    issues.extend(
        f"旧目录仍存在: {name}"
        for name in OLD_DIRECTORIES
        if (vault / name).exists()
    )
    return ValidationReport(
        passed=not issues,
        issues=tuple(issues),
        markdown_files_before=report.markdown_files_before,
        local_links_checked=report.local_links_checked,
        image_links_checked=report.image_links_checked,
        wiki_links_checked=report.wiki_links_checked,
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
    parser.add_argument("--vault", type=Path)
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
    try:
        args.vault = load_vault_root(args.vault)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.verify:
        report = verify_completed_vault(args.vault)
        if not report.passed:
            for issue in report.issues:
                print(f"验证失败: {issue}", file=sys.stderr)
        return 0 if report.passed else 1
    if args.apply and args.confirm != CONFIRMATION:
        print(
            f"--apply 必须同时提供 --confirm {CONFIRMATION}",
            file=sys.stderr,
        )
        return 2
    plan = build_migration_plan(args.vault)
    if args.apply:
        state_paths = VaultStatePaths.for_vault(args.vault)
        with runtime_write_lock(state_paths, "restructure-vault"):
            migrate_legacy_state(state_paths, REPO_ROOT / ".state")
            if not plan.old_directories:
                report = verify_completed_vault(plan.vault)
                if not report.passed:
                    for issue in report.issues:
                        print(f"验证失败: {issue}", file=sys.stderr)
                return 0 if report.passed else 1
            conflicts = find_migration_conflicts(plan)
            if conflicts:
                for conflict in conflicts:
                    print(f"迁移冲突: {conflict}", file=sys.stderr)
                return 1
            record_paths = migration_record_paths(plan.vault, plan)
            backup = record_paths["backup"]
            manifest = record_paths["manifest"]
            link_report_path = record_paths["link_report"]
            summary_path = record_paths["summary"]

            create_backup(plan, backup)
            write_manifest(plan, manifest)
            assert_source_snapshot_consistent(plan, manifest, backup)
            apply_copy_phase(plan)
            report = validate_migration(plan.vault, manifest)
            write_link_report(report, link_report_path)
            record_manifest_results(manifest, report)
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
