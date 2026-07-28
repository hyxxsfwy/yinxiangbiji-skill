#!/usr/bin/env python3
"""一次任务完成印象笔记多领域搜索、审核、导出和验收。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.type.ttypes import NoteSortOrder

try:
    from .export_catalog import CatalogEntry, ExportCatalog
    from .export_integrity import scan_export_integrity
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
    from .knowledge_base import (
        INDEX_FILENAME,
        _split_frontmatter,
        extract_note_metadata,
        finalize_knowledge_base,
    )
    from .runtime import (
        RateLimitBudgetExceeded,
        call_with_rate_limit_retry,
        configure_utf8_output,
        create_note_store,
        find_all_notes_metadata,
        load_config,
    )
except ImportError:
    from export_catalog import CatalogEntry, ExportCatalog
    from export_integrity import scan_export_integrity
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
    from knowledge_base import (
        INDEX_FILENAME,
        _split_frontmatter,
        extract_note_metadata,
        finalize_knowledge_base,
    )
    from runtime import (
        RateLimitBudgetExceeded,
        call_with_rate_limit_retry,
        configure_utf8_output,
        create_note_store,
        find_all_notes_metadata,
        load_config,
    )


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ExportJob:
    since: date
    until: date
    vault: Path
    domains: dict[str, tuple[str, ...]]

    def target_for(self, domain):
        if domain not in self.domains:
            raise ValueError(f"任务未声明领域: {domain}")
        return self.vault / "30_精选资料" / domain


def _parse_job_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD") from exc


def normalize_job(payload):
    if not isinstance(payload, dict):
        raise ValueError("任务文件根节点必须是对象")
    since = _parse_job_date(payload.get("since"), "since")
    until = _parse_job_date(payload.get("until"), "until")
    if until <= since:
        raise ValueError("until 必须晚于 since")

    vault = Path(str(payload.get("vault") or "")).expanduser().resolve()
    if vault.name == "30_精选资料":
        raise ValueError("vault 必须指向 Obsidian 根目录，不能指向 30_精选资料")
    if not vault.is_dir():
        raise ValueError(f"Obsidian vault 不存在: {vault}")

    raw_domains = payload.get("domains")
    if not isinstance(raw_domains, dict) or not raw_domains:
        raise ValueError("domains 必须是非空对象")
    domains = {}
    for domain, settings in raw_domains.items():
        if domain not in DOMAIN_PROFILES:
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
    return ExportJob(
        since=since,
        until=until,
        vault=vault,
        domains=domains,
    )


def load_job(path):
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取任务文件 {path}: {exc}") from exc
    return normalize_job(payload)


def _job_id(job):
    payload = {
        "since": job.since.isoformat(),
        "until": job.until.isoformat(),
        "vault": str(job.vault).casefold(),
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
    temporary.replace(path)


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


def _updated_seconds(metadata):
    return int((getattr(metadata, "updated", 0) or 0) / 1000)


def _candidate_sort_key(metadata):
    return (
        getattr(metadata, "updated", 0) or 0,
        getattr(metadata, "created", 0) or 0,
        str(getattr(metadata, "guid", "") or ""),
    )


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


def main():
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        description="按任务文件执行印象笔记大规模多领域导出"
    )
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=REPO_ROOT / ".state" / "export-catalog.sqlite3",
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
        job = load_job(args.job)
    except ValueError as exc:
        parser.error(str(exc))
    task_id = _job_id(job)
    state_file = (
        args.state_file
        or REPO_ROOT / ".state" / f"multi-export-{task_id}.json"
    )
    report_file = (
        args.report_file
        or REPO_ROOT / ".state" / "reports" / f"{task_id}.json"
    )
    token, note_store_url = load_config()
    if not token or not note_store_url:
        parser.error("未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")
    note_store = create_note_store(note_store_url, token)
    try:
        report = run_export_job(
            job,
            note_store,
            token,
            catalog_path=args.catalog,
            state_file=state_file,
            report_file=report_file,
            rate_limit_mode=args.rate_limit_mode,
            max_rate_limit_wait=args.max_rate_limit_wait,
            verbose=args.verbose,
        )
    except RateLimitBudgetExceeded as exc:
        print(f"限流等待预算不足，已保留断点：{exc}")
        return 75

    counts = report["candidates"]
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
