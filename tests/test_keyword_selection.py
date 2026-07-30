import unittest
from unittest.mock import patch

from scripts.keyword_selection import (
    assess_keyword_union,
    expanded_query_terms,
    keyword_selection_hash,
    match_keyword_terms,
)


class KeywordBoundaryTests(unittest.TestCase):
    def test_ascii_terms_require_ascii_alphanumeric_boundaries(self):
        domains = {
            "AI": ("AI",),
            "投资理财": ("SOL",),
        }
        self.assertFalse(
            assess_keyword_union(
                "training solution",
                "<en-note>training solution</en-note>",
                domains,
                {},
            ).matched
        )

        result = assess_keyword_union(
            "AI助手与SOL交易",
            "<en-note>使用AI助手分析SOL交易</en-note>",
            domains,
            {},
        )

        self.assertTrue(result.matched)
        self.assertEqual(result.matched_keywords, ("AI", "SOL"))

    def test_chinese_terms_match_normalized_title_or_full_body(self):
        domains = {"健康医学": ("中医", "医学")}

        result = assess_keyword_union(
            "门诊记录",
            "<en-note><div>中医与现代医学</div></en-note>",
            domains,
            {},
        )

        self.assertEqual(result.primary_domain, "健康医学")
        self.assertEqual(result.matched_keywords, ("中医", "医学"))


class KeywordAssessmentTests(unittest.TestCase):
    def test_alias_is_reported_as_canonical_keyword(self):
        result = assess_keyword_union(
            "HuggingFace 入门",
            "<en-note>Hugging Face Transformer</en-note>",
            {"AI": ("HugginFace", "Transformer")},
            {"HugginFace": ("HuggingFace", "Hugging Face")},
        )

        self.assertEqual(
            result.matched_keywords,
            ("HugginFace", "Transformer"),
        )
        self.assertEqual(
            result.matched_terms,
            ("HuggingFace", "Hugging Face", "Transformer"),
        )

    def test_domain_count_wins_and_job_order_breaks_ties(self):
        domains = {
            "软件工程": ("软件工程",),
            "AI": ("AI", "LLM"),
        }

        result = assess_keyword_union(
            "软件工程中的AI与LLM",
            "<en-note>软件工程 AI LLM</en-note>",
            domains,
            {},
        )
        self.assertEqual(result.primary_domain, "AI")

        tie = assess_keyword_union(
            "软件工程与AI",
            "<en-note>软件工程 AI</en-note>",
            domains,
            {},
        )
        self.assertEqual(tie.primary_domain, "软件工程")

    def test_subject_domain_beats_larger_keyword_bucket(self):
        result = assess_keyword_union(
            "Python量化策略：基于成交量的 QQQ 交易策略",
            (
                "<en-note>用 AI 和 LLM 辅助编写代码，但正文主旨是"
                "量化交易、策略回测、交易信号和实盘风控。</en-note>"
            ),
            {
                "AI": ("AI", "LLM"),
                "Quant": ("量化",),
            },
            {},
        )

        self.assertEqual(result.primary_domain, "Quant")

    def test_managed_domain_can_differ_from_search_bucket(self):
        result = assess_keyword_union(
            "倪海厦：气血不足的调理方法",
            "<en-note>讨论中医辨证、经络、穴位和气血调理。</en-note>",
            {"健康医学": ("中医", "健康")},
            {},
        )

        self.assertEqual(result.primary_domain, "中医")

    def test_personal_growth_can_win_when_ai_only_selected_the_note(self):
        result = assess_keyword_union(
            "40岁失业后如何重新规划职业",
            (
                "<en-note>AI 筛选简历只是背景，正文讨论失业、"
                "职业规划、人生选择与自我提升。</en-note>"
            ),
            {"AI": ("AI",)},
            {},
        )

        self.assertEqual(result.primary_domain, "个人成长")

    def test_quant_can_win_even_when_only_ai_search_terms_selected_note(self):
        result = assess_keyword_union(
            "XALPHA：AI量化研究员——研报理解、策略挖掘与代码生成",
            (
                "<en-note>系统使用AI、LLM、机器学习、智能体和Agent，"
                "理解量化研报、挖掘Alpha因子、生成交易策略并回测。</en-note>"
            ),
            {"AI": ("AI", "LLM", "Agent")},
            {},
        )

        self.assertEqual(result.primary_domain, "Quant")

    def test_policy_hash_is_stable_and_changes_with_keywords(self):
        first = keyword_selection_hash({"AI": ("AI",)}, {})
        second = keyword_selection_hash({"AI": ("AI",)}, {})
        changed = keyword_selection_hash({"AI": ("AI", "LLM")}, {})

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_policy_hash_changes_with_shared_classifier_policy(self):
        current = keyword_selection_hash({"AI": ("AI",)}, {})
        with patch(
            "scripts.keyword_selection.CLASSIFICATION_POLICY_VERSION",
            999,
        ):
            changed = keyword_selection_hash({"AI": ("AI",)}, {})

        self.assertNotEqual(current, changed)

    def test_query_terms_expand_aliases_without_losing_canonical_identity(self):
        terms = expanded_query_terms(
            {"AI": ("HugginFace", "Transformer")},
            {"HugginFace": ("HuggingFace", "Hugging Face")},
        )

        self.assertEqual(
            terms,
            (
                ("AI", "HugginFace", "HugginFace"),
                ("AI", "HugginFace", "HuggingFace"),
                ("AI", "HugginFace", "Hugging Face"),
                ("AI", "Transformer", "Transformer"),
            ),
        )

    def test_match_details_preserve_domain_and_canonical_order(self):
        matches = match_keyword_terms(
            "LLM 与 AI",
            "<en-note>AI LLM</en-note>",
            {"AI": ("AI", "LLM")},
            {},
        )

        self.assertEqual(matches, {"AI": ("AI", "LLM")})


if __name__ == "__main__":
    unittest.main()
