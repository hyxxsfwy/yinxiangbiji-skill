import contextlib
import importlib
import io
import os
import unittest
from unittest.mock import patch

from tests.support import workspace_temp_dir


class RuntimeConfigTests(unittest.TestCase):
    def test_environment_overrides_dotenv(self):
        try:
            from scripts.runtime import load_config
        except ModuleNotFoundError:
            self.fail("尚未实现共享运行时配置模块")

        with workspace_temp_dir() as temp_dir:
            env_path = temp_dir / ".env"
            env_path.write_text(
                "EVERNOTE_TOKEN=file-token\n"
                "EVERNOTE_NOTESTORE_URL="
                "https://app.yinxiang.com/shard/s16/notestore\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "EVERNOTE_TOKEN": "env-token",
                    "EVERNOTE_NOTESTORE_URL":
                    "https://app.yinxiang.com/shard/s27/notestore",
                },
                clear=True,
            ):
                config = load_config(env_path=env_path)

        self.assertEqual(
            config,
            (
                "env-token",
                "https://app.yinxiang.com/shard/s27/notestore",
            ),
        )

    def test_importing_list_tags_has_no_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module = importlib.import_module("scripts.list_tags")
            importlib.reload(module)

        self.assertEqual(output.getvalue(), "")

    def test_reads_optional_vault_path_from_dotenv(self):
        try:
            from scripts.runtime import load_setting
        except ImportError:
            self.fail("尚未实现通用环境配置读取")

        with workspace_temp_dir() as temp_dir:
            env_path = temp_dir / ".env"
            env_path.write_text(
                r"OBSIDIAN_VAULT_PATH=D:\vault\知识库" + "\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                vault_path = load_setting(
                    "OBSIDIAN_VAULT_PATH",
                    env_path=env_path,
                )

        self.assertEqual(vault_path, r"D:\vault\知识库")


if __name__ == "__main__":
    unittest.main()
