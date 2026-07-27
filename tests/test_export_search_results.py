import unittest
from datetime import date
import hashlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from evernote.edam.type.ttypes import NoteSortOrder

from scripts.sync_to_obsidian import save_attachments
from tests.support import workspace_temp_dir


class SearchQueryTests(unittest.TestCase):
    def test_builds_one_date_scoped_query_per_keyword(self):
        try:
            from scripts.export_search_results import build_keyword_queries
        except ModuleNotFoundError:
            self.fail("尚未实现按日期和多关键词构建查询")

        queries = build_keyword_queries(
            ["AI", "Agent", "人工智能"],
            since=date(2025, 7, 26),
        )

        self.assertEqual(
            queries,
            [
                "created:20250726 AI",
                "created:20250726 Agent",
                "created:20250726 人工智能",
            ],
        )

    def test_builds_an_exclusive_end_date_into_each_keyword_query(self):
        from scripts.export_search_results import build_keyword_queries

        queries = build_keyword_queries(
            ["AI", "量化"],
            since=date(2026, 7, 1),
            until=date(2026, 8, 1),
        )

        self.assertEqual(
            queries,
            [
                "created:20260701 -created:20260801 AI",
                "created:20260701 -created:20260801 量化",
            ],
        )

    def test_deduplicates_and_prioritizes_recent_title_matches(self):
        try:
            from scripts.export_search_results import select_top_notes
        except ImportError:
            self.fail("尚未实现搜索结果去重与排序")

        image_only = SimpleNamespace(
            guid="image",
            title="图片",
            created=400,
            updated=400,
        )
        agent_note = SimpleNamespace(
            guid="agent",
            title="Agent 技术总结",
            created=200,
            updated=200,
        )
        ai_note_old = SimpleNamespace(
            guid="ai",
            title="AI 编程指南",
            created=250,
            updated=250,
        )
        ai_note_new = SimpleNamespace(
            guid="ai",
            title="AI 编程指南",
            created=250,
            updated=300,
        )
        chinese_note = SimpleNamespace(
            guid="cn",
            title="人工智能评测",
            created=100,
            updated=100,
        )

        selected = select_top_notes(
            [
                [image_only, ai_note_old, agent_note],
                [ai_note_new, chinese_note],
            ],
            keywords=["AI", "Agent", "人工智能"],
            limit=3,
        )

        self.assertEqual([note.guid for note in selected], ["ai", "agent", "cn"])
        self.assertEqual(selected[0].updated, 300)

    def test_deduplicates_exact_titles_before_applying_limit(self):
        from scripts.export_search_results import select_top_notes

        older = SimpleNamespace(
            guid="same-old",
            title="Agent 重复剪藏",
            created=100,
            updated=200,
        )
        newer = SimpleNamespace(
            guid="same-new",
            title="Agent 重复剪藏",
            created=150,
            updated=300,
        )
        same_updated_newer_created = SimpleNamespace(
            guid="same-created",
            title="Agent 重复剪藏",
            created=180,
            updated=300,
        )
        unique = SimpleNamespace(
            guid="unique",
            title="AI 唯一文章",
            created=120,
            updated=250,
        )

        selected = select_top_notes(
            [[older, newer, unique, same_updated_newer_created]],
            keywords=["AI", "Agent"],
            limit=2,
        )

        self.assertEqual(
            [note.guid for note in selected],
            ["same-created", "unique"],
        )
        self.assertEqual(len({note.title for note in selected}), 2)

    def test_uses_guid_to_break_a_same_title_timestamp_tie(self):
        from scripts.export_search_results import (
            rank_note_candidates,
            select_top_notes,
        )

        first = SimpleNamespace(
            guid="aaa-guid",
            title="AI 完全重复",
            created=100,
            updated=200,
        )
        second = SimpleNamespace(
            guid="zzz-guid",
            title="AI 完全重复",
            created=100,
            updated=200,
        )

        selected = select_top_notes(
            [[first, second]],
            keywords=["AI"],
            limit=1,
        )
        ranked = rank_note_candidates(
            [[first, second]],
            keywords=["AI"],
        )

        self.assertEqual([note.guid for note in selected], ["zzz-guid"])
        self.assertEqual([note.guid for note in ranked], ["zzz-guid", "aaa-guid"])

    def test_selects_every_unique_title_when_limit_is_unbounded(self):
        from scripts.export_search_results import select_top_notes

        notes = [
            SimpleNamespace(
                guid=f"guid-{index}",
                title=f"AI 笔记 {index}",
                created=index,
                updated=index,
            )
            for index in range(5)
        ]

        selected = select_top_notes(
            [notes],
            keywords=["AI"],
            limit=None,
        )

        self.assertEqual(len(selected), 5)
        self.assertEqual(
            {note.guid for note in selected},
            {f"guid-{index}" for index in range(5)},
        )

    def test_searches_each_keyword_with_updated_descending_order(self):
        try:
            from scripts.export_search_results import search_metadata_batches
        except ImportError:
            self.fail("尚未实现多关键词元数据搜索")

        class FakeNoteStore:
            def __init__(self):
                self.calls = []

            def findNotesMetadata(
                self,
                token,
                note_filter,
                offset,
                max_results,
                result_spec,
            ):
                self.calls.append(
                    {
                        "token": token,
                        "words": note_filter.words,
                        "order": note_filter.order,
                        "ascending": note_filter.ascending,
                        "offset": offset,
                        "max_results": max_results,
                    }
                )
                return SimpleNamespace(
                    notes=[SimpleNamespace(guid=note_filter.words)],
                    totalNotes=1,
                )

        note_store = FakeNoteStore()
        batches, totals = search_metadata_batches(
            note_store,
            token="test-token",
            keywords=["AI", "Agent"],
            since=date(2025, 7, 26),
            until=date(2025, 8, 1),
            max_per_keyword=25,
        )

        self.assertEqual(
            [call["words"] for call in note_store.calls],
            [
                "created:20250726 -created:20250801 AI",
                "created:20250726 -created:20250801 Agent",
            ],
        )
        self.assertTrue(
            all(
                call["order"] == NoteSortOrder.UPDATED
                and call["ascending"] is False
                and call["offset"] == 0
                and call["max_results"] == 25
                for call in note_store.calls
            )
        )
        self.assertEqual([len(batch) for batch in batches], [1, 1])
        self.assertEqual(totals, [1, 1])


