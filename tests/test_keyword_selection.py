import unittest

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

    def test_policy_hash_is_stable_and_changes_with_keywords(self):
        first = keyword_selection_hash({"AI": ("AI",)}, {})
        second = keyword_selection_hash({"AI": ("AI",)}, {})
        changed = keyword_selection_hash({"AI": ("AI", "LLM")}, {})

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

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
