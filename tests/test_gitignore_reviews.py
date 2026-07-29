"""验证 reviews 忽略规则只作用于同名目录内容。"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def check_ignored(path: str) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode == 0


class ReviewsIgnoreRuleTests(unittest.TestCase):
    def test_reviews_directory_contents_are_ignored_but_plain_files_are_not(self) -> None:
        self.assertTrue(check_ignored("reviews/sentinel.md"))
        self.assertTrue(check_ignored("nested/reviews/sentinel.md"))
        self.assertFalse(check_ignored("reviews.md"))
        self.assertFalse(check_ignored("nested/reviews"))
