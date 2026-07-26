import unittest
from datetime import datetime


class MonthFolderTests(unittest.TestCase):
    def test_formats_created_time_as_chinese_month_folder(self):
        from scripts.knowledge_base import month_folder_name

        self.assertEqual(
            month_folder_name(datetime(2026, 7, 24, 11, 0)),
            "2026年07月",
        )