class DomainRelevanceTests(unittest.TestCase):
    def test_rejects_title_hit_when_full_body_is_unrelated(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="AI",
            title="AI 时代的家庭收纳",
            content=(
                "<en-note><div>本文介绍衣柜分区、厨房清洁和家庭物品"
                "收纳方法，不讨论任何技术主题。</div></en-note>"
            ),
        )

        self.assertFalse(assessment.matched)
        self.assertIn("正文", assessment.reason)

    def test_accepts_neutral_title_when_full_body_matches_domain(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="AI",
            title="本周技术观察",
            content=(
                "<en-note><div>本文比较大语言模型的推理能力，并介绍"
                " RAG、向量检索和提示词工程的实现方法。</div></en-note>"
            ),
        )

        self.assertTrue(assessment.matched)
        self.assertIn("大语言模型", assessment.evidence)
        self.assertIn("rag", assessment.evidence)

    def test_accepts_agent_skill_article_from_body_evidence_cluster(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="AI",
            title="删掉80%的Skill，Agent反而更听话了",
            content=(
                "<en-note><div>Agent 的 Skill 太多会分散上下文，"
                "系统指令、工具调用和提示词互相竞争。精简 Skill 后，"
                "模型能够更稳定地选择工具。</div></en-note>"
            ),
        )

        self.assertTrue(assessment.matched)

    def test_accepts_reinforcement_learning_and_diffusion_body(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="AI",
            title="模型训练方法",
            content=(
                "<en-note>本文讨论强化学习、RLHF、奖励模型和"
                "Stable Diffusion 扩散模型的训练方法。</en-note>"
            ),
        )

        self.assertTrue(assessment.matched)

    def test_accepts_crypto_and_etf_body_as_investment(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="投资理财",
            title="资产观察",
            content=(
                "<en-note>本文比较 ETF 定投、比特币 BTC、以太坊 ETH "
                "和 SOL 的资产配置与风险控制。</en-note>"
            ),
        )

        self.assertTrue(assessment.matched)

    def test_short_crypto_symbols_do_not_match_inside_english_words(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="投资理财",
            title="Software method",
            content=(
                "<en-note>This method describes a software solution "
                "for resolving network isolation.</en-note>"
            ),
        )

        self.assertFalse(assessment.matched)

    def test_rejects_target_domain_when_another_domain_is_clearly_dominant(self):
        from scripts.export_search_results import assess_domain_relevance

        assessment = assess_domain_relevance(
            domain="AI",
            title="人工智能热点与投资组合",
            content=(
                "<en-note><div>人工智能只是市场热点之一。本文重点讨论"
                "股票估值、基金配置、债券收益率、投资组合、仓位管理、"
                "资产配置与风险控制。</div></en-note>"
            ),
        )

        self.assertFalse(assessment.matched)
        self.assertEqual(assessment.competing_domain, "投资理财")
        self.assertIn("更接近", assessment.reason)


