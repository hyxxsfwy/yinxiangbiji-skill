#!/usr/bin/env python3
"""跨任务复用印象笔记正文解析结果的本地 SQLite 目录。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import unicodedata


@dataclass(frozen=True)
class CatalogEntry:
    guid: str
    updated_ms: int
    title: str
    created_ms: int
    notebook_name: str
    summary: str
    body_sha256: str
    policy_hash: str
    outcome: str
    primary_domain: str | None
    domain_labels: tuple[str, ...]
    scores: dict[str, int]
    evidence: dict[str, tuple[str, ...]]
    canonical_path: str | None
    first_fetched_at: str
    last_fetched_at: str
    last_seen_at: str


def _normalized_title(title):
    return unicodedata.normalize("NFKC", str(title or "")).casefold().strip()


def _json_dump(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class ExportCatalog:
    """保存摘要和领域判定，不保存可还原完整正文的数据。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS parsed_notes (
                guid TEXT PRIMARY KEY,
                updated_ms INTEGER NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                created_ms INTEGER NOT NULL,
                notebook_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                body_sha256 TEXT NOT NULL,
                policy_hash TEXT NOT NULL,
                outcome TEXT NOT NULL,
                primary_domain TEXT,
                domain_labels_json TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                canonical_path TEXT,
                first_fetched_at TEXT NOT NULL,
                last_fetched_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_parsed_notes_updated
                ON parsed_notes(updated_ms);
            CREATE INDEX IF NOT EXISTS idx_parsed_notes_domain
                ON parsed_notes(primary_domain);
            CREATE INDEX IF NOT EXISTS idx_parsed_notes_title
                ON parsed_notes(normalized_title);
            """
        )
        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()

    def upsert(self, entry):
        if entry.outcome not in {"accepted", "rejected"}:
            raise ValueError("outcome 只能是 accepted 或 rejected")
        values = (
            entry.guid,
            int(entry.updated_ms),
            entry.title,
            _normalized_title(entry.title),
            int(entry.created_ms),
            entry.notebook_name,
            entry.summary,
            entry.body_sha256,
            entry.policy_hash,
            entry.outcome,
            entry.primary_domain,
            _json_dump(list(entry.domain_labels)),
            _json_dump(entry.scores),
            _json_dump(
                {
                    key: list(items)
                    for key, items in entry.evidence.items()
                }
            ),
            entry.canonical_path,
            entry.first_fetched_at,
            entry.last_fetched_at,
            entry.last_seen_at,
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO parsed_notes (
                    guid, updated_ms, title, normalized_title, created_ms,
                    notebook_name, summary, body_sha256, policy_hash,
                    outcome, primary_domain, domain_labels_json, scores_json,
                    evidence_json, canonical_path, first_fetched_at,
                    last_fetched_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guid) DO UPDATE SET
                    updated_ms = excluded.updated_ms,
                    title = excluded.title,
                    normalized_title = excluded.normalized_title,
                    created_ms = excluded.created_ms,
                    notebook_name = excluded.notebook_name,
                    summary = excluded.summary,
                    body_sha256 = excluded.body_sha256,
                    policy_hash = excluded.policy_hash,
                    outcome = excluded.outcome,
                    primary_domain = excluded.primary_domain,
                    domain_labels_json = excluded.domain_labels_json,
                    scores_json = excluded.scores_json,
                    evidence_json = excluded.evidence_json,
                    canonical_path = excluded.canonical_path,
                    first_fetched_at = parsed_notes.first_fetched_at,
                    last_fetched_at = excluded.last_fetched_at,
                    last_seen_at = excluded.last_seen_at
                """,
                values,
            )

    def get(self, guid):
        row = self.connection.execute(
            "SELECT * FROM parsed_notes WHERE guid = ?",
            (guid,),
        ).fetchone()
        return self._row_to_entry(row) if row is not None else None

    def get_current(self, guid, updated_ms, policy_hash):
        entry = self.get(guid)
        if entry is None:
            return None
        if (
            entry.updated_ms // 1000 != int(updated_ms) // 1000
            or entry.policy_hash != policy_hash
        ):
            return None
        return entry

    def mark_seen(self, guid, seen_at):
        with self.connection:
            self.connection.execute(
                """
                UPDATE parsed_notes
                SET last_seen_at = ?
                WHERE guid = ?
                """,
                (seen_at, guid),
            )

    def stats(self):
        total = self.connection.execute(
            "SELECT COUNT(*) FROM parsed_notes"
        ).fetchone()[0]
        outcomes = {
            row["outcome"]: row["count"]
            for row in self.connection.execute(
                """
                SELECT outcome, COUNT(*) AS count
                FROM parsed_notes
                GROUP BY outcome
                """
            )
        }
        domains = {
            row["primary_domain"]: row["count"]
            for row in self.connection.execute(
                """
                SELECT primary_domain, COUNT(*) AS count
                FROM parsed_notes
                WHERE primary_domain IS NOT NULL
                GROUP BY primary_domain
                ORDER BY primary_domain
                """
            )
        }
        return {
            "total": total,
            "accepted": outcomes.get("accepted", 0),
            "rejected": outcomes.get("rejected", 0),
            "domains": domains,
        }

    @staticmethod
    def _row_to_entry(row):
        evidence = json.loads(row["evidence_json"])
        return CatalogEntry(
            guid=row["guid"],
            updated_ms=row["updated_ms"],
            title=row["title"],
            created_ms=row["created_ms"],
            notebook_name=row["notebook_name"],
            summary=row["summary"],
            body_sha256=row["body_sha256"],
            policy_hash=row["policy_hash"],
            outcome=row["outcome"],
            primary_domain=row["primary_domain"],
            domain_labels=tuple(json.loads(row["domain_labels_json"])),
            scores={
                key: int(value)
                for key, value in json.loads(row["scores_json"]).items()
            },
            evidence={
                key: tuple(items)
                for key, items in evidence.items()
            },
            canonical_path=row["canonical_path"],
            first_fetched_at=row["first_fetched_at"],
            last_fetched_at=row["last_fetched_at"],
            last_seen_at=row["last_seen_at"],
        )
