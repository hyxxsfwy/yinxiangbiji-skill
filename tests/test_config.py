import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.list_notebooks import load_config
from scripts import search_notes


class LoadConfigTests(unittest.TestCase):
    def test_reads_explicit_skill_local_env_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "EVERNOTE_TOKEN=test-token\n"
                "EVERNOTE_NOTESTORE_URL=https://app.yinxiang.com/shard/s27/notestore\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                token, note_store_url = load_config(env_path=env_path)

        self.assertEqual(token, "test-token")
        self.assertEqual(
            note_store_url,
            "https://app.yinxiang.com/shard/s27/notestore",
        )

    def test_search_uses_the_same_config_loader(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "EVERNOTE_TOKEN=search-token\n"
                "EVERNOTE_NOTESTORE_URL=https://app.yinxiang.com/shard/s27/notestore\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                token, note_store_url = search_notes.load_config(env_path=env_path)

        self.assertEqual(token, "search-token")
        self.assertEqual(
            note_store_url,
            "https://app.yinxiang.com/shard/s27/notestore",
        )


if __name__ == "__main__":
    unittest.main()