class DomainGatedExportTests(unittest.TestCase):
    def test_resume_skips_unchanged_candidates_previously_rejected(self):
        from scripts.export_search_results import export_domain_candidates

        metadata = SimpleNamespace(
            guid="rejected-guid",
            title="AI 家庭整理术",
            created=1753488000000,
            updated=1753574400000,
            notebookGuid="notebook-guid",
        )
        note = SimpleNamespace(
            **metadata.__dict__,
            content="<en-note>衣柜整理、厨房清洁和家庭收纳。</en-note>",
            resources=[],
        )

        class FirstNoteStore:
            def getNote(self, *_args):
                return note

        class ResumeNoteStore:
            def getNote(self, *_args):
                raise AssertionError("未变化的已拒绝候选不应再次请求正文")

        with workspace_temp_dir() as temp_dir:
            state_file = temp_dir / "export-state.json"
            first = export_domain_candidates(
                note_store=FirstNoteStore(),
                token="token",
                candidates=[metadata],
                notebook_map={"notebook-guid": "剪藏"},
                target_dir=temp_dir / "AI",
                domain="AI",
                limit=None,
                state_file=state_file,
            )
            resumed = export_domain_candidates(
                note_store=ResumeNoteStore(),
                token="token",
                candidates=[metadata],
                notebook_map={"notebook-guid": "剪藏"},
                target_dir=temp_dir / "AI",
                domain="AI",
                limit=None,
                state_file=state_file,
            )

            self.assertEqual(len(first.rejected), 1)
            self.assertTrue(state_file.is_file())
            self.assertEqual(
                [item.guid for item in resumed.previously_rejected],
                ["rejected-guid"],
            )
            self.assertEqual(resumed.rejected, ())

    def test_resume_skips_unchanged_guids_already_exported_to_target(self):
        from datetime import datetime

        from scripts.export_search_results import export_domain_candidates

        updated_ms = 1753574400000
        existing = SimpleNamespace(
            guid="already-exported",
            title="已导出的 AI 笔记",
            created=1753488000000,
            updated=updated_ms,
            notebookGuid="notebook-guid",
        )
        pending = SimpleNamespace(
            guid="pending-note",
            title="待导出的 AI 笔记",
            created=1753488000000,
            updated=1753574400000,
            notebookGuid="notebook-guid",
        )
        pending_note = SimpleNamespace(
            **pending.__dict__,
            content=(
                "<en-note>本文讨论大语言模型、智能体、RAG 和"
                "向量检索。</en-note>"
            ),
            resources=[],
        )

        class FakeNoteStore:
            def __init__(self):
                self.calls = []

            def getNote(self, _token, guid, *_args):
                self.calls.append(guid)
                if guid != "pending-note":
                    raise AssertionError("续跑不应再次读取已成功导出的正文")
                return pending_note

        with workspace_temp_dir() as temp_dir:
            target = temp_dir / "AI"
            month = target / "2025年07月"
            month.mkdir(parents=True)
            updated_text = datetime.fromtimestamp(
                updated_ms / 1000
            ).strftime("%Y-%m-%d %H:%M:%S")
            (month / "已导出的 AI 笔记.md").write_text(
                "---\n"
                'created: "2025-07-26 08:00:00"\n'
                f'updated: "{updated_text}"\n'
                'source_guid: "already-exported"\n'
                "---\n\n"
                "# 已导出的 AI 笔记\n\n"
                "已有正文。\n",
                encoding="utf-8",
            )

            note_store = FakeNoteStore()
            result = export_domain_candidates(
                note_store=note_store,
                token="token",
                candidates=[existing, pending],
                notebook_map={"notebook-guid": "剪藏"},
                target_dir=target,
                domain="AI",
                limit=None,
            )

            self.assertEqual(note_store.calls, ["pending-note"])
            self.assertEqual(
                [item.guid for item in result.already_exported],
                ["already-exported"],
            )
            self.assertEqual(
                [review.metadata.guid for review in result.selected],
                ["pending-note"],
            )

    def test_mismatched_full_body_writes_no_markdown_or_attachments(self):
        from scripts.export_search_results import export_domain_candidates

        image_hash = "0123456789abcdef0123456789abcdef"
        metadata = SimpleNamespace(
            guid="wrong-domain",
            title="AI 家庭整理术",
            created=1753488000000,
            updated=1753574400000,
            notebookGuid="notebook-guid",
        )
        note = SimpleNamespace(
            **metadata.__dict__,
            content=(
                "<en-note><div>这篇文章只讨论衣柜整理、厨房清洁和"
                "家庭物品收纳。</div>"
                f'<en-media type="image/png" hash="{image_hash}"/>'
                "</en-note>"
            ),
            resources=[
                SimpleNamespace(
                    data=SimpleNamespace(
                        body=b"must-not-be-written",
                        bodyHash=bytes.fromhex(image_hash),
                    ),
                    mime="image/png",
                    attributes=SimpleNamespace(fileName="wrong.png"),
                )
            ],
        )

        class FakeNoteStore:
            def getNote(self, *_args):
                return note

        with workspace_temp_dir() as temp_dir:
            target = temp_dir / "AI"
            result = export_domain_candidates(
                note_store=FakeNoteStore(),
                token="token",
                candidates=[metadata],
                notebook_map={"notebook-guid": "剪藏"},
                target_dir=target,
                domain="AI",
                limit=1,
            )

            self.assertEqual(result.exported_paths, ())
            self.assertEqual(len(result.rejected), 1)
            self.assertFalse(target.exists())

    def test_skips_mismatch_and_continues_until_limit_is_filled(self):
        from scripts.export_search_results import export_domain_candidates

        candidates = [
            SimpleNamespace(
                guid="wrong-domain",
                title="AI 家庭整理术",
                created=1753488000000,
                updated=1753660800000,
                notebookGuid="notebook-guid",
            ),
            SimpleNamespace(
                guid="right-domain",
                title="技术观察",
                created=1753488000000,
                updated=1753574400000,
                notebookGuid="notebook-guid",
            ),
        ]
        notes = {
            "wrong-domain": SimpleNamespace(
                **candidates[0].__dict__,
                content=(
                    "<en-note><div>衣柜整理、厨房清洁和家庭收纳。"
                    "</div></en-note>"
                ),
                resources=[],
            ),
            "right-domain": SimpleNamespace(
                **candidates[1].__dict__,
                content=(
                    "<en-note><div>本文讨论大语言模型、智能体、RAG "
                    "和向量检索的工程实践。</div></en-note>"
                ),
                resources=[],
            ),
        }

        class FakeNoteStore:
            def __init__(self):
                self.calls = []

            def getNote(self, _token, guid, *_args):
                self.calls.append(guid)
                return notes[guid]

        note_store = FakeNoteStore()
        with workspace_temp_dir() as temp_dir:
            target = temp_dir / "AI"
            result = export_domain_candidates(
                note_store=note_store,
                token="token",
                candidates=candidates,
                notebook_map={"notebook-guid": "剪藏"},
                target_dir=target,
                domain="AI",
                limit=1,
            )

            exported_names = [
                path.name for path in result.exported_paths
            ]
            self.assertEqual(exported_names, ["技术观察.md"])
            self.assertEqual(note_store.calls, ["wrong-domain", "right-domain"])
            self.assertFalse(
                any(target.rglob("AI 家庭整理术.md"))
            )
            self.assertEqual(len(result.rejected), 1)

    def test_checks_older_duplicate_when_newest_body_is_mismatched(self):
        from scripts.export_search_results import export_domain_candidates

        candidates = [
            SimpleNamespace(
                guid="new-wrong",
                title="Agent 专题",
                created=1753488000000,
                updated=1753660800000,
                notebookGuid="notebook-guid",
            ),
            SimpleNamespace(
                guid="old-right",
                title="Agent 专题",
                created=1753401600000,
                updated=1753488000000,
                notebookGuid="notebook-guid",
            ),
        ]
        notes = {
            "new-wrong": SimpleNamespace(
                **candidates[0].__dict__,
                content="<en-note>旅行住宿与行李收纳指南。</en-note>",
                resources=[],
            ),
            "old-right": SimpleNamespace(
                **candidates[1].__dict__,
                content=(
                    "<en-note>大语言模型的智能体通过 RAG、向量检索"
                    "和工具调用完成任务。</en-note>"
                ),
                resources=[],
            ),
        }

        class FakeNoteStore:
            def getNote(self, _token, guid, *_args):
                return notes[guid]

        with workspace_temp_dir() as temp_dir:
            result = export_domain_candidates(
                note_store=FakeNoteStore(),
                token="token",
                candidates=candidates,
                notebook_map={"notebook-guid": "剪藏"},
                target_dir=temp_dir / "AI",
                domain="AI",
                limit=1,
            )

        self.assertEqual(
            [review.metadata.guid for review in result.selected],
            ["old-right"],
        )
        self.assertEqual(
            [review.metadata.guid for review in result.rejected],
            ["new-wrong"],
        )


