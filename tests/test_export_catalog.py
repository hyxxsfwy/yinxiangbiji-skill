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
