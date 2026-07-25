import unittest

from scripts.search_notes import parse_query


class ParseQueryTests(unittest.TestCase):
    def test_title_query_uses_supported_intitle_modifier(self):
        note_filter = parse_query("标题:AI")
        self.assertEqual(note_filter.words, "intitle:AI")

    def test_any_query_keeps_the_union_modifier(self):
        note_filter = parse_query("any:AI Agent")
        self.assertEqual(note_filter.words, "any: AI Agent")

    def test_created_query_normalizes_iso_date_for_search_grammar(self):
        note_filter = parse_query("创建时间:2024-01-01")
        self.assertEqual(note_filter.words, "created:20240101")


if __name__ == "__main__":
    unittest.main()
