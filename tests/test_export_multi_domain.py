import json
import unittest
from types import SimpleNamespace

from evernote.edam.error.ttypes import EDAMSystemException

from tests.support import workspace_temp_dir


def metadata(guid, title, updated, created=1775000000000):
    return SimpleNamespace(
        guid=guid,
        title=title,
        updated=updated,
        created=created,
        notebookGuid="notebook-guid",
        contentLength=100,
    )


def full_note(item, content):
    return SimpleNamespace(
        **item.__dict__,
        content=content,
        resources=[],
    )


class FakeNoteStore:
    def __init__(self, searches, notes, forbid_body=False):
        self.searches = searches
        self.notes = notes
        self.forbid_body = forbid_body
        self.body_calls = []
        self.search_calls = []

    def findNotesMetadata(
        self,
        _token,
        note_filter,
        offset,
        limit,
        _result_spec,
    ):
        keyword = note_filter.words.rsplit(" ", 1)[-1]
        values = self.searches.get(keyword, [])
        self.search_calls.append((keyword, offset, limit))
        return SimpleNamespace(
            totalNotes=len(values),
            notes=values[offset:offset + limit],
        )

    def listNotebooks(self, _token):
        return [
            SimpleNamespace(
                guid="notebook-guid",
                name="微信",
            )
        ]

    def getNote(self, _token, guid, *_args):
        self.body_calls.append(guid)
        if self.forbid_body:
            raise AssertionError("目录命中时不得重复请求正文")
        return self.notes[guid]


