import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote
from unittest.mock import patch
import zipfile

from scripts.reclassify_selected_materials import (
    _is_within,
    audit_vault,
    classify_document,
    create_review_snapshot,
    default_report_path,
    execute_review,
    load_review_decisions,
    main,
    validate_links,
    verify_review_results,
)
from tests.support import create_directory_link_or_skip, workspace_temp_dir


REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_DOMAINS = (
    "AI",
    "Quant",
    "信息技术",
    "投资理财",
    "知识管理",
    "健康医学",
    "中医",
    "两性情感",
    "个人成长",
    "科技产业",
    "自然科学",
    "文史社政",
)


class ClassificationTests(unittest.TestCase):
    def test_specific_new_domains_override_incidental_old_domain_terms(self):
        cases = (
            (
                "自然科学中的机器学习",
                (
                    "用机器学习分析天文学观测数据，重点推导行星轨道、"
                    "经典力学和天体物理。"
                ),
                "AI",
                "自然科学",
            ),
            (
                "女权运动与公共政策",
                (
                    "文章研究女性主义、女权运动、政治制度、社会阶层和"
                    "公共政策。"
                ),
                "两性情感",
                "文史社政",
            ),
        )

        for title, body, current_domain, expected in cases:
            with self.subTest(expected=expected):
                result = classify_document(title, body, current_domain)
                self.assertEqual(result.decision, "move")
                self.assertEqual(result.target_domain, expected)

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
            "信息技术",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "信息技术")

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

    def test_anthropic_title_keeps_ai_when_body_mentions_software(self):
        result = classify_document(
            "Anthropic万字爆火长文的三个判断，以及一个值得警惕的阳谋",
            (
                "文章分析 Claude 与大模型竞争，同时多次讨论软件、"
                "代码、数据库、开发、测试、部署和系统架构。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_gpt_coding_title_keeps_ai_when_software_score_is_close(self):
        result = classify_document(
            "GPT-5.5和Opus 4.8都搞不定的Bug，被Fable 5一晚上解决",
            (
                "比较 GPT 与其他大模型解决代码缺陷的能力，正文包含"
                "数据库、测试、部署、接口和软件开发细节。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_ai_business_strategy_is_not_moved_by_incidental_software_terms(self):
        result = classify_document(
            "卖铲子不再是好生意",
            (
                "很多创业者在AI时代选择做工具，服务律师、程序员和设计师。"
                "文章讨论大模型重构产业分工，以及AI改变供需、AI重构服务关系；"
                "正文举例软件开发、编程、软件、代码、测试和部署，"
                "只是为了说明商业模式。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_ai_video_generator_is_not_moved_by_open_source_project_label(self):
        result = classify_document(
            "开源项目爆火，输入一句话就能全自动出视频",
            (
                "AI团队发布视频生成工具，能够用大模型写文案、生成画面、"
                "语音和背景音乐，再自动合成视频。项目在GitHub提供源码和API。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_vibe_coding_article_stays_ai(self):
        result = classify_document(
            "胡彦斌苦修Vibe Coding，还上架了APP",
            (
                "作者用AI辅助编程完成应用，大模型生成代码并反复修复Bug，"
                "正文也介绍JavaScript、数据库、测试、部署和软件开发。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_andrew_ng_loop_engineering_article_stays_ai(self):
        result = classify_document(
            "吴恩达对 Loop Engineering 的理解真深刻",
            (
                "Andrew Ng讨论Agent自主写代码、调试和修复Bug，"
                "分析AI参与软件开发后形成的多层反馈循环。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_ai_accelerated_product_development_stays_in_software(self):
        result = classify_document(
            "AI让开发快了10倍，为什么好产品没有多10倍",
            (
                "产品经理用AI快速开发数据工具，但用户并不需要。"
                "文章讨论需求验证、产品体验、技术评估、开发排期和项目管理，"
                "重点是软件产品是否解决真实问题。"
            ),
            "信息技术",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "信息技术")

    def test_binance_alpha_reward_article_is_investment_not_quant(self):
        result = classify_document(
            "停更几个月的币安 Alpha，竟然又开始赚钱了",
            (
                "记录币安用户活动与代币奖励，围绕加密货币行情、"
                "账户收益和币圈体验。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "投资理财")

    def test_general_time_series_article_stays_ai(self):
        result = classify_document(
            "解决现阶段时间序列所遇问题的方法",
            (
                "使用机器学习、深度学习、Transformer 和神经网络"
                "处理时间序列预测问题。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_ethereum_title_keeps_investment_despite_ai_discussion(self):
        result = classify_document(
            "以太坊基金会一口气离开 54 人！",
            (
                "文章主要记录基金会人员调整。后半部分比较 AI 公司、"
                "大模型、Agent 和机器学习团队的人才流动。"
            ),
            "投资理财",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "投资理财")

    def test_intraday_reversal_strategy_stays_quant(self):
        result = classify_document(
            "为什么股票最后几分钟的价格走势更重要？一个日内截面反转策略",
            (
                "使用股票历史行情做因子回测，生成交易信号，"
                "比较策略收益、最大回撤和实盘表现。"
            ),
            "Quant",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "Quant")

    def test_trading_timeframe_method_moves_from_investment_to_quant(self):
        result = classify_document(
            "真正能赚钱的时间周期，只有一个（99%的交易者一开始就选错了）",
            (
                "比较5分钟、1小时、日线和周线交易方式，"
                "分析市场噪音、入场时机、交易逻辑与持续盈利方法。"
            ),
            "投资理财",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "Quant")

    def test_machine_learning_factor_research_moves_to_quant(self):
        result = classify_document(
            "基于SHAP与XGBoost的中国A股可解释因子分解",
            (
                "使用机器学习解释多因子信号，进行历史回测，"
                "比较因子收益、最大回撤和策略表现。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "Quant")

    def test_ai_quant_researcher_moves_to_more_specific_quant_domain(self):
        result = classify_document(
            "XALPHA：AI量化研究员——研报理解、策略挖掘与代码生成",
            (
                "系统大量使用AI、LLM、机器学习、智能体、Agent和大模型，"
                "通过AI理解量化研报、挖掘Alpha因子并生成交易策略代码。"
                "正文反复介绍AI Agent架构，最后完成历史回测和收益评估。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "Quant")

    def test_claude_options_quant_analyst_prefers_quant_over_investment(self):
        result = classify_document(
            "我把 Claude 爆改成了期权量化分析师",
            (
                "通过MCP、代码和Claude构建智能交易界面，"
                "分析期权链、仓位、Delta、交易策略与策略收益。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "Quant")

    def test_explicit_quant_analysis_moves_from_broader_investment_domain(self):
        result = classify_document(
            "期权量化分析师：自动生成策略并完成回测",
            (
                "分析期权链、仓位和收益，同时生成量化交易策略、"
                "历史回测、交易信号与最大回撤报告。"
            ),
            "投资理财",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "Quant")

    def test_ai_golden_age_phrase_is_not_treated_as_gold_investment(self):
        result = classify_document(
            "让它崩：AI泡沫之后，黄金时代才会开始",
            (
                "文章讨论人工智能基础设施、数据中心、大模型产业周期，"
                "并用铁路和互联网泡沫解释AI技术扩散。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "AI")

    def test_programmer_resignation_story_moves_to_personal_growth(self):
        result = classify_document(
            "干程序员久了，为什么总有干不下去想辞职的感觉",
            (
                "从职业规划、工作倦怠、人生选择和自我反思角度，"
                "讨论如何面对辞职与转型。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "个人成长")

    def test_resignation_compensation_options_move_to_personal_growth(self):
        result = classify_document(
            "1700天无过错被动离职：绩效期权被清零",
            (
                "记录被动离职、职业转型、劳动经历和找工作计划；"
                "期权只是离职补偿的一项。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "个人成长")

    def test_marriage_conflict_beats_job_loss_signal(self):
        result = classify_document(
            "才失业一周，天天被媳妇催找工作，后悔结婚",
            (
                "重点讨论夫妻沟通、婚姻冲突、伴侣支持和情感关系；"
                "失业是矛盾发生的背景。"
            ),
            "AI",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "两性情感")

    def test_crypto_hiring_article_moves_to_personal_growth(self):
        result = classify_document(
            "a16z：不要只看学历资历，找到更有加密精神的招聘方法",
            (
                "文章讨论招聘、职业经历、学历筛选和人才成长，"
                "加密行业只是招聘场景。"
            ),
            "投资理财",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "个人成长")

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
        self.assertEqual(result.target_domain, "信息技术")

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

    def test_workplace_stroke_story_stays_health(self):
        result = classify_document(
            "大厂员工被约谈后，在工位上脑梗了",
            (
                "文章记录公司约谈、裁员压力、职业选择和找工作焦虑，"
                "员工最终在工位突发脑梗。"
            ),
            "健康医学",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "健康医学")

    def test_liver_soothing_nodule_remedy_moves_to_tcm(self):
        result = classify_document(
            "这个能消灭结节的小果子，舒肝又散结",
            (
                "文章依据黄帝内经和五运六气理论，讨论气机、寒湿、"
                "疏肝理气与中药食疗方法。"
            ),
            "健康医学",
        )

        self.assertEqual(result.decision, "move")
        self.assertEqual(result.target_domain, "中医")

    def test_depression_story_stays_health(self):
        result = classify_document(
            "朋友得了抑郁症，还不敢离开大厂",
            (
                "文章记录职业压力、离职顾虑、找工作和人生选择，"
                "朋友已经确诊抑郁症。"
            ),
            "健康医学",
        )

        self.assertEqual(result.decision, "keep")
        self.assertEqual(result.target_domain, "健康医学")

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


class ReviewDecisionTests(unittest.TestCase):
    def _write_decisions(self, root, payload):
        path = root / "decisions.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def test_decisions_reject_move_trash_overlap(self):
        payload = {
            "moves": {"AI/2026年01月/文章.md": "信息技术"},
            "trash": ["AI/2026年01月/文章.md"],
            "links": {},
        }
        with workspace_temp_dir() as root:
            with self.assertRaises(ValueError):
                load_review_decisions(self._write_decisions(root, payload))

    def test_decisions_require_reciprocal_links(self):
        payload = {
            "moves": {},
            "trash": [],
            "links": {
                "AI/2026年01月/一.md": ["AI/2026年01月/二.md"],
            },
        }
        with workspace_temp_dir() as root:
            with self.assertRaises(ValueError):
                load_review_decisions(self._write_decisions(root, payload))

    def test_decisions_reject_unknown_or_escaping_move_domain(self):
        with workspace_temp_dir() as root:
            for target_domain in ("未知领域", "../逃逸目录"):
                with self.subTest(target_domain=target_domain):
                    payload = {
                        "moves": {
                            "AI/2026年01月/文章.md": target_domain,
                        },
                        "trash": [],
                        "links": {},
                    }
                    with self.assertRaises(ValueError):
                        load_review_decisions(
                            self._write_decisions(root, payload)
                        )

    def test_decisions_require_exact_schema_and_canonical_document_paths(self):
        invalid_payloads = (
            {
                "move": {"AI/2026年01月/文章.md": "信息技术"},
                "trash": [],
                "links": {},
            },
            {"moves": {}, "trash": []},
            {
                "moves": {"AI/文章.md": "信息技术"},
                "trash": [],
                "links": {},
            },
            {
                "moves": {},
                "trash": ["未知领域/2026年01月/文章.md"],
                "links": {},
            },
            {
                "moves": {},
                "trash": ["AI/2026-01/文章.md"],
                "links": {},
            },
            {
                "moves": {},
                "trash": ["AI/2026年13月/文章.md"],
                "links": {},
            },
            {
                "moves": {},
                "trash": [r"AI\2026年01月\文章.md"],
                "links": {},
            },
            {
                "moves": {},
                "trash": ["AI/2026年01月/目录索引.md"],
                "links": {},
            },
        )
        with workspace_temp_dir() as root:
            for payload in invalid_payloads:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    load_review_decisions(self._write_decisions(root, payload))

    def test_decisions_reject_duplicate_trash_and_duplicate_json_keys(self):
        with workspace_temp_dir() as root:
            duplicate_trash = {
                "moves": {},
                "trash": [
                    "AI/2026年01月/文章.md",
                    "AI/2026年01月/文章.md",
                ],
                "links": {},
            }
            with self.assertRaises(ValueError):
                load_review_decisions(
                    self._write_decisions(root, duplicate_trash)
                )

            duplicate_key = root / "duplicate-key.json"
            duplicate_key.write_text(
                '{"moves": {}, "moves": {}, "trash": [], "links": {}}\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_review_decisions(duplicate_key)


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
                    "信息技术"
                },
                trash=(),
                links={},
            )

            copied = (
                vault
                / "30_精选资料"
                / "信息技术"
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
                / "信息技术"
                / "2026年01月"
                / "持续集成.md"
            )
            self._write_note(
                correct,
                "信息技术",
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
                vault / "30_精选资料" / "信息技术" / "2026年01月" / "同名.md"
            )
            earlier_source = (
                vault / "30_精选资料" / "AI" / "2026年01月" / "先处理.md"
            )
            self._write_note(source, "AI", "同名", "源内容")
            self._write_note(destination, "信息技术", "同名", "目标内容")
            self._write_note(earlier_source, "AI", "先处理", "必须保持")

            with self.assertRaises(FileExistsError):
                execute_review(
                    vault,
                    moves={
                        Path("AI/2026年01月/先处理.md"): "信息技术",
                        Path("AI/2026年01月/同名.md"): "信息技术",
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
                moves={Path("AI/2026年01月/迁移.md"): "信息技术"},
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

    def test_move_batch_reuses_equal_assets_and_hashes_different_content(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            first = Path("AI/2026年01月/批次甲.md")
            second = Path("Quant/2026年01月/批次乙.md")
            equal = Path("知识管理/2026年01月/批次同内容.md")
            for relative, domain, title in (
                (first, "AI", "批次甲"),
                (second, "Quant", "批次乙"),
                (equal, "知识管理", "批次同内容"),
            ):
                self._write_note(
                    selected / relative,
                    domain,
                    title,
                    "正文\n\n![](../_attachments/shared.png)",
                )
            for domain, payload in (
                ("AI", b"content-a"),
                ("Quant", b"content-b"),
                ("知识管理", b"content-a"),
            ):
                asset = selected / domain / "_attachments/shared.png"
                asset.parent.mkdir(parents=True)
                asset.write_bytes(payload)

            try:
                execute_review(
                    vault,
                    moves={
                        first: "信息技术",
                        second: "信息技术",
                        equal: "信息技术",
                    },
                    trash=(),
                    links={},
                )
            except FileExistsError as exc:
                self.fail(f"批次内附件冲突不应拒绝合法 move: {exc}")

            target_assets = selected / "信息技术/_attachments"
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in target_assets.glob("shared*.png")
                },
                {
                    "shared.png": b"content-a",
                    "shared_6ce5fb87f75c.png": b"content-b",
                },
            )
            self.assertIn(
                "../_attachments/shared.png",
                (
                    selected / "信息技术/2026年01月/批次甲.md"
                ).read_text(encoding="utf-8"),
            )
            self.assertIn(
                "../_attachments/shared_6ce5fb87f75c.png",
                (
                    selected / "信息技术/2026年01月/批次乙.md"
                ).read_text(encoding="utf-8"),
            )
            self.assertIn(
                "../_attachments/shared.png",
                (
                    selected / "信息技术/2026年01月/批次同内容.md"
                ).read_text(encoding="utf-8"),
            )

    def test_trash_batch_reuses_equal_assets_and_hashes_different_content(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            first = Path("AI/2026年01月/废纸批次甲.md")
            second = Path("AI/2026年01月/废纸批次乙.md")
            equal = Path("AI/2026年01月/废纸批次同内容.md")
            for relative, asset_group, title in (
                (first, "a", "废纸批次甲"),
                (second, "b", "废纸批次乙"),
                (equal, "c", "废纸批次同内容"),
            ):
                self._write_note(
                    selected / relative,
                    "AI",
                    title,
                    f"正文\n\n![](../_attachments/{asset_group}/shared.png)",
                )
            for asset_group, payload in (
                ("a", b"content-a"),
                ("b", b"content-b"),
                ("c", b"content-a"),
            ):
                asset = (
                    selected
                    / "AI"
                    / "_attachments"
                    / asset_group
                    / "shared.png"
                )
                asset.parent.mkdir(parents=True)
                asset.write_bytes(payload)

            try:
                execute_review(
                    vault,
                    moves={},
                    trash=(first, second, equal),
                    links={},
                )
            except FileExistsError as exc:
                self.fail(f"批次内附件冲突不应拒绝合法 trash: {exc}")

            trash_root = vault / "99_废纸篓/30_精选资料/AI"
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in (trash_root / "_attachments").glob(
                        "shared*.png"
                    )
                },
                {
                    "shared.png": b"content-a",
                    "shared_6ce5fb87f75c.png": b"content-b",
                },
            )
            self.assertIn(
                "../_attachments/shared.png",
                (trash_root / "2026年01月/废纸批次甲.md").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertIn(
                "../_attachments/shared_6ce5fb87f75c.png",
                (trash_root / "2026年01月/废纸批次乙.md").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertIn(
                "../_attachments/shared.png",
                (trash_root / "2026年01月/废纸批次同内容.md").read_text(
                    encoding="utf-8"
                ),
            )


    def test_move_preflight_rejects_destination_outside_selected_root(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source = vault / "30_精选资料/AI/2026年01月/待移动.md"
            self._write_note(source, "AI", "待移动", "原始正文")

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={Path("AI/2026年01月/待移动.md"): "../逃逸目录"},
                    trash=(),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse((vault / "逃逸目录").exists())

    def test_move_remaps_both_ends_of_controlled_links(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/迁移资料.md")
            neighbor = Path("AI/2026年01月/关联资料.md")
            self._write_note(selected / moved, "AI", "迁移资料", "迁移正文")
            self._write_note(selected / neighbor, "AI", "关联资料", "关联正文")

            execute_review(
                vault,
                moves={moved: "信息技术"},
                trash=(),
                links={moved: (neighbor,), neighbor: (moved,)},
            )

            moved_note = selected / "信息技术/2026年01月/迁移资料.md"
            neighbor_note = selected / neighbor
            self.assertEqual(validate_links(vault), ())
            self.assertIn(
                "[[30_精选资料/AI/2026年01月/关联资料|关联资料]]",
                moved_note.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "[[30_精选资料/信息技术/2026年01月/迁移资料|迁移资料]]",
                neighbor_note.read_text(encoding="utf-8"),
            )

    def test_invalid_link_endpoint_stops_before_move_or_trash(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/待移动.md")
            discarded = Path("AI/2026年01月/待废弃.md")
            neighbor = Path("AI/2026年01月/关联资料.md")
            missing = Path("AI/2026年01月/不存在.md")
            self._write_note(selected / moved, "AI", "待移动", "移动前正文")
            self._write_note(selected / discarded, "AI", "待废弃", "废弃前正文")
            self._write_note(selected / neighbor, "AI", "关联资料", "关联正文")

            with self.assertRaises(FileNotFoundError):
                execute_review(
                    vault,
                    moves={moved: "信息技术"},
                    trash=(discarded,),
                    links={neighbor: (missing,), missing: (neighbor,)},
                )

            self.assertTrue((selected / moved).is_file())
            self.assertTrue((selected / discarded).is_file())
            self.assertFalse(
                (vault / "99_废纸篓/30_精选资料/AI/2026年01月/待废弃.md").exists()
            )

    def test_duplicate_planned_move_destination_stops_before_any_write(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            ai_source = Path("AI/2026年01月/同名资料.md")
            quant_source = Path("Quant/2026年01月/同名资料.md")
            self._write_note(selected / ai_source, "AI", "AI同名", "AI 原始正文")
            self._write_note(
                selected / quant_source, "Quant", "Quant同名", "Quant 原始正文"
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={ai_source: "信息技术", quant_source: "信息技术"},
                    trash=(),
                    links={},
                )

            self.assertTrue((selected / ai_source).is_file())
            self.assertTrue((selected / quant_source).is_file())
            self.assertFalse(
                (selected / "信息技术/2026年01月/同名资料.md").exists()
            )

    def test_selected_root_directory_link_escape_is_rejected_before_delete(self):
        with workspace_temp_dir() as root:
            vault = root / "vault"
            outside = root / "outside-selected"
            vault.mkdir()
            outside.mkdir()
            (vault / ".obsidian").mkdir()
            source_relative = Path("AI/2026年01月/外部资料.md")
            outside_source = outside / source_relative
            self._write_note(
                outside_source,
                "AI",
                "外部资料",
                "不得通过目录链接读取或删除。",
            )
            create_directory_link_or_skip(
                self,
                vault / "30_精选资料",
                outside,
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={},
                    trash=(source_relative,),
                    links={},
                )

            self.assertTrue(outside_source.is_file())
            self.assertFalse(
                (
                    vault
                    / "99_废纸篓"
                    / "30_精选资料"
                    / source_relative
                ).exists()
            )

    def test_trash_root_directory_link_escape_is_rejected_before_write(self):
        with workspace_temp_dir() as root:
            vault = root / "vault"
            outside = root / "outside-trash"
            vault.mkdir()
            outside.mkdir()
            (vault / ".obsidian").mkdir()
            source_relative = Path("AI/2026年01月/待废弃.md")
            source = vault / "30_精选资料" / source_relative
            self._write_note(source, "AI", "待废弃", "仍须保持在 Vault 内。")
            trash_parent = vault / "99_废纸篓"
            trash_parent.mkdir()
            create_directory_link_or_skip(
                self,
                trash_parent / "30_精选资料",
                outside,
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={},
                    trash=(source_relative,),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse((outside / source_relative).exists())

    def test_target_attachment_link_escape_is_rejected_before_snapshot(self):
        with workspace_temp_dir() as root:
            vault = root / "vault"
            outside = root / "outside-assets"
            vault.mkdir()
            outside.mkdir()
            (vault / ".obsidian").mkdir()
            source_relative = Path("AI/2026年01月/附件资料.md")
            source = vault / "30_精选资料" / source_relative
            self._write_note(
                source,
                "AI",
                "附件资料",
                "正文\n\n![](../_attachments/picture.png)",
            )
            source_asset = vault / "30_精选资料/AI/_attachments/picture.png"
            source_asset.parent.mkdir(parents=True)
            source_asset.write_bytes(b"managed-picture")
            target_domain = vault / "30_精选资料/信息技术"
            target_domain.mkdir(parents=True)
            create_directory_link_or_skip(
                self,
                target_domain / "_attachments",
                outside,
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={source_relative: "信息技术"},
                    trash=(),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertEqual(tuple(outside.iterdir()), ())
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_move_rejects_target_domain_junction_to_another_domain(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            relative = Path("AI/2026年01月/跨领域根.md")
            source = selected / relative
            self._write_note(source, "AI", "跨领域根", "不得写入其他领域。")
            physical_domain = selected / "Quant"
            physical_domain.mkdir(parents=True)
            create_directory_link_or_skip(
                self,
                selected / "信息技术",
                physical_domain,
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={relative: "信息技术"},
                    trash=(),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse(
                (physical_domain / "2026年01月/跨领域根.md").exists()
            )
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_trash_rejects_domain_mirror_junction_to_another_domain(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            relative = Path("AI/2026年01月/废纸篓领域根.md")
            source = selected / relative
            self._write_note(
                source,
                "AI",
                "废纸篓领域根",
                "不得写入其他领域镜像。",
            )
            trash_root = vault / "99_废纸篓/30_精选资料"
            physical_domain = trash_root / "Quant"
            physical_domain.mkdir(parents=True)
            create_directory_link_or_skip(
                self,
                trash_root / "AI",
                physical_domain,
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={},
                    trash=(relative,),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse(
                (physical_domain / "2026年01月/废纸篓领域根.md").exists()
            )
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_move_rejects_external_absolute_encoded_escape_and_missing_assets(
        self,
    ):
        with workspace_temp_dir() as root:
            outside = root / "outside-secret.bin"
            outside.write_bytes(b"outside-secret")
            raw_targets = (
                "../../../../outside-secret.bin",
                "../_attachments/%2e%2e/%2e%2e/%2e%2e/"
                "outside-secret.bin",
                outside.resolve().as_posix(),
                "../_attachments/missing.bin",
            )
            for raw_target in raw_targets:
                with self.subTest(raw_target=raw_target):
                    vault = root / f"vault-{raw_targets.index(raw_target)}"
                    vault.mkdir()
                    (vault / ".obsidian").mkdir()
                    source_relative = Path("AI/2026年01月/附件边界.md")
                    source = vault / "30_精选资料" / source_relative
                    self._write_note(
                        source,
                        "AI",
                        "附件边界",
                        f"正文\n\n![]({raw_target})",
                    )

                    with self.assertRaises((ValueError, FileNotFoundError)):
                        execute_review(
                            vault,
                            moves={source_relative: "信息技术"},
                            trash=(),
                            links={},
                        )

                    self.assertTrue(source.is_file())
                    self.assertFalse(
                        (vault / ".state/yinxiang-notes/snapshots").exists()
                    )

    def test_encoded_asset_collision_rewrites_to_correct_hashed_content(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            source_relative = Path("Quant/2026年01月/编码附件.md")
            source = vault / "30_精选资料" / source_relative
            self._write_note(
                source,
                "Quant",
                "编码附件",
                "正文\n\n![](../_attachments/Expression%2067%402x.png)",
            )
            source_asset = (
                vault
                / "30_精选资料"
                / "Quant"
                / "_attachments"
                / "Expression 67@2x.png"
            )
            source_asset.parent.mkdir(parents=True)
            source_asset.write_bytes(b"correct-content")
            occupied = (
                vault
                / "30_精选资料"
                / "信息技术"
                / "_attachments"
                / "Expression 67@2x.png"
            )
            occupied.parent.mkdir(parents=True)
            occupied.write_bytes(b"wrong-content")

            execute_review(
                vault,
                moves={source_relative: "信息技术"},
                trash=(),
                links={},
            )

            moved = vault / "30_精选资料/信息技术/2026年01月/编码附件.md"
            rendered = moved.read_text(encoding="utf-8")
            raw_target = next(
                target
                for target in re.findall(r"\]\(([^)]+)\)", rendered)
                if "_attachments" in target
            )
            referenced = (moved.parent / unquote(raw_target)).resolve()
            self.assertNotEqual(referenced, occupied)
            self.assertRegex(referenced.name, r"_[0-9a-f]{12}\.png$")
            self.assertEqual(referenced.read_bytes(), b"correct-content")
            report = verify_review_results(
                vault,
                {source_relative: "信息技术"},
                (),
                {},
            )
            self.assertTrue(report["ok"], report["issues"])

    def test_all_frontmatter_is_rendered_before_snapshot_or_business_write(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            first = Path("AI/2026年01月/先处理.md")
            second = Path("AI/2026年01月/后失败.md")
            self._write_note(selected / first, "AI", "先处理", "有效正文")
            invalid = selected / second
            invalid.parent.mkdir(parents=True, exist_ok=True)
            invalid.write_text("# 后失败\n\n没有 frontmatter。\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={first: "信息技术", second: "投资理财"},
                    trash=(),
                    links={},
                )

            self.assertTrue((selected / first).is_file())
            self.assertTrue((selected / second).is_file())
            self.assertFalse((selected / "信息技术/2026年01月/先处理.md").exists())
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_body_domain_line_cannot_replace_missing_frontmatter(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            relative = Path("AI/2026年01月/正文伪字段.md")
            source = vault / "30_精选资料" / relative
            source.parent.mkdir(parents=True)
            source.write_text(
                "# 正文伪字段\n\n正文。\ndomain: AI\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={relative: "信息技术"},
                    trash=(),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_index_inputs_are_validated_before_snapshot_or_move(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/待移动.md")
            self._write_note(selected / moved, "AI", "待移动", "有效正文")
            invalid = selected / "Quant/2026年01月/缺少元数据.md"
            invalid.parent.mkdir(parents=True)
            invalid.write_text(
                "---\ntype: 资料\ndomain: Quant\n---\n\n# 缺少元数据\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={moved: "信息技术"},
                    trash=(),
                    links={},
                )

            self.assertTrue((selected / moved).is_file())
            self.assertFalse((selected / "信息技术/2026年01月/待移动.md").exists())
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_execute_review_defensively_rejects_duplicate_trash_before_write(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            relative = Path("AI/2026年01月/重复废弃.md")
            source = vault / "30_精选资料" / relative
            self._write_note(source, "AI", "重复废弃", "必须原子拒绝。")

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={},
                    trash=(relative, relative),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse(
                (vault / "99_废纸篓/30_精选资料" / relative).exists()
            )
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_execute_review_rejects_duplicate_normalized_move_paths(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            relative = Path("AI/2026年01月/重复移动.md")
            source = vault / "30_精选资料" / relative
            self._write_note(source, "AI", "重复移动", "必须原子拒绝。")

            with self.assertRaises(ValueError):
                execute_review(
                    vault,
                    moves={
                        relative: "信息技术",
                        relative.as_posix(): "投资理财",
                    },
                    trash=(),
                    links={},
                )

            self.assertTrue(source.is_file())
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )

    def test_snapshot_excludes_unchanged_assets_and_apply_preserves_sources(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            relative = Path("AI/2026年01月/来源附件.md")
            source = vault / "30_精选资料" / relative
            self._write_note(
                source,
                "AI",
                "来源附件",
                "正文\n\n![](../_attachments/source.png)",
            )
            asset = vault / "30_精选资料/AI/_attachments/source.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"source-stays")

            archive, _ = execute_review(
                vault,
                moves={relative: "信息技术"},
                trash=(),
                links={},
            )

            with zipfile.ZipFile(archive) as zipped:
                names = set(zipped.namelist())
            self.assertNotIn(
                "30_精选资料/AI/_attachments/source.png",
                names,
            )
            self.assertEqual(asset.read_bytes(), b"source-stays")


class ReviewVerificationTests(unittest.TestCase):
    def _write_note(self, path, domain, title, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                (
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
                )
            ),
            encoding="utf-8",
        )

    def _managed_links(self, targets):
        return "\n".join(
            (
                "正文",
                "",
                "## 相关笔记",
                "",
                "<!-- llmwiki:auto-links:start -->",
                *(
                    f"- [[30_精选资料/{target.with_suffix('').as_posix()}|"
                    f"{target.stem}]]"
                    for target in targets
                ),
                "<!-- llmwiki:auto-links:end -->",
            )
        )

    def test_verify_detects_deleted_asset_and_tampered_snapshot_manifest(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/跨域资料.md")
            discarded = Path("AI/2026年01月/废纸资料.md")
            first = Path("AI/2026年01月/双向一.md")
            second = Path("AI/2026年01月/双向二.md")
            self._write_note(
                selected / moved,
                "AI",
                "跨域资料",
                "正文\n\n![](../_attachments/Expression_67%402x.png)",
            )
            self._write_note(selected / discarded, "AI", "废纸资料", "待移除")
            self._write_note(selected / first, "AI", "双向一", "双向资料一")
            self._write_note(selected / second, "AI", "双向二", "双向资料二")
            self._write_note(
                selected / "信息技术/2026年01月/[索引]条目.md",
                "信息技术",
                "[索引]条目",
                "索引转义验证资料",
            )
            asset = selected / "AI/_attachments/Expression_67@2x.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"encoded-attachment")
            moves = {moved: "信息技术"}
            trash = (discarded,)
            links = {first: (second,), second: (first,)}
            snapshot = create_review_snapshot(vault, moves, trash, links)

            execute_review(vault, moves, trash, links)

            report = verify_review_results(vault, moves, trash, links, snapshot)
            self.assertTrue(report["ok"], report["issues"])
            self.assertEqual(report["moves"], 1)
            self.assertEqual(report["trash"], 1)
            self.assertEqual(report["managed_link_notes"], 2)
            self.assertEqual(report["missing_assets"], [])
            self.assertIn("信息技术", report["index_counts"])
            self.assertEqual(report["snapshot_files"], 4)

            copied_asset = (
                selected / "信息技术/_attachments/Expression_67@2x.png"
            )
            copied_asset.unlink()
            missing_asset_report = verify_review_results(
                vault, moves, trash, links, snapshot
            )
            self.assertFalse(missing_asset_report["ok"])
            self.assertIn(
                "30_精选资料/信息技术/_attachments/Expression_67@2x.png",
                "\n".join(missing_asset_report["issues"]),
            )

            copied_asset.write_bytes(b"encoded-attachment")
            archive, manifest = snapshot
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_payload["files"][0]["sha256"] = "0" * 64
            manifest.write_text(
                json.dumps(manifest_payload, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tampered_snapshot_report = verify_review_results(
                vault, moves, trash, links, (archive, manifest)
            )
            self.assertFalse(tampered_snapshot_report["ok"])
            self.assertIn(
                manifest.as_posix(),
                "\n".join(tampered_snapshot_report["issues"]),
            )

    def test_verify_compares_exact_decision_links_and_reports_each_invalid_shape(
        self,
    ):
        first = Path("AI/2026年01月/一.md")
        second = Path("AI/2026年01月/二.md")
        third = Path("AI/2026年01月/三.md")
        fourth = Path("AI/2026年01月/四.md")
        fifth = Path("AI/2026年01月/五.md")
        decisions = {first: (second,), second: (first,)}

        def missing(selected):
            self._write_note(selected / first, "AI", "一", "正文")
            self._write_note(selected / second, "AI", "二", "正文")

        def extra(selected):
            self._write_note(
                selected / third,
                "AI",
                "三",
                self._managed_links((fourth,)),
            )
            self._write_note(
                selected / fourth,
                "AI",
                "四",
                self._managed_links((third,)),
            )

        def duplicate(selected):
            self._write_note(
                selected / first,
                "AI",
                "一",
                self._managed_links((second, second)),
            )

        def self_link(selected):
            self._write_note(
                selected / first,
                "AI",
                "一",
                self._managed_links((first,)),
            )

        def too_many(selected):
            self._write_note(
                selected / first,
                "AI",
                "一",
                self._managed_links((second, third, fourth, fifth)),
            )

        def asymmetric(selected):
            self._write_note(selected / second, "AI", "二", "正文")

        cases = (
            ("缺失", missing, "缺少"),
            ("额外", extra, "额外"),
            ("重复", duplicate, "重复"),
            ("自链", self_link, "自链接"),
            ("超过三条", too_many, "超过 3"),
            ("非对称", asymmetric, "不对称"),
        )
        for name, mutate, marker in cases:
            with self.subTest(case=name), workspace_temp_dir() as vault:
                (vault / ".obsidian").mkdir()
                selected = vault / "30_精选资料"
                for relative in (first, second, third, fourth, fifth):
                    self._write_note(
                        selected / relative,
                        "AI",
                        relative.stem,
                        "正文",
                    )
                execute_review(
                    vault,
                    moves={},
                    trash=(),
                    links=decisions,
                )

                mutate(selected)
                report = verify_review_results(
                    vault,
                    moves={},
                    trash=(),
                    links=decisions,
                )

                self.assertFalse(report["ok"], report)
                self.assertIn(marker, "\n".join(report["issues"]))
                if name == "缺失":
                    self.assertEqual(report["managed_link_notes"], 0)

    def test_verify_uses_same_nine_domain_type_and_month_index_contract(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            self._write_note(
                selected / "AI/2026年01月/资料.md",
                "AI",
                "资料",
                "应进入索引。",
            )
            knowledge = selected / "AI/2026年01月/知识.md"
            self._write_note(knowledge, "AI", "知识", "不应进入资料索引。")
            knowledge.write_text(
                knowledge.read_text(encoding="utf-8").replace(
                    'type: "资料"',
                    'type: "知识"',
                ),
                encoding="utf-8",
            )
            execute_review(vault, moves={}, trash=(), links={})

            report = verify_review_results(vault, {}, (), {})

            self.assertTrue(report["ok"], report["issues"])
            self.assertEqual(set(report["index_counts"]), set(EXPECTED_DOMAINS))
            self.assertEqual(report["index_counts"]["AI"], 1)
            for domain in EXPECTED_DOMAINS:
                self.assertTrue(
                    (selected / domain / "目录索引.md").is_file(),
                    domain,
                )

    def test_verify_rejects_missing_indexes_for_any_managed_domain(self):
        from scripts.knowledge_base import write_knowledge_base_index

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            ai = vault / "30_精选资料/AI"
            ai.mkdir(parents=True)
            write_knowledge_base_index(ai, "AI")

            report = verify_review_results(vault, {}, (), {})

            self.assertFalse(report["ok"])
            self.assertIn(
                "30_精选资料/Quant/目录索引.md",
                "\n".join(report["issues"]),
            )

    def test_verify_reports_invalid_metadata_using_index_generator_contract(self):
        from scripts.knowledge_base import write_knowledge_base_index

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            for domain in EXPECTED_DOMAINS:
                domain_root = selected / domain
                domain_root.mkdir(parents=True)
                write_knowledge_base_index(domain_root, domain)
            invalid = selected / "AI/2026年01月/缺少元数据.md"
            invalid.parent.mkdir(parents=True)
            invalid.write_text(
                "---\ntype: 资料\ndomain: AI\n---\n\n# 缺少元数据\n",
                encoding="utf-8",
            )

            report = verify_review_results(vault, {}, (), {})

            self.assertFalse(report["ok"])
            self.assertIn("缺少 created", "\n".join(report["issues"]))

    def test_verify_rejects_asset_reference_outside_managed_attachment_root(self):
        with workspace_temp_dir() as root:
            vault = root / "vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/越界验证.md")
            self._write_note(selected / moved, "AI", "越界验证", "正文")
            execute_review(
                vault,
                moves={moved: "信息技术"},
                trash=(),
                links={},
            )
            outside = root / "outside.bin"
            outside.write_bytes(b"outside")
            destination = selected / "信息技术/2026年01月/越界验证.md"
            destination.write_text(
                destination.read_text(encoding="utf-8")
                + f"\n![]({outside.resolve().as_posix()})\n",
                encoding="utf-8",
            )

            report = verify_review_results(
                vault,
                {moved: "信息技术"},
                (),
                {},
            )

            self.assertFalse(report["ok"])
            self.assertIn("附件超出受管目录", "\n".join(report["issues"]))

    def test_audit_and_verify_reject_selected_root_directory_link_escape(self):
        with workspace_temp_dir() as root:
            vault = root / "vault"
            outside = root / "outside-selected"
            vault.mkdir()
            outside.mkdir()
            (vault / ".obsidian").mkdir()
            create_directory_link_or_skip(
                self,
                vault / "30_精选资料",
                outside,
            )

            with self.assertRaises(ValueError):
                audit_vault(vault)
            with self.assertRaises(ValueError):
                verify_review_results(vault, {}, (), {})


    def test_verify_rejects_moved_note_with_wrong_frontmatter_domain(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/领域不符.md")
            self._write_note(selected / moved, "AI", "领域不符", "待迁移正文")
            moves = {moved: "信息技术"}

            execute_review(vault, moves, trash=(), links={})
            destination = selected / "信息技术/2026年01月/领域不符.md"
            destination.write_text(
                destination.read_text(encoding="utf-8").replace(
                    'domain: "信息技术"', 'domain: "AI"'
                ),
                encoding="utf-8",
            )

            report = verify_review_results(vault, moves, (), {})

            self.assertFalse(report["ok"])
            self.assertIn(
                "领域不符.md",
                "\n".join(report["issues"]),
            )
            self.assertIn("domain", "\n".join(report["issues"]))

    def test_verify_rejects_body_domain_without_opening_frontmatter(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/伪字段资料.md")
            self._write_note(selected / moved, "AI", "伪字段资料", "待迁移正文")
            moves = {moved: "信息技术"}

            execute_review(vault, moves, trash=(), links={})
            destination = selected / "信息技术/2026年01月/伪字段资料.md"
            destination.write_text(
                "# 伪字段资料\n\n正文中的伪字段不能作为 frontmatter。\n"
                "domain: 信息技术\n",
                encoding="utf-8",
            )

            report = verify_review_results(vault, moves, (), {})

            self.assertFalse(report["ok"])
            self.assertIn("伪字段资料.md", "\n".join(report["issues"]))
            self.assertIn("domain", "\n".join(report["issues"]))

    def test_verify_rejects_domain_inside_frontmatter_block_scalar(self):
        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            selected = vault / "30_精选资料"
            moved = Path("AI/2026年01月/块标量伪字段.md")
            self._write_note(selected / moved, "AI", "块标量伪字段", "待迁移正文")
            moves = {moved: "信息技术"}

            execute_review(vault, moves, trash=(), links={})
            destination = selected / "信息技术/2026年01月/块标量伪字段.md"
            destination.write_text(
                "---\n"
                "notes: |\n"
                '  domain: "信息技术"\n'
                "---\n\n"
                "# 块标量伪字段\n",
                encoding="utf-8",
            )

            report = verify_review_results(vault, moves, (), {})

            self.assertFalse(report["ok"])
            self.assertIn("块标量伪字段.md", "\n".join(report["issues"]))
            self.assertIn("domain", "\n".join(report["issues"]))

    def test_verify_rejects_block_scalar_domain_values(self):
        for indicator in ("|", ">"):
            with self.subTest(indicator=indicator):
                with workspace_temp_dir() as vault:
                    (vault / ".obsidian").mkdir()
                    selected = vault / "30_精选资料"
                    moved = Path("AI/2026年01月/块标量领域.md")
                    self._write_note(
                        selected / moved,
                        "AI",
                        "块标量领域",
                        "待迁移正文",
                    )
                    moves = {moved: "信息技术"}

                    execute_review(vault, moves, trash=(), links={})
                    destination = (
                        selected / "信息技术/2026年01月/块标量领域.md"
                    )
                    destination.write_text(
                        "---\n"
                        f"domain: {indicator}\n"
                        "  信息技术\n"
                        "---\n\n"
                        "# 块标量领域\n",
                        encoding="utf-8",
                    )

                    report = verify_review_results(vault, moves, (), {})

                    self.assertFalse(report["ok"])
                    self.assertIn(
                        "实际 None",
                        "\n".join(report["issues"]),
                    )

    def test_verify_accepts_quoted_and_unquoted_scalar_domains(self):
        for domain_line in ('domain: "信息技术"', "domain: 信息技术"):
            with self.subTest(domain_line=domain_line):
                with workspace_temp_dir() as vault:
                    (vault / ".obsidian").mkdir()
                    selected = vault / "30_精选资料"
                    moved = Path("AI/2026年01月/普通标量领域.md")
                    self._write_note(
                        selected / moved,
                        "AI",
                        "普通标量领域",
                        "待迁移正文",
                    )
                    moves = {moved: "信息技术"}

                    execute_review(vault, moves, trash=(), links={})
                    destination = (
                        selected / "信息技术/2026年01月/普通标量领域.md"
                    )
                    destination.write_text(
                        "---\n"
                        "type: 资料\n"
                        f"{domain_line}\n"
                        'created: "2026-01-02 03:04:05"\n'
                        'uid: "normal-scalar-domain"\n'
                        "---\n\n"
                        "# 普通标量领域\n",
                        encoding="utf-8",
                    )

                    report = verify_review_results(vault, moves, (), {})

                    self.assertTrue(report["ok"], report["issues"])

    def test_containment_rejects_path_resolving_outside_root(self):
        with workspace_temp_dir() as root:
            selected = root / "30_精选资料"
            outside = root / "outside"
            selected.mkdir()
            outside.mkdir()

            self.assertFalse(_is_within(selected / "../outside", selected))


class CommandLineTests(unittest.TestCase):
    def test_help_works_for_script_and_module_entry_points(self):
        commands = (
            (
                sys.executable,
                str(REPO_ROOT / "scripts" / "reclassify_selected_materials.py"),
                "--help",
            ),
            (
                sys.executable,
                "-m",
                "scripts.reclassify_selected_materials",
                "--help",
            ),
        )
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    command,
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for phase in ("audit", "apply", "verify"):
                    self.assertIn(phase, result.stdout)

    def test_help_exposes_defaults_schema_writes_and_confirmation_boundary(self):
        script = str(REPO_ROOT / "scripts" / "reclassify_selected_materials.py")
        root_help = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        apply_help = subprocess.run(
            [sys.executable, script, "apply", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        verify_help = subprocess.run(
            [sys.executable, script, "verify", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(root_help.returncode, 0, root_help.stderr)
        self.assertIn("OBSIDIAN_VAULT_PATH", root_help.stdout)
        self.assertIn(".state/yinxiang-notes/reports", root_help.stdout)
        self.assertIn("moves、trash、links", root_help.stdout)
        self.assertEqual(apply_help.returncode, 0, apply_help.stderr)
        self.assertIn("RECLASSIFY_SELECTED_MATERIALS", apply_help.stdout)
        self.assertIn("修改业务资料", apply_help.stdout)
        self.assertIn("九个领域索引", apply_help.stdout)
        self.assertEqual(verify_help.returncode, 0, verify_help.stderr)
        self.assertIn("业务资料只读", verify_help.stdout)
        self.assertIn("写验证报告", verify_help.stdout)

    def _seed_vault(self, vault):
        (vault / ".obsidian").mkdir()
        note = vault / "30_精选资料/AI/2026年01月/原始资料.md"
        note.parent.mkdir(parents=True)
        note.write_text(
            "---\n"
            'type: "资料"\n'
            'domain: "AI"\n'
            'created: "2026-01-02 03:04:05"\n'
            'source_guid: "original-guid"\n'
            "---\n\n"
            "# 原始资料\n\n"
            "AI 工程资料。\n",
            encoding="utf-8",
        )

    def _write_decisions(self, vault, payload):
        path = vault / "decisions.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def test_audit_defaults_report_into_vault_state_reports(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)

            result = main(["audit", "--vault", str(vault)])

            reports = tuple(
                (vault / ".state/yinxiang-notes/reports").glob("audit-*.json")
            )
            self.assertEqual(result, 0)
            self.assertEqual(len(reports), 1)
            self.assertEqual(
                reports[0].parent,
                default_report_path(vault, "audit").parent,
            )
            self.assertTrue(reports[0].read_text(encoding="utf-8").endswith("\n"))

    def test_apply_requires_exact_confirmation(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            decisions = self._write_decisions(
                vault,
                {"moves": {}, "trash": [], "links": {}},
            )

            result = main(
                [
                    "apply",
                    "--vault",
                    str(vault),
                    "--decisions",
                    str(decisions),
                    "--confirm",
                    "RECLASSIFY_SELECTED_MATERIAL",
                ]
            )

            self.assertEqual(result, 2)
            self.assertTrue(
                (vault / "30_精选资料/AI/2026年01月/原始资料.md").is_file()
            )

    def test_verify_returns_nonzero_when_result_is_invalid(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            decisions = self._write_decisions(
                vault,
                {
                    "moves": {"AI/2026年01月/原始资料.md": "信息技术"},
                    "trash": [],
                    "links": {},
                },
            )

            result = main(
                ["verify", "--vault", str(vault), "--decisions", str(decisions)]
            )

            self.assertEqual(result, 1)

    def test_cli_uses_default_vault_loader_when_vault_omitted(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            with patch(
                "scripts.reclassify_selected_materials.load_vault_root",
                return_value=vault,
            ) as loader:
                result = main(["audit"])

            self.assertEqual(result, 0)
            loader.assert_called_once_with(None)

    def test_active_runtime_lock_blocks_apply_without_any_write(self):
        from scripts.vault_state import VaultStatePaths, runtime_write_lock

        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            decisions = self._write_decisions(
                vault,
                {
                    "moves": {
                        "AI/2026年01月/原始资料.md": "信息技术",
                    },
                    "trash": [],
                    "links": {},
                },
            )
            output = vault / "blocked-report.json"
            paths = VaultStatePaths.for_vault(vault)
            source = vault / "30_精选资料/AI/2026年01月/原始资料.md"
            destination = (
                vault / "30_精选资料/信息技术/2026年01月/原始资料.md"
            )

            with runtime_write_lock(paths, "active-task"):
                result = main(
                    [
                        "apply",
                        "--vault",
                        str(vault),
                        "--decisions",
                        str(decisions),
                        "--confirm",
                        "RECLASSIFY_SELECTED_MATERIALS",
                        "--output",
                        str(output),
                    ]
                )

                self.assertEqual(result, 1)
                self.assertTrue(source.is_file())
                self.assertFalse(destination.exists())
                self.assertFalse(output.exists())

    def test_apply_holds_runtime_lock_until_report_is_written(self):
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            decisions = self._write_decisions(
                vault,
                {"moves": {}, "trash": [], "links": {}},
            )
            paths = VaultStatePaths.for_vault(vault)
            observed = []

            def observe_report(path, report):
                del path, report
                observed.append(paths.lock.is_file())

            with patch(
                "scripts.reclassify_selected_materials._write_report",
                side_effect=observe_report,
            ):
                result = main(
                    [
                        "apply",
                        "--vault",
                        str(vault),
                        "--decisions",
                        str(decisions),
                        "--confirm",
                        "RECLASSIFY_SELECTED_MATERIALS",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(observed, [True])
            self.assertFalse(paths.lock.exists())

    def test_apply_preflight_failure_is_stable_reported_and_atomic(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            invalid = vault / "30_精选资料/AI/2026年01月/无前置字段.md"
            invalid.write_text("# 无前置字段\n\n正文。\n", encoding="utf-8")
            decisions = self._write_decisions(
                vault,
                {
                    "moves": {
                        "AI/2026年01月/原始资料.md": "信息技术",
                        "AI/2026年01月/无前置字段.md": "投资理财",
                    },
                    "trash": [],
                    "links": {},
                },
            )
            output = vault / "failed-apply.json"

            result = main(
                [
                    "apply",
                    "--vault",
                    str(vault),
                    "--decisions",
                    str(decisions),
                    "--confirm",
                    "RECLASSIFY_SELECTED_MATERIALS",
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(result, 1)
            self.assertTrue(
                (vault / "30_精选资料/AI/2026年01月/原始资料.md").is_file()
            )
            self.assertTrue(invalid.is_file())
            self.assertFalse(
                (
                    vault
                    / "30_精选资料"
                    / "信息技术"
                    / "2026年01月"
                    / "原始资料.md"
                ).exists()
            )
            self.assertFalse(
                (vault / ".state/yinxiang-notes/snapshots").exists()
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertEqual(report["phase"], "apply")
            self.assertEqual(report["completed"], [])
            self.assertEqual(report["snapshot"], None)

    def test_apply_verification_exception_report_keeps_created_snapshot(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            decisions = self._write_decisions(
                vault,
                {
                    "moves": {
                        "AI/2026年01月/原始资料.md": "信息技术",
                    },
                    "trash": [],
                    "links": {},
                },
            )
            output = vault / "failed-verification.json"

            with patch(
                "scripts.reclassify_selected_materials.verify_review_results",
                side_effect=ValueError("验证器异常"),
            ):
                result = main(
                    [
                        "apply",
                        "--vault",
                        str(vault),
                        "--decisions",
                        str(decisions),
                        "--confirm",
                        "RECLASSIFY_SELECTED_MATERIALS",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(result, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertIsNotNone(report["snapshot"])
            self.assertTrue(Path(report["snapshot"]["archive"]).is_file())
            self.assertTrue(Path(report["snapshot"]["manifest"]).is_file())

    def test_apply_execution_failure_rolls_back_and_reports_snapshot(self):
        with workspace_temp_dir() as vault:
            self._seed_vault(vault)
            decisions = self._write_decisions(
                vault,
                {
                    "moves": {
                        "AI/2026年01月/原始资料.md": "信息技术",
                    },
                    "trash": [],
                    "links": {},
                },
            )
            output = vault / "failed-execution.json"
            source = vault / "30_精选资料/AI/2026年01月/原始资料.md"
            destination = (
                vault / "30_精选资料/信息技术/2026年01月/原始资料.md"
            )

            with patch(
                "scripts.reclassify_selected_materials.write_knowledge_base_index",
                side_effect=OSError("模拟索引写入中断"),
            ):
                result = main(
                    [
                        "apply",
                        "--vault",
                        str(vault),
                        "--decisions",
                        str(decisions),
                        "--confirm",
                        "RECLASSIFY_SELECTED_MATERIALS",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(result, 1)
            self.assertTrue(source.is_file())
            self.assertFalse(destination.exists())
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertEqual(report["completed"], [])
            self.assertIsNotNone(report["snapshot"])
            self.assertIn("已回滚", "\n".join(report["issues"]))


if __name__ == "__main__":
    unittest.main()
