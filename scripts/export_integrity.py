#!/usr/bin/env python3
"""精选资料导出后的索引、附件、范围和重复项验收。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import unquote

try:
    from .knowledge_base import (
        INDEX_FILENAME,
        _split_frontmatter,
        extract_note_metadata,
    )
    from .restructure_obsidian_vault import iter_markdown_references
except ImportError:
    from knowledge_base import (
        INDEX_FILENAME,
        _split_frontmatter,
        extract_note_metadata,
    )
    from restructure_obsidian_vault import iter_markdown_references


INDEX_POSITION = re.compile(r"^\s+- 位置：`([^`]+)`\s*$", re.MULTILINE)
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "data:", "evernote:")


@dataclass(frozen=True)
class IntegrityIssue:
    kind: str
    domain: str
    source: Path
    detail: str

    def to_dict(self):
        return {
            "kind": self.kind,
            "domain": self.domain,
            "source": self.source.as_posix(),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DomainIntegrity:
    domain: str
    total_articles: int
    in_range_articles: int
    index_entries: int
    image_references: int
    issues: tuple[IntegrityIssue, ...]

    def to_dict(self):
        return {
            "total_articles": self.total_articles,
            "in_range_articles": self.in_range_articles,
            "index_entries": self.index_entries,
            "image_references": self.image_references,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class ExportIntegrityReport:
    domains: dict[str, DomainIntegrity]
    cross_domain_guid_duplicates: dict[str, tuple[str, ...]]
    cross_domain_title_duplicates: dict[str, tuple[str, ...]]

    @property
    def ok(self):
        return (
            all(not item.issues for item in self.domains.values())
            and not self.cross_domain_guid_duplicates
            and not self.cross_domain_title_duplicates
        )

    def to_dict(self):
        return {
            "ok": self.ok,
            "domains": {
                name: item.to_dict()
                for name, item in self.domains.items()
            },
            "cross_domain_guid_duplicates": {
                key: list(paths)
                for key, paths in self.cross_domain_guid_duplicates.items()
            },
            "cross_domain_title_duplicates": {
                key: list(paths)
                for key, paths in self.cross_domain_title_duplicates.items()
            },
        }


def _local_attachment_target(article_path, reference):
    raw_target = reference.target.strip()
    if not raw_target or raw_target.lower().startswith(EXTERNAL_SCHEMES):
        return None
    normalized = raw_target.replace("\\", "/")
    if not reference.is_image and "_attachments/" not in normalized:
        return None
    if reference.is_wikilink:
        raw_target = raw_target.split("|", 1)[0]
    raw_target = raw_target.split("#", 1)[0].strip().strip("<>")
    if not raw_target:
        return None
    return (article_path.parent / unquote(raw_target)).resolve()


def _scan_domain(vault, domain, since, until):
    root = vault / "30_精选资料" / domain
    issues = []
    records = []
    image_references = 0
    markdown_paths = (
        sorted(
            path
            for path in root.rglob("*.md")
            if path.name != INDEX_FILENAME
        )
        if root.is_dir()
        else []
    )

    for path in markdown_paths:
        relative = path.relative_to(root)
        try:
            markdown = path.read_text(encoding="utf-8")
            fields, _ = _split_frontmatter(markdown)
            metadata = extract_note_metadata(path)
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(
                IntegrityIssue(
                    "metadata_error",
                    domain,
                    relative,
                    str(exc),
                )
            )
            continue
        if fields.get("type") != "资料" or fields.get("domain") != domain:
            issues.append(
                IntegrityIssue(
                    "domain_mismatch",
                    domain,
                    relative,
                    "frontmatter 的 type 或 domain 与目标目录不一致",
                )
            )
            continue
        records.append((path, relative, markdown, metadata))
        for reference in iter_markdown_references(markdown):
            if reference.is_image:
                image_references += 1
            target = _local_attachment_target(path, reference)
            if target is not None and not target.is_file():
                issues.append(
                    IntegrityIssue(
                        "missing_attachment",
                        domain,
                        relative,
                        reference.target,
                    )
                )

    for field, values in (
        ("duplicate_guid", [item[3].guid for item in records]),
        ("duplicate_title", [item[3].title for item in records]),
    ):
        for value, count in Counter(values).items():
            if count > 1:
                issues.append(
                    IntegrityIssue(
                        field,
                        domain,
                        Path("."),
                        f"{value}: {count}",
                    )
                )

    expected = {item[1].as_posix() for item in records}
    index_path = root / INDEX_FILENAME
    positions = []
    if index_path.is_file():
        try:
            index_text = index_path.read_text(encoding="utf-8")
            positions = INDEX_POSITION.findall(index_text)
        except (OSError, UnicodeError) as exc:
            issues.append(
                IntegrityIssue(
                    "index_error",
                    domain,
                    Path(INDEX_FILENAME),
                    str(exc),
                )
            )
    else:
        issues.append(
            IntegrityIssue(
                "missing_index",
                domain,
                Path(INDEX_FILENAME),
                "目录索引不存在",
            )
        )

    indexed = set(positions)
    for relative in positions:
        target = root / Path(*relative.split("/"))
        if not target.is_file():
            issues.append(
                IntegrityIssue(
                    "missing_index_target",
                    domain,
                    Path(INDEX_FILENAME),
                    relative,
                )
            )
    for relative in sorted(expected - indexed):
        issues.append(
            IntegrityIssue(
                "index_missing_article",
                domain,
                Path(relative),
                "文章未进入目录索引",
            )
        )
    for relative in sorted(indexed - expected):
        if (root / Path(*relative.split("/"))).is_file():
            issues.append(
                IntegrityIssue(
                    "index_extra_article",
                    domain,
                    Path(INDEX_FILENAME),
                    relative,
                )
            )

    in_range = sum(
        1
        for _path, _relative, _markdown, metadata in records
        if since <= metadata.created < until
    )
    return (
        DomainIntegrity(
            domain=domain,
            total_articles=len(records),
            in_range_articles=in_range,
            index_entries=len(positions),
            image_references=image_references,
            issues=tuple(issues),
        ),
        records,
    )


def scan_export_integrity(vault, domains, since, until):
    """扫描声明领域并返回机器可读的硬性验收报告。"""
    vault = Path(vault).resolve()
    if not vault.is_dir():
        raise ValueError(f"Obsidian vault 不存在: {vault}")
    if not isinstance(since, datetime) or not isinstance(until, datetime):
        raise TypeError("since 和 until 必须是 datetime")
    if until <= since:
        raise ValueError("until 必须晚于 since")

    domain_reports = {}
    guid_paths = defaultdict(list)
    title_paths = defaultdict(list)
    for domain in tuple(dict.fromkeys(domains)):
        report, records = _scan_domain(vault, domain, since, until)
        domain_reports[domain] = report
        for path, _relative, _markdown, metadata in records:
            relative_vault = path.relative_to(vault).as_posix()
            guid_paths[metadata.guid].append((domain, relative_vault))
            title_paths[metadata.title].append((domain, relative_vault))

    cross_guid = {
        key: tuple(path for _domain, path in values)
        for key, values in guid_paths.items()
        if len({domain for domain, _path in values}) > 1
    }
    cross_title = {
        key: tuple(path for _domain, path in values)
        for key, values in title_paths.items()
        if len({domain for domain, _path in values}) > 1
    }
    return ExportIntegrityReport(
        domains=domain_reports,
        cross_domain_guid_duplicates=cross_guid,
        cross_domain_title_duplicates=cross_title,
    )
