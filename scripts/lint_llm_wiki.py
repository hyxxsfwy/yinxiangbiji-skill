from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.domain_taxonomy import MANAGED_DOMAINS
from scripts.restructure_obsidian_vault import (
    iter_markdown_references,
    resolve_wikilink,
    split_frontmatter,
)
from scripts.runtime import load_vault_root
from scripts.vault_state import require_path_within_vault


REQUIRED_PATHS = (
    Path("AGENTS.md"),
    Path("20_知识笔记"),
    Path("30_精选资料"),
    Path("80_系统/知识库治理"),
)
ALLOWED_TYPES = {"资料", "知识", "索引", "模板"}
ALLOWED_STATUS = {"待提炼", "常青"}
ALLOWED_REVIEW_STATUS = {"pending", "human-approved"}
ALLOWED_LLM_POLICY = {"standard", "strict", "off"}
AUTO_START = "<!-- llmwiki:auto:start -->"
AUTO_END = "<!-- llmwiki:auto:end -->"
KNOWLEDGE_MAP_PATH = Path("20_知识笔记/知识地图.md")
KNOWLEDGE_INDEX_PATH = Path("20_知识笔记/目录索引.md")
LOG_PATH = Path("80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md")
LOG_ENTRY_RE = re.compile(
    r"(?m)^## \[(?P<timestamp>[^\]]+)\] (?P<operation>ingest|query|lint)$"
)
LOG_HEADING_RE = re.compile(r"(?m)^##(?: .*)?$")
LOG_REQUIRED_FIELDS = (
    "input",
    "read_scope",
    "proposed_writes",
    "actual_writes",
    "review_status",
    "issues",
)


@dataclass(frozen=True)
class LintIssue:
    code: str
    severity: str
    path: str
    detail: str
    fixable: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "detail": self.detail,
            "fixable": self.fixable,
        }


@dataclass(frozen=True)
class LintReport:
    vault: Path
    checked_at: datetime
    checked_files: int
    issues: tuple[LintIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.issues)

    def to_dict(self) -> dict[str, object]:
        counts = {"error": 0, "warning": 0, "manual_review": 0}
        for item in self.issues:
            counts[item.severity] += 1
        return {
            "ok": self.ok,
            "vault": str(self.vault),
            "checked_at": self.checked_at.isoformat(),
            "checked_files": self.checked_files,
            "summary": counts,
            "issues": [item.to_dict() for item in self.issues],
        }


