import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.list_notebooks import load_config
from scripts import search_notes
from tests.support import workspace_temp_dir


class LoadConfigTests(unittest.TestCase):
    def test_env_example_separates_formal_vault_from_sync_staging(self):
        environment = (
            Path(__file__).resolve().parent.parent / ".env.example"
        ).read_text(encoding="utf-8")

        self.assertIn(
            r"OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian",
            environment,
        )
        self.assertIn(
            r"YINXIANG_SYNC_VAULT_PATH=D:\OneDrive\文档\@_Obsidian_全量同步暂存",
            environment,
        )

    def test_reads_explicit_skill_local_env_file(self):
        with workspace_temp_dir() as temp_dir:
            env_path = temp_dir / ".env"
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
        with workspace_temp_dir() as temp_dir:
            env_path = temp_dir / ".env"
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
