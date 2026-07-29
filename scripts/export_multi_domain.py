#!/usr/bin/env python3
"""一次任务完成印象笔记多领域搜索、审核、导出和验收。"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time as time_module
import uuid

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.type.ttypes import NoteSortOrder

try:
    from .export_catalog import (
        CatalogEntry,
        ExportCatalog,
        KeywordCatalogEntry,
    )
    from .export_integrity import (
        scan_export_integrity,
        scan_keyword_export_integrity,
    )
    from .export_search_results import (
        DOMAIN_PROFILES,
        _score_domain,
        assess_primary_domain,
        build_keyword_queries,
        domain_policy_hash,
        export_note_to_obsidian,
        full_body_text,
        markdown_attachments_complete,
    )
    from .export_snapshot import create_domain_snapshot
    from .knowledge_base import (
        INDEX_FILENAME,
        _split_frontmatter,
        archived_freshness_key,
        archived_title_owners,
        extract_note_metadata,
        finalize_knowledge_base,
    )
    from .keyword_selection import (
        assess_keyword_union,
        expanded_query_terms,
        keyword_selection_hash,
    )
    from .runtime import (
        RateLimitBudgetExceeded,
        call_with_rate_limit_retry,
        configure_utf8_output,
        create_note_store,
        find_all_notes_metadata,
        load_config,
        load_vault_root,
    )
    from .vault_state import (
        VaultStatePaths,
        migrate_legacy_state,
        require_path_within_vault,
        runtime_write_lock,
    )
except ImportError:
    from export_catalog import (
        CatalogEntry,
        ExportCatalog,
        KeywordCatalogEntry,
    )
    from export_integrity import (
        scan_export_integrity,
        scan_keyword_export_integrity,
    )
    from export_search_results import (
        DOMAIN_PROFILES,
        _score_domain,
        assess_primary_domain,
        build_keyword_queries,
        domain_policy_hash,
        export_note_to_obsidian,
        full_body_text,
        markdown_attachments_complete,
    )
    from export_snapshot import create_domain_snapshot
    from knowledge_base import (
        INDEX_FILENAME,
        _split_frontmatter,
        archived_freshness_key,
        archived_title_owners,
        extract_note_metadata,
        finalize_knowledge_base,
    )
    from keyword_selection import (
        assess_keyword_union,
        expanded_query_terms,
        keyword_selection_hash,
    )
    from runtime import (
        RateLimitBudgetExceeded,
        call_with_rate_limit_retry,
        configure_utf8_output,
        create_note_store,
        find_all_notes_metadata,
        load_config,
        load_vault_root,
    )
    from vault_state import (
        VaultStatePaths,
        migrate_legacy_state,
        require_path_within_vault,
        runtime_write_lock,
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
_INVALID_DOMAIN_CHARACTER_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_ATOMIC_REPLACE_ATTEMPTS = 241
_ATOMIC_REPLACE_RETRY_SECONDS = 0.25


@dataclass(frozen=True)
class ExportJob:
    since: date
    until: date
    vault: Path
    domains: dict[str, tuple[str, ...]]
    selection_mode: str = "domain_gate"
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def target_for(self, domain):
        if domain not in self.domains:
            raise ValueError(f"任务未声明领域: {domain}")
        root = (self.vault / "30_精选资料").resolve()
        target = (root / domain).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"领域目标逃逸出 30_精选资料: {domain}") from exc
        return target


def _parse_job_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD") from exc


def _valid_domain_name(domain):
    if (
        not domain
        or domain in {".", ".."}
        or domain[0] in {".", " "}
        or domain[-1] in {".", " "}
        or _INVALID_DOMAIN_CHARACTER_RE.search(domain)
    ):
        return False
    stem = domain.split(".", 1)[0].upper()
    return stem not in _WINDOWS_RESERVED_NAMES


def normalize_job(payload, vault):
    if not isinstance(payload, dict):
        raise ValueError("任务文件根节点必须是对象")
    since = _parse_job_date(payload.get("since"), "since")
    until = _parse_job_date(payload.get("until"), "until")
    if until <= since:
        raise ValueError("until 必须晚于 since")

    vault = Path(vault).expanduser().resolve()
    if vault.name == "30_精选资料":
        raise ValueError("vault 必须指向 Obsidian 根目录，不能指向 30_精选资料")
    if not vault.is_dir():
        raise ValueError(f"Obsidian vault 不存在: {vault}")

    selection_mode = str(
        payload.get("selection_mode", "domain_gate")
    ).strip()
    if selection_mode not in {"domain_gate", "keyword_union"}:
        raise ValueError(
            "selection_mode 只能是 domain_gate 或 keyword_union"
        )

    raw_domains = payload.get("domains")
    if not isinstance(raw_domains, dict) or not raw_domains:
        raise ValueError("domains 必须是非空对象")
    domains = {}
    for domain, settings in raw_domains.items():
        if not isinstance(domain, str) or not _valid_domain_name(domain):
            raise ValueError(f"领域名称无效: {domain!r}")
        if selection_mode == "domain_gate" and domain not in DOMAIN_PROFILES:
            raise ValueError(f"不支持的领域: {domain}")
        if not isinstance(settings, dict):
            raise ValueError(f"{domain}.keywords 配置无效")
        raw_keywords = settings.get("keywords")
        if not isinstance(raw_keywords, list):
            raise ValueError(f"{domain}.keywords 必须是数组")
        keywords = tuple(
            dict.fromkeys(
                str(keyword).strip()
                for keyword in raw_keywords
                if str(keyword).strip()
            )
        )
        if not keywords:
            raise ValueError(f"{domain}.keywords 不能为空")
        domains[domain] = keywords

    canonical_keywords = {
        keyword
        for keywords in domains.values()
        for keyword in keywords
    }
    raw_aliases = payload.get("aliases", {})
    if not isinstance(raw_aliases, dict):
        raise ValueError("aliases 必须是对象")
    aliases = {}
    for canonical_keyword, raw_terms in raw_aliases.items():
        if canonical_keyword not in canonical_keywords:
            raise ValueError(f"别名键不是规范关键词: {canonical_keyword}")
        if not isinstance(raw_terms, list) or not raw_terms:
            raise ValueError(f"{canonical_keyword} 的别名必须是非空字符串数组")
        terms = []
        for raw_term in raw_terms:
            if not isinstance(raw_term, str) or not raw_term.strip():
                raise ValueError(
                    f"{canonical_keyword} 的别名必须是非空字符串数组"
                )
            terms.append(raw_term.strip())
        aliases[canonical_keyword] = tuple(dict.fromkeys(terms))

    return ExportJob(
        since=since,
        until=until,
        vault=vault,
        domains=domains,
        selection_mode=selection_mode,
        aliases=aliases,
    )


def _read_job_payload(path):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取任务文件 {path}: {exc}") from exc


def _job_from_payload(payload, vault):
    if isinstance(payload, dict) and "vault" in payload:
        print(
            "警告：任务文件中的 vault 字段已废弃，"
            "使用 OBSIDIAN_VAULT_PATH"
        )
    return normalize_job(payload, vault)


def load_job(path, vault):
    return _job_from_payload(_read_job_payload(path), vault)


def _job_id(job):
    payload = {
        "version": 2,
        "since": job.since.isoformat(),
        "until": job.until.isoformat(),
        "domains": {
            domain: list(keywords)
            for domain, keywords in sorted(job.domains.items())
        },
    }
    if job.selection_mode != "domain_gate" or job.aliases:
        payload["selection_mode"] = job.selection_mode
        payload["aliases"] = {
            canonical_keyword: list(terms)
            for canonical_keyword, terms in sorted(job.aliases.items())
        }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]


def _legacy_job_id(job, vault):
    payload = {
        "since": job.since.isoformat(),
        "until": job.until.isoformat(),
        "vault": str(Path(vault).expanduser().resolve()).casefold(),
        "domains": {
            domain: list(keywords)
            for domain, keywords in sorted(job.domains.items())
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]


def _files_have_same_content(first, second):
    first = Path(first)
    second = Path(second)
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as first_file, second.open("rb") as second_file:
        while True:
            first_chunk = first_file.read(1024 * 1024)
            second_chunk = second_file.read(1024 * 1024)
            if first_chunk != second_chunk:
                return False
            if not first_chunk:
                return True


def _require_compatible_target(source, target, concurrent=False):
    target = Path(target)
    if not target.exists():
        return
    if (
        not target.is_file()
        or not _files_have_same_content(source, target)
    ):
        qualifier = "并发创建的" if concurrent else "已有"
        raise ValueError(
            f"v1 状态与{qualifier} v2 状态冲突，未覆盖: {target}"
        )


def _copy_without_overwrite(source, target):
    source = Path(source)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copyfile(source, staged)
        if target.exists():
            _require_compatible_target(staged, target)
            return None
        try:
            os.link(staged, target)
        except FileExistsError:
            _require_compatible_target(staged, target, concurrent=True)
            return None
        return staged.stat()
    finally:
        staged.unlink(missing_ok=True)


def _rollback_adopted_targets(published):
    for target, created_stat in reversed(published):
        quarantine = (
            target.parent / f".{target.name}.{uuid.uuid4().hex}.rollback"
        )
        try:
            os.replace(target, quarantine)
        except FileNotFoundError:
            continue

        current_stat = quarantine.stat()
        owned_by_batch = (
            current_stat.st_dev == created_stat.st_dev
            and current_stat.st_ino == created_stat.st_ino
        )
        if owned_by_batch:
            quarantine.unlink()
            continue

        try:
            os.link(quarantine, target)
        except FileExistsError as exc:
            raise ValueError(
                f"接管回滚时目标被再次占用，并发文件保留在 {quarantine}"
            ) from exc
        else:
            quarantine.unlink()


def _adopt_legacy_job_state(paths, job, payload):
    legacy_vault = payload.get("vault") if isinstance(payload, dict) else None
    if not isinstance(legacy_vault, str) or not legacy_vault.strip():
        return
    legacy_id = _legacy_job_id(job, legacy_vault)
    current_id = _job_id(job)
    candidates = tuple(
        (source, target)
        for source, target in (
            (
                paths.runs / f"multi-export-{legacy_id}.json",
                paths.runs / f"multi-export-{current_id}.json",
            ),
            (
                paths.reports / f"{legacy_id}.json",
                paths.reports / f"{current_id}.json",
            ),
        )
        if source.is_file()
    )
    for source, target in candidates:
        _require_compatible_target(source, target)
    published = []
    try:
        for source, target in candidates:
            created_stat = _copy_without_overwrite(source, target)
            if created_stat is not None:
                published.append((target, created_stat))
    except BaseException as original:
        try:
            _rollback_adopted_targets(published)
        except BaseException as rollback_error:
            original.add_note(
                f"旧任务接管回滚失败，原始异常仍为首要错误: "
                f"{rollback_error!r}"
            )
        raise


def _replace_path_with_retry(source, destination):
    for attempt in range(_ATOMIC_REPLACE_ATTEMPTS):
        try:
            Path(source).replace(destination)
            return
        except PermissionError:
            if attempt + 1 == _ATOMIC_REPLACE_ATTEMPTS:
                raise
            time_module.sleep(_ATOMIC_REPLACE_RETRY_SECONDS)


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _replace_path_with_retry(temporary, path)


def _catalog_path_is_current(job, entry, metadata):
    if not entry.canonical_path:
        return False
    candidate = (job.vault / Path(*Path(entry.canonical_path).parts)).resolve()
    try:
        candidate.relative_to(job.vault)
    except ValueError:
        return False
    if not markdown_attachments_complete(candidate):
        return False
    try:
        exported = extract_note_metadata(candidate)
    except (OSError, UnicodeError, ValueError):
        return False
    return (
        exported.guid == metadata.guid
        and int(exported.updated.timestamp())
        == int(metadata.updated / 1000)
        and candidate.parent.parent.name == entry.primary_domain
    )


def _content_analysis(content):
    body = full_body_text(content)
    scores = {}
    evidence = {}
    labels = []
    for domain, profile in DOMAIN_PROFILES.items():
        score, eligible, domain_evidence = _score_domain(body, profile)
        scores[domain] = score
        evidence[domain] = tuple(domain_evidence)
        if eligible:
            labels.append(domain)
    summary = body[:360].strip()
    if len(body) > 360:
        summary = summary.rstrip("，,；;。 ") + "……"
    return body, scores, evidence, tuple(labels), summary


def _known_vault_domains(job):
    existing_root = job.vault / "30_精选资料"
    existing = (
        [
            domain
            for domain in DOMAIN_PROFILES
            if (existing_root / domain).is_dir()
        ]
        if existing_root.is_dir()
        else []
    )
    return tuple(dict.fromkeys((*job.domains, *existing)))


def bootstrap_catalog_from_vault(job, catalog, policy_hash, seen_at):
    """用现有规范 Markdown 初始化跨任务目录，避免再次请求历史正文。"""
    bootstrapped = 0
    for directory_domain in _known_vault_domains(job):
        root = job.vault / "30_精选资料" / directory_domain
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name == INDEX_FILENAME:
                continue
            try:
                markdown = path.read_text(encoding="utf-8")
                fields, body_lines = _split_frontmatter(markdown)
                metadata = extract_note_metadata(path)
            except (OSError, UnicodeError, ValueError):
                continue
            if (
                fields.get("type") != "资料"
                or fields.get("domain") != directory_domain
            ):
                continue
            try:
                updated_ms = int(fields["source_updated_ms"])
            except (KeyError, TypeError, ValueError):
                updated_ms = int(metadata.updated.timestamp() * 1000)
            if catalog.get_current(
                metadata.guid,
                updated_ms,
                policy_hash,
            ) is not None:
                continue
            body_markdown = "\n".join(body_lines)
            assessment = assess_primary_domain(
                title=metadata.title,
                content=body_markdown,
                allowed_domains=tuple(DOMAIN_PROFILES),
            )
            if (
                not assessment.matched
                or assessment.domain != directory_domain
                or not markdown_attachments_complete(path)
            ):
                continue
            body, scores, evidence, labels, summary = _content_analysis(
                body_markdown
            )
            fetched_at = datetime.fromtimestamp(
                path.stat().st_mtime
            ).astimezone().isoformat(timespec="seconds")
            catalog.upsert(
                CatalogEntry(
                    guid=metadata.guid,
                    updated_ms=updated_ms,
                    title=metadata.title,
                    created_ms=int(metadata.created.timestamp() * 1000),
                    notebook_name=fields.get("notebook", "未知笔记本"),
                    summary=summary,
                    body_sha256=hashlib.sha256(
                        body.encode("utf-8")
                    ).hexdigest(),
                    policy_hash=policy_hash,
                    outcome="accepted",
                    primary_domain=directory_domain,
                    domain_labels=labels,
                    scores=scores,
                    evidence=evidence,
                    canonical_path=path.relative_to(job.vault).as_posix(),
                    first_fetched_at=fetched_at,
                    last_fetched_at=fetched_at,
                    last_seen_at=seen_at,
                )
            )
            bootstrapped += 1
    return bootstrapped


def bootstrap_keyword_catalog_from_vault(
    job,
    catalog,
    selection_hash,
    seen_at,
):
    """从完整且匹配当前关键词任务的现有 Markdown 回填分析缓存。"""
    bootstrapped = 0
    for directory_domain in job.domains:
        root = job.target_for(directory_domain)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name == INDEX_FILENAME:
                continue
            try:
                markdown = path.read_text(encoding="utf-8")
                fields, body_lines = _split_frontmatter(markdown)
                metadata = extract_note_metadata(path)
                updated_ms = int(fields["source_updated_ms"])
            except (KeyError, OSError, TypeError, UnicodeError, ValueError):
                continue
            if (
                fields.get("type") != "资料"
                or fields.get("domain") != directory_domain
                or not (
                    job.since
                    <= metadata.created.date()
                    < job.until
                )
                or not markdown_attachments_complete(path)
            ):
                continue
            if (
                catalog.get_keyword_current(
                    metadata.guid,
                    updated_ms,
                    selection_hash,
                )
                is not None
            ):
                continue

            body_markdown = "\n".join(body_lines)
            assessment = assess_keyword_union(
                metadata.title,
                body_markdown,
                job.domains,
                job.aliases,
            )
            if (
                not assessment.matched
                or assessment.primary_domain != directory_domain
            ):
                continue

            body = full_body_text(body_markdown)
            summary = body[:360].strip()
            if len(body) > 360:
                summary = summary.rstrip("，。；; ") + "……"
            fetched_at = datetime.fromtimestamp(
                path.stat().st_mtime
            ).astimezone().isoformat(timespec="seconds")
            catalog.upsert_keyword(
                KeywordCatalogEntry(
                    guid=metadata.guid,
                    updated_ms=updated_ms,
                    selection_hash=selection_hash,
                    title=metadata.title,
                    created_ms=int(metadata.created.timestamp() * 1000),
                    notebook_name=fields.get("notebook", "未知笔记本"),
                    summary=summary,
                    body_sha256=hashlib.sha256(
                        body.encode("utf-8")
                    ).hexdigest(),
                    outcome="accepted",
                    primary_domain=directory_domain,
                    matched_keywords=assessment.matched_keywords,
                    matched_terms=assessment.matched_terms,
                    canonical_path=path.relative_to(job.vault).as_posix(),
                    first_fetched_at=fetched_at,
                    last_fetched_at=fetched_at,
                    last_seen_at=seen_at,
                )
            )
            bootstrapped += 1
    return bootstrapped


def _updated_seconds(metadata):
    return int((getattr(metadata, "updated", 0) or 0) / 1000)


def _candidate_sort_key(metadata):
    return (
        getattr(metadata, "updated", 0) or 0,
        getattr(metadata, "created", 0) or 0,
        str(getattr(metadata, "guid", "") or ""),
    )


def _keyword_integrity_summary(integrity):
    issue_counts = Counter(
        issue.kind
        for domain in integrity.domains.values()
        for issue in domain.issues
    )
    return {
        "missing_attachments": issue_counts["missing_attachment"],
        "missing_index_targets": issue_counts["missing_index_target"],
        "index_missing_articles": issue_counts["index_missing_article"],
        "domain_duplicates": (
            issue_counts["duplicate_guid"]
            + issue_counts["duplicate_title"]
        ),
        "cross_domain_guid_duplicates": len(
            integrity.cross_domain_guid_duplicates
        ),
        "cross_domain_title_duplicates": len(
            integrity.cross_domain_title_duplicates
        ),
        "selection_hash_mismatches": issue_counts[
            "selection_hash_mismatch"
        ],
        "missing_keyword_cache": issue_counts["missing_keyword_cache"],
        "out_of_range_articles": issue_counts["out_of_range_article"],
    }


def _keyword_catalog_path_is_current(job, entry, metadata):
    if not entry.canonical_path or not entry.primary_domain:
        return False
    candidate = (
        job.vault / Path(*Path(entry.canonical_path).parts)
    ).resolve()
    try:
        candidate.relative_to(job.vault)
    except ValueError:
        return False
    if not markdown_attachments_complete(candidate):
        return False
    try:
        markdown = candidate.read_text(encoding="utf-8")
        fields, _body_lines = _split_frontmatter(markdown)
        exported = extract_note_metadata(candidate)
        exported_updated_ms = int(fields["source_updated_ms"])
    except (KeyError, OSError, TypeError, UnicodeError, ValueError):
        return False
    return (
        exported.guid == str(metadata.guid)
        and exported_updated_ms == int(metadata.updated)
        and fields.get("domain") == entry.primary_domain
        and fields.get("selection_mode") == "keyword_union"
        and fields.get("selection_hash") == entry.selection_hash
    )


def _metadata_freshness_key(metadata):
    return archived_freshness_key(
        datetime.fromtimestamp(int(metadata.updated) / 1000),
        datetime.fromtimestamp(int(metadata.created) / 1000),
        str(metadata.guid),
    )


def _historical_title_owner_is_fresher(
    owners_by_title,
    title,
    metadata,
):
    owner = owners_by_title.get(title.strip())
    if owner is None or owner.guid == str(metadata.guid):
        return False
    owner_key = archived_freshness_key(
        owner.updated,
        owner.created,
        owner.guid,
    )
    return owner_key > _metadata_freshness_key(metadata)


def _older_historical_title_paths(
    notes_by_title,
    title,
    metadata,
):
    candidate_key = _metadata_freshness_key(metadata)
    return tuple(
        note.path
        for note in notes_by_title.get(title.strip(), ())
        if archived_freshness_key(
            note.updated,
            note.created,
            note.guid,
        )
        < candidate_key
    )


def _keyword_summary_and_hash(content):
    body = full_body_text(content or "")
    summary = body[:360].strip()
    if len(body) > 360:
        summary = summary.rstrip("，。；; ") + "……"
    return (
        summary,
        hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def _keyword_entry_from_note(
    *,
    note,
    metadata,
    notebook_name,
    selection_hash,
    assessment,
    outcome,
    canonical_path,
    first_fetched_at,
    now,
):
    summary, body_sha256 = _keyword_summary_and_hash(note.content or "")
    return KeywordCatalogEntry(
        guid=str(metadata.guid),
        updated_ms=int(metadata.updated),
        selection_hash=selection_hash,
        title=note.title,
        created_ms=int(metadata.created),
        notebook_name=notebook_name,
        summary=summary,
        body_sha256=body_sha256,
        outcome=outcome,
        primary_domain=assessment.primary_domain,
        matched_keywords=assessment.matched_keywords,
        matched_terms=assessment.matched_terms,
        canonical_path=canonical_path,
        first_fetched_at=first_fetched_at,
        last_fetched_at=now,
        last_seen_at=now,
    )


def reconcile_keyword_outputs(
    job,
    catalog,
    selection_hash,
    task_id,
    *,
    older_title_paths=(),
):
    """将当前关键词任务判定为非规范的旧副本移入可恢复隔离区。"""
    state_root = VaultStatePaths.for_vault(job.vault).root
    quarantine_root = state_root / "quarantine" / task_id
    manifest_path = quarantine_root / "manifest.json"
    records = []
    affected_domains = set()

    def quarantine_path(path, metadata, reason):
        source = Path(path).resolve()
        try:
            relative_path = source.relative_to(job.vault)
        except ValueError as exc:
            raise ValueError(
                f"隔离源文件逃逸出 Vault: {source}"
            ) from exc
        if (
            len(relative_path.parts) < 3
            or relative_path.parts[0] != "30_精选资料"
        ):
            raise ValueError(
                f"隔离源文件不在领域目录内: {source}"
            )
        if not source.is_file():
            return

        relative = relative_path.as_posix()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        destination = (
            quarantine_root
            / "files"
            / relative_path
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing_digest = hashlib.sha256(
                destination.read_bytes()
            ).hexdigest()
            if existing_digest != digest:
                raise RuntimeError(
                    f"隔离区文件冲突，未移动旧副本: {destination}"
                )
            source.unlink()
        else:
            _replace_path_with_retry(source, destination)
        records.append(
            {
                "guid": metadata.guid,
                "reason": reason,
                "sha256": digest,
                "source": relative,
                "quarantine": destination.relative_to(
                    job.vault
                ).as_posix(),
            }
        )
        affected_domains.add(relative_path.parts[1])

    for directory_domain in job.domains:
        root = job.target_for(directory_domain)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name == INDEX_FILENAME:
                continue
            try:
                fields, _body_lines = _split_frontmatter(
                    path.read_text(encoding="utf-8")
                )
                metadata = extract_note_metadata(path)
            except (OSError, TypeError, UnicodeError, ValueError):
                continue
            if not (
                job.since <= metadata.created.date() < job.until
            ):
                continue

            entry = catalog.get_keyword(
                metadata.guid,
                selection_hash,
            )
            if entry is None:
                continue
            relative = path.relative_to(job.vault).as_posix()
            if (
                entry.outcome == "accepted"
                and entry.canonical_path == relative
            ):
                continue

            if entry.outcome == "accepted":
                if not entry.canonical_path:
                    continue
                canonical = (
                    job.vault
                    / Path(*Path(entry.canonical_path).parts)
                ).resolve()
                try:
                    canonical.relative_to(job.vault)
                except ValueError:
                    continue
                if not markdown_attachments_complete(canonical):
                    continue
                reason = "noncanonical_path"
            elif entry.outcome in {"rejected", "duplicate_title"}:
                reason = entry.outcome
            else:
                continue

            quarantine_path(path, metadata, reason)

    for path in sorted(
        {Path(item).resolve() for item in older_title_paths},
        key=str,
    ):
        if not path.is_file():
            continue
        metadata = extract_note_metadata(path)
        quarantine_path(
            path,
            metadata,
            "older_cross_domain_title",
        )

    previous_records = []
    if manifest_path.is_file():
        try:
            previous = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            previous_records = list(previous.get("records", ()))
        except (OSError, TypeError, UnicodeError, ValueError):
            previous_records = []
    combined = {
        item["source"]: item
        for item in (*previous_records, *records)
    }
    if records or not manifest_path.exists():
        _atomic_json(
            manifest_path,
            {
                "job_id": task_id,
                "selection_hash": selection_hash,
                "records": [
                    combined[key]
                    for key in sorted(combined)
                ],
            },
        )
    return {
        "quarantined": len(records),
        "quarantined_total": len(combined),
        "manifest": str(manifest_path),
        "affected_domains": sorted(affected_domains),
    }


def _run_keyword_union_job(
    job,
    note_store,
    token,
    *,
    catalog_path,
    state_file,
    report_file,
    rate_limit_mode="wait",
    max_rate_limit_wait=3600,
    verbose=False,
):
    selection_hash = keyword_selection_hash(job.domains, job.aliases)
    wait_stats = {"events": 0, "seconds": 0}
    processed = {}
    search_stats = []
    candidates = {}
    counts = {
        "unique_guids": 0,
        "accepted": 0,
        "rejected": 0,
        "duplicate_titles": 0,
        "body_requests": 0,
    }
    cache_counts = {
        "hits": 0,
        "stale": 0,
        "bootstrapped": 0,
        "body_requests_saved": 0,
        "rows_for_candidates": 0,
    }
    materialization = {
        "written": 0,
        "already_exported": 0,
    }
    state_payload = {
        "version": 2,
        "job_id": _job_id(job),
        "selection_mode": "keyword_union",
        "selection_hash": selection_hash,
        "processed": processed,
    }
    _atomic_json(state_file, state_payload)

    def on_wait(seconds):
        wait_stats["events"] += 1
        wait_stats["seconds"] += seconds
        print(f"API 限流，等待 {seconds} 秒后继续")

    def api_call(operation):
        remaining = max(0, max_rate_limit_wait - wait_stats["seconds"])
        return call_with_rate_limit_retry(
            operation,
            mode=rate_limit_mode,
            max_wait_seconds=remaining,
            on_wait=on_wait,
        )

    def finish_candidate():
        state_payload.pop("current_candidate", None)
        _atomic_json(state_file, state_payload)

    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeContentLength=True,
        includeCreated=True,
        includeUpdated=True,
        includeNotebookGuid=True,
    )
    expanded_terms = expanded_query_terms(job.domains, job.aliases)
    for domain, canonical_keyword, query_term in expanded_terms:
        query = build_keyword_queries(
            (query_term,),
            job.since,
            until=job.until,
        )[0]
        note_filter = NoteStore.NoteFilter(
            words=query,
            order=NoteSortOrder.UPDATED,
            ascending=False,
        )
        batch, total = api_call(
            lambda note_filter=note_filter: find_all_notes_metadata(
                note_store,
                token,
                note_filter,
                result_spec,
            )
        )
        search_stats.append(
            {
                "domain": domain,
                "canonical_keyword": canonical_keyword,
                "query_term": query_term,
                "total": total,
                "pulled": len(batch),
            }
        )
        if len(batch) != total:
            raise RuntimeError(
                f"关键词 {query_term} 分页不完整: {len(batch)}/{total}"
            )
        for metadata in batch:
            guid = str(metadata.guid)
            previous = candidates.get(guid)
            if (
                previous is None
                or _candidate_sort_key(metadata)
                > _candidate_sort_key(previous)
            ):
                candidates[guid] = metadata

    counts["unique_guids"] = len(candidates)
    state_payload["candidate_count"] = len(candidates)
    _atomic_json(state_file, state_payload)
    notebooks = api_call(lambda: note_store.listNotebooks(token))
    notebook_map = {item.guid: item.name for item in notebooks}
    selected_titles = set()
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    with ExportCatalog(catalog_path) as catalog:
        cache_counts["bootstrapped"] = (
            bootstrap_keyword_catalog_from_vault(
                job,
                catalog,
                selection_hash,
                now,
            )
        )
        snapshot_result = create_domain_snapshot(
            job.vault,
            tuple(job.domains),
            VaultStatePaths.for_vault(job.vault).root / "snapshots",
            _job_id(job),
        )
        state_payload["snapshot"] = snapshot_result.to_dict()
        _atomic_json(state_file, state_payload)
        historical_title_notes = {}
        for domain in _known_vault_domains(job):
            root = job.vault / "30_精选资料" / domain
            for title, note in archived_title_owners(root).items():
                historical_title_notes.setdefault(title, []).append(
                    note
                )
        historical_title_owners = {
            title: max(
                notes,
                key=lambda note: archived_freshness_key(
                    note.updated,
                    note.created,
                    note.guid,
                ),
            )
            for title, notes in historical_title_notes.items()
        }
        older_title_paths = set()
        for metadata in sorted(
            candidates.values(),
            key=_candidate_sort_key,
            reverse=True,
        ):
            guid = str(metadata.guid)
            metadata_title = (metadata.title or "").strip()
            cached_any = catalog.get_keyword(guid, selection_hash)
            cached = catalog.get_keyword_current(
                guid,
                int(metadata.updated),
                selection_hash,
            )
            if cached is None and cached_any is not None:
                cache_counts["stale"] += 1

            if cached is not None:
                cache_counts["hits"] += 1
                catalog.mark_keyword_seen(guid, selection_hash, now)
                if cached.outcome == "rejected":
                    counts["rejected"] += 1
                    cache_counts["body_requests_saved"] += 1
                    processed[guid] = {
                        "outcome": "cached_rejected",
                        "title": metadata_title,
                    }
                    finish_candidate()
                    continue
                if cached.outcome == "duplicate_title":
                    counts["duplicate_titles"] += 1
                    cache_counts["body_requests_saved"] += 1
                    processed[guid] = {
                        "outcome": "cached_duplicate_title",
                        "title": metadata_title,
                    }
                    finish_candidate()
                    continue
                if (
                    cached.outcome == "accepted"
                    and _historical_title_owner_is_fresher(
                        historical_title_owners,
                        metadata_title,
                        metadata,
                    )
                ):
                    duplicate = replace(
                        cached,
                        outcome="duplicate_title",
                        canonical_path=None,
                        last_seen_at=now,
                    )
                    catalog.upsert_keyword(duplicate)
                    counts["duplicate_titles"] += 1
                    cache_counts["body_requests_saved"] += 1
                    processed[guid] = {
                        "outcome": "cached_duplicate_title",
                        "title": metadata_title,
                    }
                    finish_candidate()
                    continue
                if _keyword_catalog_path_is_current(job, cached, metadata):
                    if metadata_title in selected_titles:
                        duplicate = replace(
                            cached,
                            outcome="duplicate_title",
                            canonical_path=None,
                            last_seen_at=now,
                        )
                        catalog.upsert_keyword(duplicate)
                        counts["duplicate_titles"] += 1
                        processed[guid] = {
                            "outcome": "duplicate_title",
                            "title": metadata_title,
                        }
                    else:
                        selected_titles.add(metadata_title)
                        older_title_paths.update(
                            _older_historical_title_paths(
                                historical_title_notes,
                                metadata_title,
                                metadata,
                            )
                        )
                        counts["accepted"] += 1
                        materialization["already_exported"] += 1
                        processed[guid] = {
                            "outcome": "already_exported",
                            "title": metadata_title,
                            "primary_domain": cached.primary_domain,
                            "path": cached.canonical_path,
                        }
                    cache_counts["body_requests_saved"] += 1
                    finish_candidate()
                    continue

            counts["body_requests"] += 1
            state_payload["current_candidate"] = {
                "guid": guid,
                "phase": "fetch_note",
                "updated_ms": int(metadata.updated),
            }
            _atomic_json(state_file, state_payload)
            note = api_call(
                lambda guid=guid: note_store.getNote(
                    token,
                    guid,
                    True,
                    True,
                    True,
                    True,
                )
            )
            state_payload["current_candidate"]["phase"] = "analyze_note"
            _atomic_json(state_file, state_payload)
            title = (note.title or "").strip()
            notebook_name = notebook_map.get(
                metadata.notebookGuid,
                "未知笔记本",
            )
            if cached is not None and cached.outcome == "accepted":
                summary, body_sha256 = _keyword_summary_and_hash(
                    note.content or ""
                )
                entry = replace(
                    cached,
                    title=note.title,
                    notebook_name=notebook_name,
                    summary=summary,
                    body_sha256=body_sha256,
                    canonical_path=None,
                    last_fetched_at=now,
                    last_seen_at=now,
                )
                catalog.upsert_keyword(entry)
            else:
                assessment = assess_keyword_union(
                    note.title,
                    note.content or "",
                    job.domains,
                    job.aliases,
                )
                existing_first = (
                    cached_any.first_fetched_at
                    if cached_any is not None
                    else now
                )
                outcome = (
                    "accepted"
                    if assessment.matched
                    else "rejected"
                )
                entry = _keyword_entry_from_note(
                    note=note,
                    metadata=metadata,
                    notebook_name=notebook_name,
                    selection_hash=selection_hash,
                    assessment=assessment,
                    outcome=outcome,
                    canonical_path=None,
                    first_fetched_at=existing_first,
                    now=now,
                )
                catalog.upsert_keyword(entry)

            if entry.outcome == "rejected":
                counts["rejected"] += 1
                processed[guid] = {
                    "outcome": "rejected",
                    "title": title,
                }
                if verbose:
                    print(f"[拒绝] {title}: 未命中关键词边界")
                finish_candidate()
                continue

            if _historical_title_owner_is_fresher(
                historical_title_owners,
                title,
                metadata,
            ):
                duplicate = replace(
                    entry,
                    outcome="duplicate_title",
                    canonical_path=None,
                    last_seen_at=now,
                )
                catalog.upsert_keyword(duplicate)
                counts["duplicate_titles"] += 1
                processed[guid] = {
                    "outcome": "duplicate_title",
                    "title": title,
                }
                finish_candidate()
                continue

            if title in selected_titles:
                duplicate = replace(
                    entry,
                    outcome="duplicate_title",
                    canonical_path=None,
                    last_seen_at=now,
                )
                catalog.upsert_keyword(duplicate)
                counts["duplicate_titles"] += 1
                processed[guid] = {
                    "outcome": "duplicate_title",
                    "title": title,
                }
                finish_candidate()
                continue

            selected_titles.add(title)
            target = job.target_for(entry.primary_domain)
            state_payload["current_candidate"]["phase"] = "materialize"
            _atomic_json(state_file, state_payload)
            exported_path = export_note_to_obsidian(
                note,
                notebook_name=notebook_name,
                target_dir=target,
                domain=entry.primary_domain,
                selection_mode="keyword_union",
                matched_keywords=entry.matched_keywords,
                selection_hash=selection_hash,
            )
            canonical_path = exported_path.relative_to(
                job.vault
            ).as_posix()
            entry = replace(
                entry,
                canonical_path=canonical_path,
                last_seen_at=now,
            )
            catalog.upsert_keyword(entry)
            older_title_paths.update(
                _older_historical_title_paths(
                    historical_title_notes,
                    title,
                    metadata,
                )
            )
            counts["accepted"] += 1
            materialization["written"] += 1
            processed[guid] = {
                "outcome": "accepted",
                "title": title,
                "primary_domain": entry.primary_domain,
                "path": canonical_path,
            }
            finish_candidate()

        expected_candidates = {
            guid: int(metadata.updated)
            for guid, metadata in candidates.items()
        }
        cache_counts["rows_for_candidates"] = (
            catalog.count_keyword_current(
                expected_candidates,
                selection_hash,
            )
        )
        reconciliation = reconcile_keyword_outputs(
            job,
            catalog,
            selection_hash,
            _job_id(job),
            older_title_paths=older_title_paths,
        )
        catalog_stats = catalog.keyword_stats(selection_hash)
        candidate_manifest = [
            {
                "guid": guid,
                "updated_ms": int(metadata.updated),
                "outcome": (
                    catalog.get_keyword_current(
                        guid,
                        int(metadata.updated),
                        selection_hash,
                    ).outcome
                ),
            }
            for guid, metadata in sorted(candidates.items())
        ]

    finalization_domains = tuple(
        dict.fromkeys(
            (
                *job.domains,
                *reconciliation["affected_domains"],
            )
        )
    )
    for domain in finalization_domains:
        target = job.vault / "30_精选资料" / domain
        target.mkdir(parents=True, exist_ok=True)
        finalization = finalize_knowledge_base(target, domain=domain)
        if finalization.errors:
            raise RuntimeError(
                f"{domain} 索引重建失败: {'; '.join(finalization.errors)}"
            )

    integrity = scan_keyword_export_integrity(
        job.vault,
        domains=_known_vault_domains(job),
        since=datetime.combine(job.since, time.min),
        until=datetime.combine(job.until, time.min),
        selection_hash=selection_hash,
        catalog_path=catalog_path,
        expected_candidates=expected_candidates,
        canonical_keywords=tuple(
            keyword
            for keywords in job.domains.values()
            for keyword in keywords
        ),
    )
    searches_complete = all(
        item["pulled"] == item["total"]
        for item in search_stats
    )
    candidate_cache_complete = (
        cache_counts["rows_for_candidates"] == counts["unique_guids"]
    )
    integrity_summary = _keyword_integrity_summary(integrity)
    materialization["attachment_references"] = sum(
        domain.image_references
        for domain in integrity.domains.values()
    )
    keyword_stats = []
    for domain, keywords in job.domains.items():
        for canonical_keyword in keywords:
            matching = [
                item
                for item in search_stats
                if (
                    item["domain"] == domain
                    and item["canonical_keyword"] == canonical_keyword
                )
            ]
            keyword_stats.append(
                {
                    "domain": domain,
                    "canonical_keyword": canonical_keyword,
                    "query_terms": [
                        item["query_term"]
                        for item in matching
                    ],
                    "total": sum(item["total"] for item in matching),
                    "pulled": sum(item["pulled"] for item in matching),
                }
            )

    report = {
        "ok": (
            searches_complete
            and candidate_cache_complete
            and integrity.ok
        ),
        "job": {
            "id": _job_id(job),
            "since": job.since.isoformat(),
            "until": job.until.isoformat(),
            "vault": str(job.vault),
            "selection_mode": job.selection_mode,
            "domains": {
                domain: list(keywords)
                for domain, keywords in job.domains.items()
            },
        },
        "selection": {
            "mode": "keyword_union",
            "hash": selection_hash,
            "canonical_keyword_count": sum(
                len(keywords)
                for keywords in job.domains.values()
            ),
            "query_term_count": len(expanded_terms),
            "keywords": keyword_stats,
        },
        "searches": search_stats,
        "searches_complete": searches_complete,
        "candidates": counts,
        "candidate_manifest": candidate_manifest,
        "cache": cache_counts,
        "materialization": materialization,
        "reconciliation": reconciliation,
        "snapshot": snapshot_result.to_dict(),
        "rate_limit": wait_stats,
        "catalog": catalog_stats,
        "integrity": integrity.to_dict(),
        "integrity_summary": integrity_summary,
    }
    _atomic_json(report_file, report)
    return report


def run_export_job(
    job,
    note_store,
    token,
    *,
    catalog_path,
    state_file,
    report_file,
    rate_limit_mode="wait",
    max_rate_limit_wait=3600,
    verbose=False,
):
    if job.selection_mode == "keyword_union":
        return _run_keyword_union_job(
            job,
            note_store,
            token,
            catalog_path=catalog_path,
            state_file=state_file,
            report_file=report_file,
            rate_limit_mode=rate_limit_mode,
            max_rate_limit_wait=max_rate_limit_wait,
            verbose=verbose,
        )
    return _run_domain_gate_job(
        job,
        note_store,
        token,
        catalog_path=catalog_path,
        state_file=state_file,
        report_file=report_file,
        rate_limit_mode=rate_limit_mode,
        max_rate_limit_wait=max_rate_limit_wait,
        verbose=verbose,
    )


def _run_domain_gate_job(
    job,
    note_store,
    token,
    *,
    catalog_path,
    state_file,
    report_file,
    rate_limit_mode="wait",
    max_rate_limit_wait=3600,
    verbose=False,
):
    """执行一个多领域任务并返回与落盘一致的验收报告。"""
    policy_hash = domain_policy_hash()
    wait_stats = {"events": 0, "seconds": 0}
    processed = {}
    search_stats = []
    candidate_hits = {}
    candidates = {}
    counts = {
        "unique_guids": 0,
        "body_requests": 0,
        "catalog_hits": 0,
        "catalog_stale": 0,
        "catalog_bootstrapped": 0,
        "body_requests_saved": 0,
        "accepted": 0,
        "rejected": 0,
        "already_exported": 0,
        "duplicate_titles": 0,
    }

    state_payload = {
        "version": 1,
        "job_id": _job_id(job),
        "policy_hash": policy_hash,
        "processed": processed,
    }
    _atomic_json(state_file, state_payload)

    def on_wait(seconds):
        wait_stats["events"] += 1
        wait_stats["seconds"] += seconds
        print(f"API 限流，等待 {seconds} 秒后继续")

    def api_call(operation):
        remaining = max(0, max_rate_limit_wait - wait_stats["seconds"])
        return call_with_rate_limit_retry(
            operation,
            mode=rate_limit_mode,
            max_wait_seconds=remaining,
            on_wait=on_wait,
        )

    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeContentLength=True,
        includeCreated=True,
        includeUpdated=True,
        includeNotebookGuid=True,
    )
    for domain, keywords in job.domains.items():
        queries = build_keyword_queries(
            keywords,
            job.since,
            until=job.until,
        )
        for keyword, query in zip(keywords, queries):
            note_filter = NoteStore.NoteFilter(
                words=query,
                order=NoteSortOrder.UPDATED,
                ascending=False,
            )
            batch, total = api_call(
                lambda note_filter=note_filter: find_all_notes_metadata(
                    note_store,
                    token,
                    note_filter,
                    result_spec,
                )
            )
            search_stats.append(
                {
                    "domain": domain,
                    "keyword": keyword,
                    "total": total,
                    "pulled": len(batch),
                }
            )
            if len(batch) != total:
                raise RuntimeError(
                    f"关键词 {keyword} 未完整拉取：{len(batch)}/{total}"
                )
            for metadata in batch:
                guid = str(metadata.guid)
                candidate_hits.setdefault(guid, set()).add((domain, keyword))
                previous = candidates.get(guid)
                if (
                    previous is None
                    or _candidate_sort_key(metadata)
                    > _candidate_sort_key(previous)
                ):
                    candidates[guid] = metadata

    counts["unique_guids"] = len(candidates)
    notebooks = api_call(lambda: note_store.listNotebooks(token))
    notebook_map = {item.guid: item.name for item in notebooks}
    selected_titles = set()
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    with ExportCatalog(catalog_path) as catalog:
        counts["catalog_bootstrapped"] = bootstrap_catalog_from_vault(
            job,
            catalog,
            policy_hash,
            now,
        )
        for metadata in sorted(
            candidates.values(),
            key=_candidate_sort_key,
            reverse=True,
        ):
            guid = str(metadata.guid)
            title = (metadata.title or "").strip()
            if title in selected_titles:
                counts["duplicate_titles"] += 1
                processed[guid] = {
                    "outcome": "duplicate_title",
                    "title": title,
                }
                _atomic_json(state_file, state_payload)
                continue

            cached_any = catalog.get(guid)
            cached = catalog.get_current(
                guid,
                int(metadata.updated),
                policy_hash,
            )
            if cached is None and cached_any is not None:
                counts["catalog_stale"] += 1
            if cached is not None:
                counts["catalog_hits"] += 1
                catalog.mark_seen(guid, now)
                if cached.outcome == "rejected":
                    if (
                        not cached.primary_domain
                        or cached.primary_domain not in job.domains
                    ):
                        counts["rejected"] += 1
                        counts["body_requests_saved"] += 1
                        processed[guid] = {
                            "outcome": "cached_rejected",
                            "title": title,
                            "primary_domain": cached.primary_domain,
                        }
                        _atomic_json(state_file, state_payload)
                        continue
                if cached.primary_domain not in job.domains:
                    counts["rejected"] += 1
                    counts["body_requests_saved"] += 1
                    processed[guid] = {
                        "outcome": "cached_outside_job",
                        "title": title,
                        "primary_domain": cached.primary_domain,
                    }
                    _atomic_json(state_file, state_payload)
                    continue
                if _catalog_path_is_current(job, cached, metadata):
                    selected_titles.add(title)
                    counts["already_exported"] += 1
                    counts["body_requests_saved"] += 1
                    processed[guid] = {
                        "outcome": "already_exported",
                        "title": title,
                        "primary_domain": cached.primary_domain,
                        "path": cached.canonical_path,
                    }
                    _atomic_json(state_file, state_payload)
                    continue

            counts["body_requests"] += 1
            note = api_call(
                lambda guid=guid: note_store.getNote(
                    token,
                    guid,
                    True,
                    True,
                    True,
                    True,
                )
            )
            body, scores, evidence, labels, summary = _content_analysis(
                note.content or ""
            )
            assessment = assess_primary_domain(
                title=note.title,
                content=note.content or "",
                allowed_domains=tuple(job.domains),
            )
            existing_first = (
                cached_any.first_fetched_at
                if cached_any is not None
                else now
            )
            if not assessment.matched:
                counts["rejected"] += 1
                catalog.upsert(
                    CatalogEntry(
                        guid=guid,
                        updated_ms=int(metadata.updated),
                        title=note.title,
                        created_ms=int(metadata.created),
                        notebook_name=notebook_map.get(
                            metadata.notebookGuid,
                            "未知笔记本",
                        ),
                        summary=summary,
                        body_sha256=hashlib.sha256(
                            body.encode("utf-8")
                        ).hexdigest(),
                        policy_hash=policy_hash,
                        outcome="rejected",
                        primary_domain=(
                            assessment.domain or None
                        ),
                        domain_labels=labels,
                        scores=scores,
                        evidence=evidence,
                        canonical_path=None,
                        first_fetched_at=existing_first,
                        last_fetched_at=now,
                        last_seen_at=now,
                    )
                )
                processed[guid] = {
                    "outcome": "rejected",
                    "title": title,
                    "reason": assessment.reason,
                }
                if verbose:
                    print(f"[拒绝] {title}: {assessment.reason}")
                _atomic_json(state_file, state_payload)
                continue

            selected_titles.add(title)
            target = job.target_for(assessment.domain)
            exported_path = export_note_to_obsidian(
                note,
                notebook_name=notebook_map.get(
                    metadata.notebookGuid,
                    "未知笔记本",
                ),
                target_dir=target,
                domain=assessment.domain,
            )
            canonical_path = exported_path.relative_to(job.vault).as_posix()
            counts["accepted"] += 1
            catalog.upsert(
                CatalogEntry(
                    guid=guid,
                    updated_ms=int(metadata.updated),
                    title=note.title,
                    created_ms=int(metadata.created),
                    notebook_name=notebook_map.get(
                        metadata.notebookGuid,
                        "未知笔记本",
                    ),
                    summary=summary,
                    body_sha256=hashlib.sha256(
                        body.encode("utf-8")
                    ).hexdigest(),
                    policy_hash=policy_hash,
                    outcome="accepted",
                    primary_domain=assessment.domain,
                    domain_labels=labels,
                    scores=scores,
                    evidence=evidence,
                    canonical_path=canonical_path,
                    first_fetched_at=existing_first,
                    last_fetched_at=now,
                    last_seen_at=now,
                )
            )
            processed[guid] = {
                "outcome": "accepted",
                "title": title,
                "primary_domain": assessment.domain,
                "path": canonical_path,
            }
            _atomic_json(state_file, state_payload)

        catalog_stats = catalog.stats()

    for domain in job.domains:
        target = job.target_for(domain)
        target.mkdir(parents=True, exist_ok=True)
        finalization = finalize_knowledge_base(target, domain=domain)
        if finalization.errors:
            raise RuntimeError(
                f"{domain} 索引重建失败: {'; '.join(finalization.errors)}"
            )

    integrity = scan_export_integrity(
        job.vault,
        domains=_known_vault_domains(job),
        since=datetime.combine(job.since, time.min),
        until=datetime.combine(job.until, time.min),
    )
    report = {
        "ok": integrity.ok,
        "job": {
            "id": _job_id(job),
            "since": job.since.isoformat(),
            "until": job.until.isoformat(),
            "vault": str(job.vault),
            "domains": {
                domain: list(keywords)
                for domain, keywords in job.domains.items()
            },
        },
        "searches": search_stats,
        "candidates": counts,
        "rate_limit": wait_stats,
        "catalog": catalog_stats,
        "integrity": integrity.to_dict(),
    }
    _atomic_json(report_file, report)
    return report


def positive_int_or_zero(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须大于或等于 0")
    return parsed


def _state_output_path(value, default, paths, description):
    return require_path_within_vault(
        value or default,
        paths.vault,
        description,
        allowed_root=paths.root,
    )


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        description="按任务文件执行印象笔记大规模多领域导出"
    )
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
    )
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--report-file", type=Path)
    parser.add_argument(
        "--rate-limit-mode",
        choices=("wait", "stop"),
        default="wait",
    )
    parser.add_argument(
        "--max-rate-limit-wait",
        type=positive_int_or_zero,
        default=3600,
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        vault = load_vault_root()
        paths = VaultStatePaths.for_vault(vault)
        payload = _read_job_payload(args.job)
        job = _job_from_payload(payload, vault)
        task_id = _job_id(job)
        catalog = _state_output_path(
            args.catalog,
            paths.catalog,
            paths,
            "目录文件",
        )
        state_file = _state_output_path(
            args.state_file,
            paths.runs / f"multi-export-{task_id}.json",
            paths,
            "运行状态文件",
        )
        report_file = _state_output_path(
            args.report_file,
            paths.reports / f"{task_id}.json",
            paths,
            "验收报告文件",
        )
        with runtime_write_lock(paths, task_id):
            migrate_legacy_state(paths, REPO_ROOT / ".state")
            _adopt_legacy_job_state(paths, job, payload)
            token, note_store_url = load_config()
            if not token or not note_store_url:
                parser.error("未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
            note_store = create_note_store(note_store_url, token)
            report = run_export_job(
                job,
                note_store,
                token,
                catalog_path=catalog,
                state_file=state_file,
                report_file=report_file,
                rate_limit_mode=args.rate_limit_mode,
                max_rate_limit_wait=args.max_rate_limit_wait,
                verbose=args.verbose,
            )
    except ValueError as exc:
        parser.error(str(exc))
    except RateLimitBudgetExceeded as exc:
        print(f"限流等待预算不足，已保留断点：{exc}")
        return 75

    counts = report["candidates"]
    if job.selection_mode == "keyword_union":
        cache = report["cache"]
        materialization = report["materialization"]
        print(
            "候选 {unique_guids}，接受 {accepted}，拒绝 {rejected}，"
            "同标题重复 {duplicate_titles}，正文请求 {body_requests}，"
            "缓存命中 {hits}，节省正文请求 {body_requests_saved}，"
            "实际写入 {written}"
            .format(
                **counts,
                **cache,
                **materialization,
            )
        )
    else:
        print(
            "候选 {unique_guids}，正文请求 {body_requests}，"
            "目录命中 {catalog_hits}，节省正文请求 {body_requests_saved}"
            .format(**counts)
        )
    print(f"验收报告：{report_file}")
    if not report["ok"]:
        print("导出已结束，但完整性验收未通过")
        return 1
    print("大规模多领域导出及完整性验收完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