def _relative(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def _managed_documents(vault: Path) -> tuple[Path, ...]:
    roots = (vault / "20_知识笔记", vault / "30_精选资料")
    documents = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            resolved = require_path_within_vault(
                path,
                vault,
                "Lint 扫描文件",
                allowed_root=root,
            )
            if resolved.is_file():
                documents.append(resolved)
    return tuple(sorted(set(documents)))


def _frontmatter_source_targets(fields: dict[str, object]) -> tuple[str, ...]:
    value = fields.get("sources", [])
    if not isinstance(value, list):
        return ()
    targets = []
    for item in value:
        if not isinstance(item, str):
            continue
        match = re.fullmatch(r"\[\[(.+?)\]\]", item.strip())
        if match:
            targets.append(match.group(1))
    return tuple(targets)


def _body_wikilink_targets(markdown: str) -> tuple[str, ...]:
    return tuple(
        reference.target
        for reference in iter_markdown_references(markdown)
        if reference.is_wikilink and not reference.is_image
    )


def _normalized_wikilink_target(raw: str) -> str:
    without_alias = raw.split("|", 1)[0].strip()
    return re.split(r"[#^]", without_alias, maxsplit=1)[0].strip()


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _link_issue(
    vault: Path,
    source: Path,
    raw_target: str,
    reason: str,
) -> LintIssue:
    code = "AMBIGUOUS_WIKILINK" if reason == "目标不唯一" else "BROKEN_WIKILINK"
    return LintIssue(
        code,
        "error",
        _relative(vault, source),
        f"Wikilink {raw_target!r}: {reason}",
    )


def _auto_region_valid(markdown: str) -> bool:
    return (
        markdown.count(AUTO_START) == 1
        and markdown.count(AUTO_END) == 1
        and markdown.index(AUTO_START) < markdown.index(AUTO_END)
    )


def _indexed_targets(
    vault: Path,
    index_path: Path,
    markdown: str,
) -> set[Path]:
    targets = set()
    for raw in _body_wikilink_targets(markdown):
        target, reason = resolve_wikilink(
            vault,
            index_path,
            _normalized_wikilink_target(raw),
        )
        if target is not None and reason is None:
            targets.add(target)
    return targets


def _drift_detail(vault: Path, missing: set[Path], unexpected: set[Path]) -> str:
    parts = []
    if missing:
        paths = ", ".join(sorted(_relative(vault, path) for path in missing))
        parts.append(f"遗漏: {paths}")
    if unexpected:
        paths = ", ".join(sorted(_relative(vault, path) for path in unexpected))
        parts.append(f"越界: {paths}")
    return "; ".join(parts)


def _index_targets_from_file(vault: Path, index_path: Path) -> set[Path]:
    if not index_path.is_file():
        return set()
    _, markdown = split_frontmatter(index_path.read_text(encoding="utf-8"))
    return _indexed_targets(vault, index_path, markdown)


def _index_drift_issue(
    vault: Path,
    index_path: Path,
    expected: set[Path],
) -> LintIssue | None:
    try:
        actual = _index_targets_from_file(vault, index_path)
    except (OSError, UnicodeError, ValueError):
        actual = set()
    missing = expected - actual
    unexpected = actual - expected
    if not missing and not unexpected:
        return None
    return LintIssue(
        "INDEX_DRIFT",
        "error",
        _relative(vault, index_path),
        _drift_detail(vault, missing, unexpected),
    )


def _index_drift_issues(
    vault: Path,
    documents: tuple[Path, ...],
    document_cache: dict[Path, tuple[dict[str, object], str]],
) -> tuple[LintIssue, ...]:
    issues = []
    knowledge_root = (vault / "20_知识笔记").resolve()
    selected_root = (vault / "30_精选资料").resolve()
    expected_knowledge = {
        path
        for path in document_cache
        if _is_within(knowledge_root, path)
        and document_cache[path][0].get("type") == "知识"
    }
    knowledge_index = vault / KNOWLEDGE_INDEX_PATH
    issue = _index_drift_issue(vault, knowledge_index, expected_knowledge)
    if issue is not None:
        issues.append(issue)

    expected_by_domain: dict[str, set[Path]] = {}
    domain_names = set()
    for path in document_cache:
        if not _is_within(selected_root, path):
            continue
        relative = path.relative_to(selected_root)
        if len(relative.parts) < 2:
            continue
        domain = relative.parts[0]
        if document_cache[path][0].get("type") == "资料":
            expected_by_domain.setdefault(domain, set()).add(path)
            domain_names.add(domain)
    for path in documents:
        if (
            path.name == "目录索引.md"
            and path.parent.parent == selected_root
        ):
            domain_names.add(path.parent.name)
    for domain in sorted(domain_names):
        index_path = vault / "30_精选资料" / domain / "目录索引.md"
        issue = _index_drift_issue(
            vault,
            index_path,
            expected_by_domain.get(domain, set()),
        )
        if issue is not None:
            issues.append(issue)
    return tuple(issues)


def _invalid_log_issue(vault: Path, detail: str) -> LintIssue:
    return LintIssue(
        "INVALID_LOG_ENTRY",
        "warning",
        LOG_PATH.as_posix(),
        detail,
    )


def _log_issues(vault: Path) -> tuple[LintIssue, ...]:
    log_path = require_path_within_vault(
        vault / LOG_PATH,
        vault,
        "LLM Wiki 操作日志",
        allowed_root=vault / "80_系统/知识库治理",
    )
    if not log_path.is_file():
        return (_invalid_log_issue(vault, "日志文件不存在"),)
    try:
        markdown = log_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return (_invalid_log_issue(vault, f"日志文件无法读取: {exc}"),)

    issues = []
    headings = tuple(LOG_HEADING_RE.finditer(markdown))
    previous_timestamp: datetime | None = None
    for position, heading in enumerate(headings):
        title = heading.group(0)
        match = LOG_ENTRY_RE.fullmatch(title)
        entry_number = position + 1
        if match is None:
            issues.append(
                _invalid_log_issue(vault, f"第 {entry_number} 个二级标题格式无效")
            )
        else:
            raw_timestamp = match.group("timestamp")
            try:
                timestamp = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                issues.append(
                    _invalid_log_issue(
                        vault,
                        f"第 {entry_number} 个条目时间戳无效: {raw_timestamp}",
                    )
                )
            else:
                if previous_timestamp is not None:
                    timezone_mismatch = (
                        timestamp.utcoffset()
                        != previous_timestamp.utcoffset()
                    )
                    if timezone_mismatch:
                        issues.append(
                            _invalid_log_issue(
                                vault,
                                f"第 {entry_number} 个条目与上一条时间戳时区不一致",
                            )
                        )
                    elif timestamp < previous_timestamp:
                        issues.append(
                            _invalid_log_issue(
                                vault,
                                f"第 {entry_number} 个条目时间顺序倒退: {raw_timestamp}",
                            )
                        )
                previous_timestamp = timestamp

        block_end = (
            headings[position + 1].start()
            if position + 1 < len(headings)
            else len(markdown)
        )
        block = markdown[heading.end():block_end]
        missing_fields = [
            field
            for field in LOG_REQUIRED_FIELDS
            if re.search(rf"(?m)^- {re.escape(field)}:", block) is None
        ]
        if missing_fields:
            issues.append(
                _invalid_log_issue(
                    vault,
                    f"第 {entry_number} 个条目缺少字段: {', '.join(missing_fields)}",
                )
            )
    return tuple(issues)


def lint_vault(
    vault: Path,
    *,
    checked_at: datetime | None = None,
) -> LintReport:
    vault = load_vault_root(explicit=vault)
    issues: list[LintIssue] = []
    for required in REQUIRED_PATHS:
        target = vault / required
        is_schema = required == Path("AGENTS.md")
        valid = target.is_file() if is_schema else target.is_dir()
        if not valid:
            if is_schema:
                code = "MISSING_SCHEMA"
            else:
                code = "MISSING_REQUIRED_DIRECTORY"
            issues.append(
                LintIssue(
                    code,
                    "error",
                    required.as_posix(),
                    "必需路径不存在",
                )
            )
    documents = _managed_documents(vault)
    document_cache: dict[Path, tuple[dict[str, object], str]] = {}
    semantic_paths: set[Path] = set()
    allowed_values = {
        "type": ALLOWED_TYPES,
        "domain": set(MANAGED_DOMAINS),
        "status": ALLOWED_STATUS,
        "review_status": ALLOWED_REVIEW_STATUS,
        "llm_policy": ALLOWED_LLM_POLICY,
    }
    for path in documents:
        try:
            fields, markdown = split_frontmatter(path.read_text(encoding="utf-8"))
            if not fields:
                raise ValueError("缺少 Frontmatter")
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(
                LintIssue(
                    "INVALID_FRONTMATTER",
                    "error",
                    _relative(vault, path),
                    str(exc),
                )
            )
            continue
        document_cache[path] = (fields, markdown)
        properties_valid = True
        for name, values in allowed_values.items():
            value = fields.get(name, "")
            if name == "domain" and fields.get("type") == "索引" and value == "":
                continue
            if not isinstance(value, str) or value not in values:
                properties_valid = False
                issues.append(
                    LintIssue(
                        "INVALID_PROPERTY_VALUE",
                        "error",
                        _relative(vault, path),
                        f"{name}={value!r} 不在允许值中",
                    )
                )
        if properties_valid:
            semantic_paths.add(path)

    selected_root = (vault / "30_精选资料").resolve()
    knowledge_root = (vault / "20_知识笔记").resolve()
    inbound_paths: set[Path] = set()
    for path in documents:
        if path not in semantic_paths:
            continue
        fields, markdown = document_cache[path]
        valid_sources: set[Path] = set()
        for raw_target in _frontmatter_source_targets(fields):
            target = _normalized_wikilink_target(raw_target)
            if not target:
                continue
            resolved, reason = resolve_wikilink(vault, path, target)
            if reason:
                issues.append(_link_issue(vault, path, raw_target, reason))
            elif resolved is not None and _is_within(selected_root, resolved):
                valid_sources.add(resolved)

        is_knowledge_note = (
            fields.get("type") == "知识"
            and _is_within(knowledge_root, path)
            and path.name not in {"目录索引.md", "知识地图.md"}
        )
        if is_knowledge_note and not valid_sources:
            issues.append(
                LintIssue(
                    "MISSING_SOURCE",
                    "error",
                    _relative(vault, path),
                    "知识笔记至少需要一个可解析到 30_精选资料 的 sources 项",
                )
            )
        if (
            is_knowledge_note
            and fields.get("knowledge_kind") == "对比"
            and len(valid_sources) < 2
        ):
            issues.append(
                LintIssue(
                    "INSUFFICIENT_COMPARISON_SOURCES",
                    "error",
                    _relative(vault, path),
                    "对比笔记至少需要两个不同且有效的精选资料来源",
                )
            )

        for raw_target in _body_wikilink_targets(markdown):
            target = _normalized_wikilink_target(raw_target)
            if not target:
                continue
            resolved, reason = resolve_wikilink(vault, path, target)
            if reason:
                issues.append(_link_issue(vault, path, raw_target, reason))
            elif resolved is not None:
                inbound_paths.add(resolved)

    for path in documents:
        if path not in semantic_paths:
            continue
        fields, _ = document_cache[path]
        is_knowledge_note = (
            fields.get("type") == "知识"
            and _is_within(knowledge_root, path)
            and path.name not in {"目录索引.md", "知识地图.md"}
        )
        if is_knowledge_note and path not in inbound_paths:
            issues.append(
                LintIssue(
                    "ORPHAN_KNOWLEDGE_NOTE",
                    "warning",
                    _relative(vault, path),
                    "没有其他正文 Wikilink 指向该知识笔记",
                )
            )
    knowledge_map = require_path_within_vault(
        vault / KNOWLEDGE_MAP_PATH,
        vault,
        "知识地图",
        allowed_root=vault / "20_知识笔记",
    )
    try:
        knowledge_map_markdown = knowledge_map.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        knowledge_map_markdown = ""
    if not _auto_region_valid(knowledge_map_markdown):
        issues.append(
            LintIssue(
                "INVALID_AUTO_REGION",
                "error",
                KNOWLEDGE_MAP_PATH.as_posix(),
                "自动区必须且只能包含一对有序的 llmwiki 标记",
            )
        )
    issues.extend(
        _index_drift_issues(
            vault,
            documents,
            document_cache,
        )
    )
    issues.extend(_log_issues(vault))
    return LintReport(
        vault=vault,
        checked_at=checked_at or datetime.now(timezone.utc),
        checked_files=len(documents),
        issues=tuple(issues),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读检查 Obsidian LLM Wiki")
    parser.add_argument("--vault")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def _render_text(report: LintReport) -> str:
    lines = [
        f"ok: {str(report.ok).lower()}",
        f"checked_files: {report.checked_files}",
    ]
    lines.extend(
        f"[{item.severity}] {item.code} {item.path}: {item.detail}"
        for item in report.issues
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = lint_vault(load_vault_root(explicit=args.vault))
    except (OSError, ValueError) as exc:
        print(f"配置错误: {exc}")
        return 2
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