class ExportNoteTests(unittest.TestCase):
    def test_exports_plain_text_note_with_source_metadata(self):
        try:
            from scripts.export_search_results import export_note_to_obsidian
        except ImportError:
            self.fail("尚未实现单篇笔记导出")

        note = SimpleNamespace(
            guid="note-guid",
            title="AI 笔记",
            created=1753488000000,
            updated=1753574400000,
            content="<en-note>AI 内容</en-note>",
            resources=[],
        )

        with workspace_temp_dir() as temp_dir:
            exported_path = export_note_to_obsidian(
                note,
                notebook_name="2026",
                target_dir=temp_dir,
                domain="AI",
            )
            exported_content = exported_path.read_text(encoding="utf-8")

        self.assertEqual(exported_path.name, "AI 笔记.md")
        self.assertEqual(exported_path.parent.name, "2025年07月")
        self.assertIn('source_guid: "note-guid"', exported_content)
        self.assertIn('notebook: "2026"', exported_content)
        self.assertIn('type: "资料"', exported_content)
        self.assertIn('domain: "AI"', exported_content)
        self.assertIn('status: "待提炼"', exported_content)
        self.assertIn('tags: []', exported_content)
        self.assertIn('review_status: "pending"', exported_content)
        self.assertIn('llm_policy: "strict"', exported_content)
        self.assertIn("# AI 笔记", exported_content)
        self.assertIn("AI 内容", exported_content)

    def test_exports_inline_image_resource_and_markdown_reference(self):
        from scripts.export_search_results import export_note_to_obsidian

        image_data = b"test-image"
        image_hash = "0123456789abcdef0123456789abcdef"
        resource = SimpleNamespace(
            data=SimpleNamespace(
                body=image_data,
                bodyHash=bytes.fromhex(image_hash),
            ),
            mime="image/png",
            attributes=SimpleNamespace(fileName=None),
        )
        note = SimpleNamespace(
            guid="image-note-guid",
            title="Agent 图片笔记",
            created=1753488000000,
            updated=1753574400000,
            content=(
                "<en-note><div>Agent 图片</div>"
                f'<en-media type="image/png" hash="{image_hash}"/>'
                "</en-note>"
            ),
            resources=[resource],
        )

        with workspace_temp_dir() as temp_dir:
            target_dir = temp_dir
            exported_path = export_note_to_obsidian(
                note,
                notebook_name="微信",
                target_dir=target_dir,
            )
            exported_content = exported_path.read_text(encoding="utf-8")
            image_path = target_dir / "_attachments" / f"{image_hash}.png"

            self.assertTrue(image_path.exists())
            self.assertEqual(image_path.read_bytes(), image_data)

        self.assertIn(
            f"![{image_hash}.png](../_attachments/{image_hash}.png)",
            exported_content,
        )
        self.assertEqual(
            exported_content.count(
                f"![{image_hash}.png](../_attachments/{image_hash}.png)"
            ),
            1,
        )
        self.assertEqual(exported_path.parent.name, "2025年07月")

    def test_exports_a_single_title_with_compact_article_layout(self):
        from scripts.export_search_results import export_note_to_obsidian

        image_data = b"article-image"
        image_hash = "fedcba9876543210fedcba9876543210"
        resource = SimpleNamespace(
            data=SimpleNamespace(
                body=image_data,
                bodyHash=bytes.fromhex(image_hash),
            ),
            mime="image/png",
            attributes=SimpleNamespace(fileName="article.png"),
        )
        note = SimpleNamespace(
            guid="article-guid",
            title="删掉80%的Skill，Agent反而更听话了",
            created=1753488000000,
            updated=1753574400000,
            content=(
                "<en-note>"
                "<h1>删掉80%的Skill，Agent反而更听话了</h1>"
                "<div><br></div><div><br></div>"
                "<h1>01</h1><div>为什么模型不遵循指令</div>"
                "<div>正文</div>"
                f'<en-media type="image/png" hash="{image_hash}"/>'
                "</en-note>"
            ),
            resources=[resource],
        )

        with workspace_temp_dir() as temp_dir:
            exported_path = export_note_to_obsidian(
                note,
                notebook_name="微信",
                target_dir=temp_dir,
            )
            exported_content = exported_path.read_text(encoding="utf-8")

        self.assertNotRegex(exported_content, r"(?m)^title:")
        self.assertEqual(
            exported_content.count(
                "# 删掉80%的Skill，Agent反而更听话了"
            ),
            1,
        )
        self.assertIn("## 01 为什么模型不遵循指令", exported_content)
        self.assertNotIn("\n\n\n", exported_content)
        self.assertIn(
            "![article.png](../_attachments/article.png)",
            exported_content,
        )