class MultiDomainJobTests(unittest.TestCase):
    def test_job_validation_and_target_derivation(self):
        from scripts.export_multi_domain import normalize_job

        with workspace_temp_dir() as vault:
            valid = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {
                        "AI": {"keywords": ["AI", "Agent"]},
                        "Quant": {"keywords": ["Quant"]},
                    },
                }
            )
            self.assertEqual(
                valid.target_for("AI"),
                vault.resolve() / "30_精选资料" / "AI",
            )

            invalid_payloads = (
                {
                    "since": "2026-07-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {"AI": {"keywords": ["AI"]}},
                },
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {"未知领域": {"keywords": ["AI"]}},
                },
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {"AI": {"keywords": []}},
                },
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault / "30_精选资料"),
                    "domains": {"AI": {"keywords": ["AI"]}},
                },
            )
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        normalize_job(payload)

    def test_each_guid_is_fetched_once_and_titles_are_globally_deduplicated(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        shared = metadata("shared-guid", "跨关键词文章", 1780000000000)
        newest = metadata("new-guid", "完全一致标题", 1779000000000)
        oldest = metadata("old-guid", "完全一致标题", 1778000000000)
        searches = {
            "AI": [shared],
            "Agent": [shared],
            "Quant": [newest, oldest],
        }
        notes = {
            "shared-guid": full_note(
                shared,
                "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
            ),
            "new-guid": full_note(
                newest,
                "<en-note>量化交易、量化研究、因子投资、回测和最大回撤。</en-note>",
            ),
            "old-guid": full_note(
                oldest,
                "<en-note>量化交易、量化研究、多因子、回测和夏普。</en-note>",
            ),
        }

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {
                        "AI": {"keywords": ["AI", "Agent"]},
                        "Quant": {"keywords": ["Quant"]},
                    },
                }
            )
            store = FakeNoteStore(searches, notes)
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(
                store.body_calls,
                ["shared-guid", "new-guid"],
            )
            self.assertEqual(report["candidates"]["unique_guids"], 3)
            self.assertEqual(report["candidates"]["body_requests"], 2)
            self.assertEqual(report["candidates"]["duplicate_titles"], 1)
            self.assertTrue(report["ok"])
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "AI"
                    / "2026年04月"
                    / "跨关键词文章.md"
                ).is_file()
            )
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "Quant"
                    / "2026年04月"
                    / "完全一致标题.md"
                ).is_file()
            )
            self.assertEqual(
                len(
                    list(
                        (vault / "30_精选资料").rglob(
                            "完全一致标题.md"
                        )
                    )
                ),
                1,
            )

    def test_changed_keywords_reuse_catalog_without_refetching_body(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        item = metadata("cached-guid", "可复用文章", 1780000000000)
        note = full_note(
            item,
            "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            common = {
                "since": "2026-04-01",
                "until": "2026-07-01",
                "vault": str(vault),
            }
            first_job = normalize_job(
                {
                    **common,
                    "domains": {
                        "AI": {"keywords": ["Claude"]},
                    },
                }
            )
            catalog_path = temp_dir / "catalog.sqlite3"
            first_store = FakeNoteStore(
                {"Claude": [item]},
                {"cached-guid": note},
            )
            run_export_job(
                first_job,
                first_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "first-state.json",
                report_file=temp_dir / "first-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )
            self.assertEqual(first_store.body_calls, ["cached-guid"])

            second_job = normalize_job(
                {
                    **common,
                    "domains": {
                        "AI": {"keywords": ["LLM"]},
                    },
                }
            )
            second_store = FakeNoteStore(
                {"LLM": [item]},
                {},
                forbid_body=True,
            )
            report = run_export_job(
                second_job,
                second_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "second-state.json",
                report_file=temp_dir / "second-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(second_store.body_calls, [])
            self.assertEqual(report["candidates"]["catalog_hits"], 1)
            self.assertEqual(
                report["candidates"]["body_requests_saved"],
                1,
            )
            self.assertTrue(report["ok"])
            persisted = json.loads(
                (temp_dir / "second-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                persisted["candidates"]["catalog_hits"],
                1,
            )

    def test_cached_outside_domain_is_rechecked_when_domain_is_added(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        item = metadata("investment-guid", "跨任务领域变化", 1780000000123)
        note = full_note(
            item,
            "<en-note>基金配置、股票估值、投资组合、资产配置和风险控制。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            catalog_path = temp_dir / "catalog.sqlite3"
            common = {
                "since": "2026-04-01",
                "until": "2026-07-01",
                "vault": str(vault),
            }
            first_job = normalize_job(
                {
                    **common,
                    "domains": {"AI": {"keywords": ["AI"]}},
                }
            )
            first_store = FakeNoteStore(
                {"AI": [item]},
                {"investment-guid": note},
            )
            run_export_job(
                first_job,
                first_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "first-state.json",
                report_file=temp_dir / "first-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            second_job = normalize_job(
                {
                    **common,
                    "domains": {
                        "投资理财": {"keywords": ["基金"]},
                    },
                }
            )
            second_store = FakeNoteStore(
                {"基金": [item]},
                {"investment-guid": note},
            )
            second_report = run_export_job(
                second_job,
                second_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "second-state.json",
                report_file=temp_dir / "second-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(first_store.body_calls, ["investment-guid"])
            self.assertEqual(second_store.body_calls, ["investment-guid"])
            self.assertEqual(second_report["candidates"]["accepted"], 1)
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "投资理财"
                    / "2026年04月"
                    / "跨任务领域变化.md"
                ).is_file()
            )

    def test_integrity_scans_existing_domains_outside_current_job(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.export_search_results import export_note_to_obsidian
        from scripts.knowledge_base import finalize_knowledge_base

        existing = metadata("existing-investment", "跨领域同标题", 1779000000000)
        candidate = metadata("new-ai", "跨领域同标题", 1780000000000)
        existing_note = full_note(
            existing,
            "<en-note>基金配置、股票估值、投资组合、资产配置和风险控制。</en-note>",
        )
        candidate_note = full_note(
            candidate,
            "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            investment_target = vault / "30_精选资料" / "投资理财"
            export_note_to_obsidian(
                existing_note,
                notebook_name="微信",
                target_dir=investment_target,
                domain="投资理财",
            )
            finalize_knowledge_base(investment_target, domain="投资理财")
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {"AI": {"keywords": ["AI"]}},
                }
            )
            report = run_export_job(
                job,
                FakeNoteStore(
                    {"AI": [candidate]},
                    {"new-ai": candidate_note},
                ),
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertFalse(report["ok"])
            self.assertEqual(
                set(report["integrity"]["cross_domain_title_duplicates"]),
                {"跨领域同标题"},
            )

    def test_existing_export_bootstraps_catalog_before_new_keyword_task(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.export_search_results import export_note_to_obsidian

        item = metadata("historical-guid", "历史已拉取文章", 1780000000000)
        note = full_note(
            item,
            "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            export_note_to_obsidian(
                note,
                notebook_name="微信",
                target_dir=vault / "30_精选资料" / "AI",
                domain="AI",
            )
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {
                        "AI": {"keywords": ["新关键词"]},
                    },
                }
            )
            store = FakeNoteStore(
                {"新关键词": [item]},
                {},
                forbid_body=True,
            )
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(store.body_calls, [])
            self.assertEqual(
                report["candidates"]["catalog_bootstrapped"],
                1,
            )
            self.assertEqual(report["candidates"]["catalog_hits"], 1)
            self.assertEqual(
                report["candidates"]["body_requests_saved"],
                1,
            )
            self.assertTrue(report["ok"])

    def test_interrupted_job_resumes_from_catalog_without_refetching_completed_body(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.runtime import RateLimitBudgetExceeded

        first = metadata("first-guid", "第一篇", 1780000000000)
        second = metadata("second-guid", "第二篇", 1779000000000)
        notes = {
            "first-guid": full_note(
                first,
                "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
            ),
            "second-guid": full_note(
                second,
                "<en-note>大语言模型、RAG、智能体、深度学习和模型训练。</en-note>",
            ),
        }

        class InterruptedStore(FakeNoteStore):
            def getNote(self, token, guid, *args):
                if guid == "second-guid":
                    self.body_calls.append(guid)
                    raise EDAMSystemException(
                        errorCode=19,
                        rateLimitDuration=30,
                    )
                return super().getNote(token, guid, *args)

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "vault": str(vault),
                    "domains": {"AI": {"keywords": ["AI"]}},
                }
            )
            catalog_path = temp_dir / "catalog.sqlite3"
            state_path = temp_dir / "state.json"
            first_store = InterruptedStore(
                {"AI": [first, second]},
                notes,
            )
            with self.assertRaises(RateLimitBudgetExceeded):
                run_export_job(
                    job,
                    first_store,
                    "token",
                    catalog_path=catalog_path,
                    state_file=state_path,
                    report_file=temp_dir / "interrupted-report.json",
                    rate_limit_mode="stop",
                    max_rate_limit_wait=0,
                )
            state = json.loads(
                state_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                state["processed"]["first-guid"]["outcome"],
                "accepted",
            )

            resumed_store = FakeNoteStore(
                {"AI": [first, second]},
                notes,
            )
            report = run_export_job(
                job,
                resumed_store,
                "token",
                catalog_path=catalog_path,
                state_file=state_path,
                report_file=temp_dir / "resumed-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(resumed_store.body_calls, ["second-guid"])
            self.assertEqual(report["candidates"]["catalog_hits"], 1)
            self.assertEqual(
                report["candidates"]["body_requests_saved"],
                1,
            )
            self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
