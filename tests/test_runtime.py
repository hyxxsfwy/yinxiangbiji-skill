import contextlib
import importlib
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from evernote.edam.error.ttypes import EDAMSystemException

from tests.support import workspace_temp_dir


class RuntimeConfigTests(unittest.TestCase):
    def test_find_all_notes_metadata_reads_until_server_total(self):
        from scripts.runtime import find_all_notes_metadata

        class FakeNoteStore:
            def __init__(self):
                self.calls = []

            def findNotesMetadata(
                self,
                token,
                note_filter,
                offset,
                limit,
                result_spec,
            ):
                self.calls.append(
                    (token, note_filter, offset, limit, result_spec)
                )
                pages = {
                    0: ["note-1", "note-2"],
                    2: ["note-3"],
                }
                return SimpleNamespace(
                    totalNotes=3,
                    notes=pages[offset],
                )

        store = FakeNoteStore()
        notes, total = find_all_notes_metadata(
            store,
            "token",
            "filter",
            "spec",
            page_size=2,
        )

        self.assertEqual(notes, ["note-1", "note-2", "note-3"])
        self.assertEqual(total, 3)
        self.assertEqual(
            [(call[2], call[3]) for call in store.calls],
            [(0, 2), (2, 1)],
        )

    def test_rate_limit_wait_retries_same_operation(self):
        from scripts.runtime import call_with_rate_limit_retry

        calls = []
        sleeps = []
        waits = []

        def operation():
            calls.append("call")
            if len(calls) == 1:
                raise EDAMSystemException(
                    errorCode=19,
                    rateLimitDuration=2,
                )
            return "ok"

        result = call_with_rate_limit_retry(
            operation,
            mode="wait",
            max_wait_seconds=10,
            sleep=sleeps.append,
            on_wait=waits.append,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [2])
        self.assertEqual(waits, [2])

    def test_rate_limit_stop_and_budget_exhaustion_preserve_control(self):
        from scripts.runtime import (
            RateLimitBudgetExceeded,
            call_with_rate_limit_retry,
        )

        def limited():
            raise EDAMSystemException(
                errorCode=19,
                rateLimitDuration=3,
            )

        for mode, budget in (("stop", 10), ("wait", 2)):
            with self.subTest(mode=mode, budget=budget):
                with self.assertRaises(RateLimitBudgetExceeded):
                    call_with_rate_limit_retry(
                        limited,
                        mode=mode,
                        max_wait_seconds=budget,
                        sleep=lambda _seconds: self.fail(
                            "停止或超预算时不得等待"
                        ),
                    )

    def test_note_store_http_requests_have_a_finite_timeout(self):
        from scripts.runtime import create_note_store

        client = create_note_store(
            "https://app.yinxiang.com/shard/s27/notestore",
            "test-token",
        )
        transport = client._iprot.trans

        self.assertEqual(
            transport._THttpClient__timeout,
            60.0,
        )

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