class AttachmentSavingTests(unittest.TestCase):
    def test_same_filename_with_different_content_gets_unique_paths(self):
        first_data = b"first-image"
        second_data = b"second-image"
        first_hash = "11111111111111111111111111111111"
        second_hash = "22222222222222222222222222222222"
        resources = {
            first_hash: {
                "filename": "640.png",
                "data": first_data,
                "mime": "image/png",
                "hash": first_hash,
                "content_hash": hashlib.sha256(first_data).hexdigest(),
            },
            second_hash: {
                "filename": "640.png",
                "data": second_data,
                "mime": "image/png",
                "hash": second_hash,
                "content_hash": hashlib.sha256(second_data).hexdigest(),
            },
        }

        with workspace_temp_dir() as temp_dir:
            saved = save_attachments(resources, temp_dir)
            first_path = temp_dir / saved[first_hash]
            second_path = temp_dir / saved[second_hash]

            self.assertNotEqual(saved[first_hash], saved[second_hash])
            self.assertEqual(saved[first_hash], "640.png")
            self.assertEqual(
                saved[second_hash],
                f"640_{second_hash[:8]}.png",
            )
            self.assertEqual(first_path.read_bytes(), first_data)
            self.assertEqual(second_path.read_bytes(), second_data)

    def test_never_reuses_a_conflicting_hash_suffixed_filename(self):
        image_data = b"expected-image"
        image_hash = "33333333333333333333333333333333"
        resources = {
            image_hash: {
                "filename": "640.png",
                "data": image_data,
                "mime": "image/png",
                "hash": image_hash,
                "content_hash": hashlib.sha256(image_data).hexdigest(),
            },
        }

        with workspace_temp_dir() as temp_dir:
            (temp_dir / "640.png").write_bytes(b"conflict-1")
            (temp_dir / f"640_{image_hash[:8]}.png").write_bytes(
                b"conflict-2"
            )
            (temp_dir / f"640_{image_hash}.png").write_bytes(
                b"conflict-3"
            )

            saved = save_attachments(resources, temp_dir)
            saved_path = temp_dir / saved[image_hash]

            self.assertEqual(
                saved[image_hash],
                f"640_{image_hash}_2.png",
            )
            self.assertEqual(saved_path.read_bytes(), image_data)


