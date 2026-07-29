import unittest
from pathlib import Path

from scripts.reclassify_selected_materials import (
    audit_vault,
    classify_document,
    create_review_snapshot,
    execute_review,
    validate_links,
)
from tests.support import workspace_temp_dir


class ClassificationTests(unittest.TestCase):
    def test_quant_keyword_does_not_make_vehicle_article_quant(self):
        result = classify_document(
            "10000辆氢能两轮车下线",
            "这种车型已经迈入规模化阶段，累计骑行订单超过三百万。",
            "Quant",
        )

        self.assertEqual(result.decision, "unclassified")
        self.assertIsNone(result.target_domain)

    def test_marriage_cashflow_article_moves_from_health_to_relationships(self):
        result = classify_document(
            "2026年最有种的男人是什么样子",
            (
                "计划明年结婚，彩礼、婚房和装修把一个男人未来三十年的现金流"
                "质押给婚姻共同体。文章讨论婚姻观念、男性责任和伴侣关系。"
            ),
            "健康医学",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "两性情感")

    def test_linux_foundation_article_stays_in_software_engineering(self):
        result = classify_document(
            "Linux 内核社区确立接班人计划",
            (
                "Linux 内核维护者制定连续性计划，涉及代码合并、版本维护、"
                "开源社区治理和软件开发流程。"
            ),
            "软件工程",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "软件工程")

    def test_ai_article_is_not_moved_by_health_examples_in_body(self):
        result = classify_document(
            "Anthropic CEO谈AI安全与模型治理",
            (
                "文章主旨是人工智能模型安全。文中举例提到药物、癌症和健康风险，"
                "但核心仍是大模型、Claude、训练和治理。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_investment_mentions_do_not_reclassify_unrelated_industry_news(self):
        result = classify_document(
            "120秒稳态运行！中国核聚变再突破",
            (
                "全文介绍托卡马克和聚变发电技术。结尾引用中信证券观点，"
                "提到金融机构关注产业投资机会。"
            ),
            "AI",
        )

        self.assertNotEqual(result.target_domain, "投资理财")

    def test_single_fund_word_does_not_reclassify_book_note(self):
        result = classify_document(
            "微信读书",
            "介绍阅读软件、书架和读书习惯，附带一本基金入门书的例子。",
            "AI",
        )

        self.assertNotEqual(result.target_domain, "投资理财")

    def test_specific_quant_title_stays_quant_despite_finance_terms(self):
        result = classify_document(
            "量化金融研报合集：多因子与回测",
            "内容同时讨论金融市场、证券、基金、股票和量化交易。",
            "Quant",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "Quant")

    def test_markdown_link_title_with_quant_stays_quant(self):
        result = classify_document(
            "[GPT-6也救不了平庸策略：Vibe Quant 的反思](https://example.com)",
            "讨论量化研究、策略回测、因子和大模型的交叉实践。",
            "Quant",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "Quant")

    def test_relationship_story_stays_relationship_despite_hospital_words(self):
        result = classify_document(
            "女护士出轨医生，老公向医院反映",
            "文章主旨是夫妻婚姻、出轨和伴侣冲突，事件发生在医院。",
            "两性情感",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "两性情感")

    def test_cpp_article_moves_from_ai_to_software_engineering(self):
        result = classify_document(
            "40年翘首，C++之父编程经典重磅上新",
            "介绍程序设计、编程语言、代码示例和软件开发。",
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "软件工程")

    def test_standalone_ai_in_title_keeps_ai_article(self):
        result = classify_document(
            "AI 网红的 Agent 暴露在公网",
            "介绍人工智能 Agent 的安全风险和大模型应用。",
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_open_source_model_title_stays_ai(self):
        result = classify_document(
            "11B的成本跑出196B的智商，这个国产开源模型效率离谱",
            "介绍模型推理、参数规模和训练效率。",
            "AI",
        )
        self.assertEqual(result.decision, "keep")

    def test_named_trading_strategy_stays_quant(self):
        result = classify_document(
            "9秒狙击手策略：网友分享的翻倍神器",
            "源码拆解交易入场、止损、收益和历史行情表现。",
            "Quant",
        )
        self.assertEqual(result.decision, "keep")

    def test_bmi_research_stays_health(self):
        result = classify_document(
            "35岁，是体重上的一道坎？BMI呈上升趋势",
            "研究脂肪细胞、代谢、体重和健康风险。",
            "健康医学",
        )
        self.assertEqual(result.decision, "keep")

    def test_communication_psychology_stays_relationships(self):
        result = classify_document(
            "为什么你总是忍不住想把话摊开讲清楚",
            "讨论沟通、情绪、关系冲突和心理边界。",
            "两性情感",
        )
        self.assertEqual(result.decision, "keep")

    def test_saving_habit_stays_investment(self):
        result = classify_document(
            "每天少花27.4元，一年就能多存1万块",
            "介绍储蓄、预算、现金流和个人理财。",
            "投资理财",
        )
        self.assertEqual(result.decision, "keep")


class ReviewExecutionTests(unittest.TestCase):
    def _write_note(self, path, domain, title, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "---",
                    'type: "资料"',
                    f'domain: "{domain}"',
                    'created: "2026-01-02 03:04:05"',
                    'source: "Evernote"',
                    f'source_guid: "{title}-guid"',
                    'status: "待提炼"',
                    "tags: []",
                    "---",
                    "",
                    f"# {title}",
                    "",
                    body,
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_move_updates_domain_copies_asset_and_rebuilds_all_indexes(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = (
                vault
                / "30_精选资料"
                / "健康医学"
                / "2026年01月"
                / "婚姻现金流.md"
            )
            self._write_note(
                source,
                "健康医学",
                "婚姻现金流",
                "婚姻关系正文\n\n![](../_attachments/chart.png)",
            )
            asset = (
                vault
                / "30_精选资料"
                / "健康医学"
                / "_attachments"
                / "chart.png"
            )
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"chart")
            (vault / "30_精选资料" / "AI").mkdir(parents=True)

            execute_review(
                vault,
                moves={
                    Path("健康医学/2026年01月/婚姻现金流.md"):
                    "两性情感"
                },
                trash=(),
                links={},
            )

            destination = (
                vault
                / "30_精选资料"
                / "两性情感"
                / "2026年01月"
                / "婚姻现金流.md"
            )
            self.assertFalse(source.exists())
            self.assertIn('domain: "两性情感"', destination.read_text("utf-8"))
            self.assertEqual(
                (
                    vault
                    / "30_精选资料"
                    / "两性情感"
                    / "_attachments"
                    / "chart.png"
                ).read_bytes(),
                b"chart",
            )
            self.assertTrue(
                (vault / "30_精选资料" / "AI" / "目录索引.md").is_file()
            )
            self.assertIn(
                "婚姻现金流",
                (
                    vault
                    / "30_精选资料"
                    / "两性情感"
                    / "目录索引.md"
                ).read_text("utf-8"),
            )

    def test_move_copies_url_encoded_attachment_name(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = (
                vault
                / "30_精选资料"
                / "Quant"
                / "2026年01月"
                / "源码拆解.md"
            )
            self._write_note(
                source,
                "Quant",
                "源码拆解",
                "正文\n\n![](../_attachments/Expression_67%402x.png)",
            )
            asset = (
                vault
                / "30_精选资料"
                / "Quant"
                / "_attachments"
                / "Expression_67@2x.png"
            )
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"expression")

            execute_review(
                vault,
                moves={
                    Path("Quant/2026年01月/源码拆解.md"):
                    "软件工程"
                },
                trash=(),
                links={},
            )

            copied = (
                vault
                / "30_精选资料"
                / "软件工程"
                / "_attachments"
                / "Expression_67@2x.png"
            )
            self.assertEqual(copied.read_bytes(), b"expression")

    def test_managed_links_are_reciprocal_and_resolve_after_move(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            first = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "Agent工程.md"
            )
            second = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "RAG工程.md"
            )
            self._write_note(first, "AI", "Agent工程", "Agent 与 RAG 的工程实践")
            self._write_note(second, "AI", "RAG工程", "RAG 与 Agent 的工程实践")

            execute_review(
                vault,
                moves={},
                trash=(),
                links={
                    Path("AI/2026年01月/Agent工程.md"): (
                        Path("AI/2026年01月/RAG工程.md"),
                    ),
                    Path("AI/2026年01月/RAG工程.md"): (
                        Path("AI/2026年01月/Agent工程.md"),
                    ),
                },
            )

            self.assertEqual(validate_links(vault), ())
            self.assertIn(
                "[[30_精选资料/AI/2026年01月/RAG工程|RAG工程]]",
                first.read_text("utf-8"),
            )
            self.assertIn(
                "[[30_精选资料/AI/2026年01月/Agent工程|Agent工程]]",
                second.read_text("utf-8"),
            )

    def test_validation_accepts_existing_targets_with_markdown_suffix(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            first = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "一.md"
            )
            second = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "二.md"
            )
            self._write_note(
                first,
                "AI",
                "一",
                (
                    "正文\n\n## 相关笔记\n\n"
                    "<!-- llmwiki:auto-links:start -->\n"
                    "- [[30_精选资料/AI/2026年01月/二.md|二]]\n"
                    "<!-- llmwiki:auto-links:end -->\n"
                ),
            )
            self._write_note(
                second,
                "AI",
                "二",
                (
                    "正文\n\n## 相关笔记\n\n"
                    "<!-- llmwiki:auto-links:start -->\n"
                    "- [[30_精选资料/AI/2026年01月/一.md|一]]\n"
                    "<!-- llmwiki:auto-links:end -->\n"
                ),
            )

            self.assertEqual(validate_links(vault), ())

    def test_audit_covers_every_document_and_reports_move_evidence(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            wrong = (
                vault
                / "30_精选资料"
                / "健康医学"
                / "2026年01月"
                / "婚姻责任.md"
            )
            self._write_note(
                wrong,
                "健康医学",
                "婚姻责任",
                "文章讨论夫妻、伴侣、彩礼和婚姻共同体。",
            )
            correct = (
                vault
                / "30_精选资料"
                / "软件工程"
                / "2026年01月"
                / "持续集成.md"
            )
            self._write_note(
                correct,
                "软件工程",
                "持续集成",
                "软件开发团队使用代码测试、版本控制和持续集成。",
            )

            report = audit_vault(vault)

            self.assertEqual(report["document_count"], 2)
            self.assertEqual(report["decision_counts"], {"keep": 1, "move": 1})
            moved = next(
                item for item in report["documents"]
                if item["decision"] == "move"
            )
            self.assertEqual(moved["path"], "健康医学/2026年01月/婚姻责任.md")
            self.assertEqual(moved["target_domain"], "两性情感")
            self.assertIn("婚姻", moved["evidence"])

    def test_destination_conflict_stops_before_any_source_is_changed(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "同名.md"
            )
            destination = (
                vault / "30_精选资料" / "软件工程" / "2026年01月" / "同名.md"
            )
            earlier_source = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "先处理.md"
            )
            self._write_note(source, "AI", "同名", "源内容")
            self._write_note(destination, "软件工程", "同名", "目标内容")
            self._write_note(earlier_source, "AI", "先处理", "必须保持")

            with self.assertRaises(FileExistsError):
                execute_review(
                    vault,
                    moves={
                        Path("AI/2026年01月/先处理.md"): "软件工程",
                        Path("AI/2026年01月/同名.md"): "软件工程",
                    },
                    trash=(),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertTrue(earlier_source.is_file())
            self.assertIn("源内容", source.read_text("utf-8"))
            self.assertIn("目标内容", destination.read_text("utf-8"))

    def test_trash_copy_preserves_referenced_attachment(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "域外.md"
            )
            self._write_note(
                source,
                "AI",
                "域外",
                "域外正文\n\n![](../_attachments/picture.png)",
            )
            asset = (
                vault / "30_精选资料" / "AI" / "_attachments" / "picture.png"
            )
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"picture")

            execute_review(
                vault,
                moves={},
                trash=(Path("AI/2026年01月/域外.md"),),
                links={},
            )

            self.assertEqual(
                (
                    vault
                    / "99_废纸篓"
                    / "30_精选资料"
                    / "AI"
                    / "_attachments"
                    / "picture.png"
                ).read_bytes(),
                b"picture",
            )

    def test_snapshot_contains_every_changed_markdown_and_index(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "迁移.md"
            )
            self._write_note(source, "AI", "迁移", "正文")
            index = vault / "30_精选资料" / "AI" / "目录索引.md"
            index.write_text("# 旧索引\n", encoding="utf-8")

            archive, manifest = create_review_snapshot(
                vault,
                moves={Path("AI/2026年01月/迁移.md"): "软件工程"},
                trash=(),
                links={},
            )

            import json
            import zipfile

            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(
                    set(zipped.namelist()),
                    {
                        "30_精选资料/AI/2026年01月/迁移.md",
                        "30_精选资料/AI/目录索引.md",
                    },
                )
            payload = json.loads(manifest.read_text("utf-8"))
            self.assertEqual(len(payload["files"]), 2)

    def test_asset_name_collision_uses_hash_name_and_rewrites_reference(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = (
                vault / "30_精选资料" / "健康医学" / "2026年01月" / "迁移.md"
            )
            self._write_note(
                source,
                "健康医学",
                "迁移",
                "正文\n\n![](../_attachments/640.png)",
            )
            source_asset = (
                vault / "30_精选资料" / "健康医学" / "_attachments" / "640.png"
            )
            source_asset.parent.mkdir(parents=True)
            source_asset.write_bytes(b"source-picture")
            occupied = (
                vault / "30_精选资料" / "AI" / "_attachments" / "640.png"
            )
            occupied.parent.mkdir(parents=True)
            occupied.write_bytes(b"different-picture")

            execute_review(
                vault,
                moves={Path("健康医学/2026年01月/迁移.md"): "AI"},
                trash=(),
                links={},
            )

            moved = vault / "30_精选资料" / "AI" / "2026年01月" / "迁移.md"
            rendered = moved.read_text("utf-8")
            self.assertNotIn("../_attachments/640.png)", rendered)
            copied = tuple(
                path
                for path in occupied.parent.glob("640_*.png")
                if path.read_bytes() == b"source-picture"
            )
            self.assertEqual(len(copied), 1)
            self.assertIn(f"../_attachments/{copied[0].name})", rendered)


if __name__ == "__main__":
    unittest.main()
