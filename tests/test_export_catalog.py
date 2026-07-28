import sqlite3
import unittest

from tests.support import workspace_temp_dir


class ExportCatalogTests(unittest.TestCase):
    def _entry(self, **overrides):
        from scripts.export_catalog import CatalogEntry

        values = {
            "guid": "note-guid",
            "updated_ms": 1780000000000,
            "title": "Claude 与量化研究",
            "created_ms": 1770000000000,
            "notebook_name": "微信",
            "summary": "文章介绍 Claude 在量化研究中的使用方法。",
            "body_sha256": "a" * 64,
            "policy_hash": "policy-v1",
            "outcome": "accepted",
            "primary_domain": "Quant",
            "domain_labels": ("AI", "Quant"),
            "scores": {"AI": 12, "Quant": 18},
            "evidence": {
                "AI": ("claude", "大模型"),
                "Quant": ("量化研究", "回测"),
            },
            "canonical_path": (
                "30_精选资料/Quant/2026年05月/"
                "Claude 与量化研究.md"
            ),
            "first_fetched_at": "2026-07-28T10:00:00+08:00",
            "last_fetched_at": "2026-07-28T10:00:00+08:00",
            "last_seen_at": "2026-07-28T10:00:00+08:00",
        }
        values.update(overrides)
        return CatalogEntry(**values)

    def _keyword_entry(self, **overrides):
        from scripts.export_catalog import KeywordCatalogEntry

        values = {
            "guid": "guid-1",
            "updated_ms": 1000,
            "selection_hash": "selection-1",
            "title": "AI 医疗",
            "created_ms": 900,
            "notebook_name": "收件箱",
            "summary": "摘要",
            "body_sha256": "body-hash",
            "outcome": "accepted",
            "primary_domain": "AI",
            "matched_keywords": ("AI", "医学"),
            "matched_terms": ("AI", "医学"),
            "canonical_path": None,
            "first_fetched_at": "2026-07-29T10:00:00+08:00",
            "last_fetched_at": "2026-07-29T10:00:00+08:00",
            "last_seen_at": "2026-07-29T10:00:00+08:00",
        }
        values.update(overrides)
        return KeywordCatalogEntry(**values)

    def test_keyword_cache_is_separate_from_domain_cache(self):
        from scripts.export_catalog import ExportCatalog

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "export-catalog.sqlite3"
            with ExportCatalog(path) as catalog:
                catalog.upsert_keyword(self._keyword_entry())

                self.assertIsNone(catalog.get("guid-1"))
                entry = catalog.get_keyword_current(
                    "guid-1",
                    1000,
                    "selection-1",
                )

            self.assertEqual(entry.matched_keywords, ("AI", "医学"))

            with sqlite3.connect(path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertIn("parsed_notes", tables)
            self.assertIn("keyword_analyses", tables)

    def test_keyword_cache_requires_updated_and_selection_hash(self):
        from scripts.export_catalog import ExportCatalog

        entry = self._keyword_entry(outcome="rejected")
        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "export-catalog.sqlite3"
            with ExportCatalog(path) as catalog:
                catalog.upsert_keyword(entry)

                self.assertIsNotNone(
                    catalog.get_keyword_current(
                        "guid-1",
                        1000,
                        "selection-1",
                    )
                )
                self.assertIsNone(
                    catalog.get_keyword_current(
                        "guid-1",
                        1001,
                        "selection-1",
                    )
                )
                self.assertIsNone(
                    catalog.get_keyword_current(
                        "guid-1",
                        1000,
                        "selection-2",
                    )
                )
                self.assertEqual(
                    catalog.keyword_stats("selection-1"),
                    {
                        "total": 1,
                        "accepted": 0,
                        "rejected": 1,
                        "duplicate_titles": 0,
                        "domains": {"AI": 1},
                    },
                )

    def test_keyword_cache_counts_only_current_expected_candidates(self):
        from scripts.export_catalog import ExportCatalog

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "export-catalog.sqlite3"
            with ExportCatalog(path) as catalog:
                catalog.upsert_keyword(self._keyword_entry())
                catalog.upsert_keyword(
                    self._keyword_entry(
                        guid="guid-2",
                        updated_ms=2000,
                        outcome="duplicate_title",
                    )
                )
                catalog.upsert_keyword(
                    self._keyword_entry(
                        guid="historical",
                        updated_ms=3000,
                    )
                )

                self.assertEqual(
                    catalog.count_keyword_current(
                        {
                            "guid-1": 1000,
                            "guid-2": 2000,
                            "missing": 4000,
                        },
                        "selection-1",
                    ),
                    2,
                )
                self.assertEqual(
                    catalog.count_keyword_current(
                        {
                            "guid-1": 999,
                            "guid-2": 2000,
                        },
                        "selection-1",
                    ),
                    1,
                )

    def test_keyword_upsert_preserves_first_fetch_and_rejects_bad_outcome(self):
        from scripts.export_catalog import ExportCatalog

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "export-catalog.sqlite3"
            with ExportCatalog(path) as catalog:
                catalog.upsert_keyword(self._keyword_entry())
                catalog.upsert_keyword(
                    self._keyword_entry(
                        updated_ms=2000,
                        title="AI 医疗新版",
                        first_fetched_at="2026-07-30T10:00:00+08:00",
                        last_fetched_at="2026-07-30T10:00:00+08:00",
                    )
                )
                restored = catalog.get_keyword_current(
                    "guid-1",
                    2000,
                    "selection-1",
                )
                self.assertEqual(
                    restored.first_fetched_at,
                    "2026-07-29T10:00:00+08:00",
                )
                self.assertEqual(restored.title, "AI 医疗新版")

                with self.assertRaisesRegex(ValueError, "outcome"):
                    catalog.upsert_keyword(
                        self._keyword_entry(outcome="unknown")
                    )

    def test_catalog_persists_summary_domain_labels_and_audit_metadata(self):
        from scripts.export_catalog import ExportCatalog

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "export-catalog.sqlite3"
            with ExportCatalog(path) as catalog:
                catalog.upsert(self._entry())

            with ExportCatalog(path) as catalog:
                restored = catalog.get_current(
                    "note-guid",
                    1780000000000,
                    "policy-v1",
                )

            self.assertEqual(restored.title, "Claude 与量化研究")
            self.assertEqual(
                restored.summary,
                "文章介绍 Claude 在量化研究中的使用方法。",
            )
            self.assertEqual(restored.domain_labels, ("AI", "Quant"))
            self.assertEqual(restored.scores, {"AI": 12, "Quant": 18})
            self.assertEqual(
                restored.evidence["Quant"],
                ("量化研究", "回测"),
            )
            self.assertEqual(restored.primary_domain, "Quant")
            self.assertEqual(
                restored.first_fetched_at,
                "2026-07-28T10:00:00+08:00",
            )
            self.assertNotIn(
                b"FULL_SECRET_BODY",
                path.read_bytes(),
            )

            with sqlite3.connect(path) as connection:
                indexes = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA index_list(parsed_notes)"
                    )
                }
            self.assertIn("idx_parsed_notes_updated", indexes)
            self.assertIn("idx_parsed_notes_domain", indexes)
            self.assertIn("idx_parsed_notes_title", indexes)

    def test_cache_key_ignores_keywords_but_invalidates_updated_or_policy(self):
        from scripts.export_catalog import ExportCatalog

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "export-catalog.sqlite3"
            with ExportCatalog(path) as catalog:
                catalog.upsert(self._entry())

                self.assertIsNotNone(
                    catalog.get_current(
                        "note-guid",
                        1780000000000,
                        "policy-v1",
                    )
                )
                self.assertIsNone(
                    catalog.get_current(
                        "note-guid",
                        1780000000001,
                        "policy-v1",
                    )
                )
                self.assertIsNone(
                    catalog.get_current(
                        "note-guid",
                        1780000001000,
                        "policy-v1",
                    )
                )
                self.assertIsNone(
                    catalog.get_current(
                        "note-guid",
                        1780000000000,
                        "policy-v2",
                    )
                )

                catalog.mark_seen(
                    "note-guid",
                    "2026-07-29T09:00:00+08:00",
                )
                restored = catalog.get_current(
                    "note-guid",
                    1780000000000,
                    "policy-v1",
                )
                self.assertEqual(
                    restored.last_seen_at,
                    "2026-07-29T09:00:00+08:00",
                )
                self.assertEqual(
                    restored.last_fetched_at,
                    "2026-07-28T10:00:00+08:00",
                )
                self.assertEqual(
                    catalog.stats(),
                    {
                        "total": 1,
                        "accepted": 1,
                        "rejected": 0,
                        "domains": {"Quant": 1},
                    },
                )


if __name__ == "__main__":
    unittest.main()