class ResourceExtractionTests(unittest.TestCase):
    def test_uses_evernote_body_hash_as_en_media_identity(self):
        from scripts.sync_to_obsidian import extract_resources

        body = b"inline-image"
        evernote_hash = "0123456789abcdef0123456789abcdef"
        resource = SimpleNamespace(
            data=SimpleNamespace(
                body=body,
                bodyHash=bytes.fromhex(evernote_hash),
            ),
            mime="image/png",
            attributes=SimpleNamespace(fileName=None),
        )

        extracted = extract_resources(
            SimpleNamespace(resources=[resource])
        )

        self.assertIn(evernote_hash, extracted)
        self.assertEqual(
            extracted[evernote_hash]["content_hash"],
            hashlib.sha256(body).hexdigest(),
        )


class HtmlConversionTests(unittest.TestCase):
    def test_converts_more_than_one_hundred_inline_resources(self):
        from scripts.sync_to_obsidian import html_to_md

        hashes = [f"{index:032x}" for index in range(101)]
        mapping = {value: f"{value}.png" for value in hashes}
        enml = (
            "<en-note>"
            + "".join(
                f'<en-media type="image/png" hash="{value}"/>'
                for value in hashes
            )
            + "</en-note>"
        )

        markdown = html_to_md(enml, mapping)

        self.assertNotIn("<en-media", markdown)
        self.assertEqual(markdown.count("_attachments/"), 101)

    def test_simplifies_body_headings_without_losing_rich_content(self):
        from scripts.sync_to_obsidian import simplify_markdown

        body = (
            "# 示例标题\n\n\n\n"
            "# 01\n\n为什么模型不遵循指令\n\n\n"
            "1.1 原因一：注意力分散\n\n"
            "# 其他一级标题\n\n"
            "* 列表项\n\n"
            "| 列 | 值 |\n| --- | --- |\n| A | 1 |\n\n"
            "![图](_attachments/image.png)\n"
        )

        simplified = simplify_markdown(body, "示例标题")

        self.assertNotIn("# 示例标题", simplified)
        self.assertIn("## 01 为什么模型不遵循指令", simplified)
        self.assertIn("### 1.1 原因一：注意力分散", simplified)
        self.assertIn("## 其他一级标题", simplified)
        self.assertIn("* 列表项", simplified)
        self.assertIn("| A | 1 |", simplified)
        self.assertIn("![图](_attachments/image.png)", simplified)
        self.assertNotIn("\n\n\n", simplified)

    def test_preserves_evernote_codeblock_line_breaks(self):
        from scripts.sync_to_obsidian import html_to_md, simplify_markdown

        enml = (
            "<en-note><div>正文</div>"
            '<div style="--en-codeblock:true;color:#333">'
            "[第 1 层] 全局规则\n"
            "[第 2 层] 核心方法\n"
            "</div><div>结尾</div></en-note>"
        )

        markdown = simplify_markdown(html_to_md(enml, {}), "示例")

        self.assertIn(
            "    [第 1 层] 全局规则\n    [第 2 层] 核心方法",
            markdown,
        )
        self.assertIn("正文", markdown)
        self.assertIn("结尾", markdown)

    def test_converts_links_todos_and_discards_embedded_svg_placeholders(self):
        from scripts.sync_to_obsidian import enml_to_markdown, html_to_md

        plain_markdown = enml_to_markdown(
            '<en-note><a class="source" href="https://example.com">'
            "示例链接</a></en-note>"
        )
        rich_markdown = html_to_md(
            '<en-note><img alt="placeholder" '
            'src="data:image/svg+xml;base64,PHN2Zy8+"></img>'
            '<en-todo checked="true"></en-todo>完成'
            '<en-todo checked="false"></en-todo>待办</en-note>',
            {},
        )

        self.assertEqual(
            plain_markdown,
            "[示例链接](https://example.com)",
        )
        self.assertNotIn("placeholder", rich_markdown)
        self.assertNotIn("data:image/svg+xml", rich_markdown)
        self.assertIn("[x] 完成", rich_markdown)
        self.assertIn("[ ] 待办", rich_markdown)


