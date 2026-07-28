import json
import unittest
from datetime import datetime

from tests.support import workspace_temp_dir


def write_article(root, domain, month, filename, guid, title, created, body="正文内容"):
    path = root / "30_精选资料" / domain / month / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'created: "{created}"\n'
        f'updated: "{created}"\n'
        f'source_guid: "{guid}"\n'
        'type: "资料"\n'
        f'domain: "{domain}"\n'
        "---\n\n"
        f"# {title}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def write_index(root, domain, relative_paths):
    path = root / "30_精选资料" / domain / "目录索引.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: 索引",
        f"domain: {domain}",
        "---",
        "",
        f"# {domain} 目录",
        "",
    ]
    for relative in relative_paths:
        lines.extend(
            [
                f"- [[{relative}|文章]]",
                f"  - 位置：`{relative}`",
                "  - 简介：测试简介。",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_keyword_article(
    root,
    *,
    domain,
    title,
    guid,
    created,
    updated_ms,
    selection_hash,
    matched_keywords,
):
    path = (
        root
        / "30_精选资料"
        / domain
        / f"{created[:4]}年{created[5:7]}月"
        / f"{title}.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'created: "{created}"\n'
        f'updated: "{created}"\n'
        f'source_guid: "{guid}"\n'
        f"source_updated_ms: {updated_ms}\n"
        'type: "资料"\n'
        f'domain: "{domain}"\n'
        'selection_mode: "keyword_union"\n'
        f"matched_keywords: {json.dumps(matched_keywords, ensure_ascii=False)}\n"
        f'selection_hash: "{selection_hash}"\n'
        "---\n\n"
        f"# {title}\n\n"
        "AI Agent\n",
        encoding="utf-8",
    )
    return path


class ExportIntegrityTests(unittest.TestCase):
    def test_keyword_integrity_reports_missing_cache_and_wrong_selection(self):
        from scripts.export_catalog import ExportCatalog
        from scripts.export_integrity import scan_keyword_export_integrity

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            article = seed_keyword_article(
                vault,
                domain="AI",
                title="AI Agent",
                guid="guid-1",
                created="2026-04-01 00:00:00",
                updated_ms=1000,
                selection_hash="wrong",
                matched_keywords=["AI", "Agent"],
            )
            write_index(
                vault,
                "AI",
                [
                    article.relative_to(
                        vault / "30_精选资料" / "AI"
                    ).as_posix()
                ],
            )
            catalog_path = temp_dir / "catalog.sqlite3"
            with ExportCatalog(catalog_path):
                pass

            report = scan_keyword_export_integrity(
                vault,
                domains=("AI",),
                since=datetime(2026, 4, 1),
                until=datetime(2026, 8, 1),
                selection_hash="selection-1",
                catalog_path=catalog_path,
                expected_candidates={"guid-1": 1000, "guid-2": 2000},
                canonical_keywords=("AI", "Agent"),
            )

        kinds = {
            issue.kind
            for domain in report.domains.values()
            for issue in domain.issues
        }
        self.assertIn("selection_hash_mismatch", kinds)
        self.assertIn("missing_keyword_cache", kinds)
        self.assertFalse(report.ok)

    def test_keyword_integrity_accepts_reconciled_file_and_cached_rejections(self):
        from scripts.export_catalog import (
            ExportCatalog,
            KeywordCatalogEntry,
        )
        from scripts.export_integrity import scan_keyword_export_integrity

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            article = seed_keyword_article(
                vault,
                domain="AI",
                title="AI Agent",
                guid="guid-1",
                created="2026-04-01 00:00:00",
                updated_ms=1000,
                selection_hash="selection-1",
                matched_keywords=["AI", "Agent"],
            )
            relative_domain = article.relative_to(
                vault / "30_精选资料" / "AI"
            ).as_posix()
            relative_vault = article.relative_to(vault).as_posix()
            write_index(vault, "AI", [relative_domain])
            catalog_path = temp_dir / "catalog.sqlite3"
            base = {
                "selection_hash": "selection-1",
                "created_ms": 900,
                "notebook_name": "收件箱",
                "summary": "摘要",
                "body_sha256": "a" * 64,
                "primary_domain": "AI",
                "matched_keywords": ("AI", "Agent"),
                "matched_terms": ("AI", "Agent"),
                "first_fetched_at": "2026-07-29T10:00:00+08:00",
                "last_fetched_at": "2026-07-29T10:00:00+08:00",
                "last_seen_at": "2026-07-29T10:00:00+08:00",
            }
            with ExportCatalog(catalog_path) as catalog:
                catalog.upsert_keyword(
                    KeywordCatalogEntry(
                        guid="guid-1",
                        updated_ms=1000,
                        title="AI Agent",
                        outcome="accepted",
                        canonical_path=relative_vault,
                        **base,
                    )
                )
                catalog.upsert_keyword(
                    KeywordCatalogEntry(
                        guid="guid-2",
                        updated_ms=2000,
                        title="training",
                        outcome="rejected",
                        canonical_path=None,
                        matched_keywords=(),
                        matched_terms=(),
                        **{
                            key: value
                            for key, value in base.items()
                            if key not in {
                                "matched_keywords",
                                "matched_terms",
                            }
                        },
                    )
                )

            report = scan_keyword_export_integrity(
                vault,
                domains=("AI",),
                since=datetime(2026, 4, 1),
                until=datetime(2026, 8, 1),
                selection_hash="selection-1",
                catalog_path=catalog_path,
                expected_candidates={"guid-1": 1000, "guid-2": 2000},
                canonical_keywords=("AI", "Agent"),
            )

        self.assertTrue(report.ok, report.to_dict())

    def test_scanner_reports_index_attachment_and_range_facts(self):
        from scripts.export_integrity import scan_export_integrity

        with workspace_temp_dir() as vault:
            write_article(
                vault,
                "AI",
                "2026年04月",
                "范围内.md",
                "inside-guid",
                "范围内",
                "2026-04-15 10:00:00",
                body="![缺图](../_attachments/missing.png)",
            )
            write_article(
                vault,
                "AI",
                "2026年07月",
                "范围外.md",
                "outside-guid",
                "范围外",
                "2026-07-03 10:00:00",
            )
            write_index(
                vault,
                "AI",
                ["2026年04月/不存在.md"],
            )

            report = scan_export_integrity(
                vault,
                domains=("AI",),
                since=datetime.fromisoformat("2026-04-01"),
                until=datetime.fromisoformat("2026-07-01"),
            )

            domain = report.domains["AI"]
            self.assertEqual(domain.total_articles, 2)
            self.assertEqual(domain.in_range_articles, 1)
            self.assertEqual(domain.index_entries, 1)
            self.assertEqual(domain.image_references, 1)
            self.assertEqual(
                {issue.kind for issue in domain.issues},
                {
                    "missing_attachment",
                    "missing_index_target",
                    "index_missing_article",
                },
            )
            self.assertFalse(report.ok)
            self.assertEqual(
                report.to_dict()["domains"]["AI"]["in_range_articles"],
                1,
            )

    def test_scanner_finds_cross_domain_guid_and_title_duplicates(self):
        from scripts.export_integrity import scan_export_integrity

        with workspace_temp_dir() as vault:
            created = "2026-05-10 09:00:00"
            fixtures = (
                ("AI", "shared-guid", "同 GUID 同标题", "共同.md"),
                ("投资理财", "shared-guid", "同 GUID 同标题", "共同.md"),
                ("AI", "title-guid-ai", "仅标题重复", "AI标题.md"),
                (
                    "投资理财",
                    "title-guid-invest",
                    "仅标题重复",
                    "投资标题.md",
                ),
            )
            paths = {"AI": [], "投资理财": []}
            for domain, guid, title, filename in fixtures:
                path = write_article(
                    vault,
                    domain,
                    "2026年05月",
                    filename,
                    guid,
                    title,
                    created,
                )
                paths[domain].append(
                    path.relative_to(
                        vault / "30_精选资料" / domain
                    ).as_posix()
                )
            for domain, relative_paths in paths.items():
                write_index(vault, domain, relative_paths)

            report = scan_export_integrity(
                vault,
                domains=("AI", "投资理财"),
                since=datetime.fromisoformat("2026-04-01"),
                until=datetime.fromisoformat("2026-07-01"),
            )

            self.assertEqual(
                set(report.cross_domain_guid_duplicates),
                {"shared-guid"},
            )
            self.assertEqual(
                set(report.cross_domain_title_duplicates),
                {"同 GUID 同标题", "仅标题重复"},
            )
            self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