class AttachmentLinkTests(unittest.TestCase):
    def test_special_filename_characters_are_url_encoded(self):
        from scripts.sync_to_obsidian import make_attachment_link

        link = make_attachment_link("报告 (最终)#1.png")

        self.assertIn(
            "_attachments/%E6%8A%A5%E5%91%8A%20%28%E6%9C%80%E7%BB%88%29%231.png",
            link,
        )


class CommandLineTests(unittest.TestCase):
    def test_help_is_emitted_as_utf8_on_windows(self):
        script_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "export_search_results.py"
        )
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        self.assertIn(
            "搜索最近一段时间内的相关笔记并导出到 Obsidian",
            result.stdout,
        )

    def test_export_counts_must_be_positive(self):
        from argparse import ArgumentTypeError

        try:
            from scripts.export_search_results import positive_int
        except ImportError:
            self.fail("尚未实现导出数量正整数校验")

        self.assertEqual(positive_int("3"), 3)
        with self.assertRaises(ArgumentTypeError):
            positive_int("0")
        with self.assertRaises(ArgumentTypeError):
            positive_int("-1")

    def test_export_limit_accepts_all_as_unbounded(self):
        from scripts.export_search_results import export_limit

        self.assertIsNone(export_limit("all"))
        self.assertEqual(export_limit("12"), 12)


if __name__ == "__main__":
    unittest.main()
