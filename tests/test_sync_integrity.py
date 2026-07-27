import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import workspace_temp_dir


class FrontmatterTests(unittest.TestCase):
    def test_frontmatter_supports_scalar_and_list_extra_fields(self):
        from scripts.sync_to_obsidian import frontmatter

        rendered = frontmatter(
            "标题",
            "微信",
            "guid-1",
            datetime(2026, 7, 21, 8, 0, 0),
            datetime(2026, 7, 22, 9, 0, 0),
            {
                "type": "资料",
                "domain": "AI",
                "status": "待提炼",
                "tags": ["主题/Agent"],
                "review_status": "pending",
                "llm_policy": "strict",
            },
            include_title=False,
        )

        self.assertIn('type: "资料"', rendered)
        self.assertIn('domain: "AI"', rendered)
        self.assertIn('tags: ["主题/Agent"]', rendered)
        self.assertNotIn('tags: "[', rendered)

    def test_quotes_yaml_sensitive_strings(self):
        from scripts.sync_to_obsidian import frontmatter

        generated = frontmatter(
            title='AI: "代理"\n第二行',
            nb_name="2026:知识库",
            guid="guid:123",
            created=datetime(2026, 7, 26, 8, 30),
            updated=datetime(2026, 7, 26, 9, 45),
            extra="type: webclip",
        )

        self.assertIn('title: "AI: \\"代理\\"\\n第二行"', generated)
        self.assertIn('notebook: "2026:知识库"', generated)
        self.assertIn('source_guid: "guid:123"', generated)
        self.assertIn('source: "Evernote"', generated)
        self.assertIn('type: "webclip"', generated)


class NotePathTests(unittest.TestCase):
    def test_same_title_different_guid_uses_distinct_markdown_paths(self):
        try:
            from scripts.sync_to_obsidian import (
                frontmatter,
                resolve_note_path,
            )
        except ImportError:
            self.fail("尚未实现按 GUID 解析 Markdown 输出路径")

        timestamp = datetime(2026, 7, 26)
        with workspace_temp_dir() as folder:
            first = resolve_note_path(
                folder,
                "同名",
                "aaaaaaaa-1111-2222-3333",
                {},
            )
            first.write_text(
                frontmatter(
                    "同名",
                    "测试",
                    "aaaaaaaa-1111-2222-3333",
                    timestamp,
                    timestamp,
                ),
                encoding="utf-8",
            )
            second = resolve_note_path(
                folder,
                "同名",
                "bbbbbbbb-1111-2222-3333",
                {},
            )
            same_as_first = resolve_note_path(
                folder,
                "同名",
                "aaaaaaaa-1111-2222-3333",
                {},
            )

        self.assertEqual(first.name, "同名.md")
        self.assertEqual(second.name, "同名_bbbbbbbb.md")
        self.assertEqual(same_as_first, first)
        self.assertNotEqual(first, second)

    def test_existing_guid_map_reuses_renamed_file(self):
        from scripts.sync_to_obsidian import resolve_note_path

        with workspace_temp_dir() as folder:
            renamed = folder / "人工改名.md"
            resolved = resolve_note_path(
                folder,
                "原始标题",
                "known-guid",
                {
                    "known-guid": {
                        "file": str(renamed),
                        "local_updated_ms": 0,
                    }
                },
            )

        self.assertEqual(resolved, renamed)

    def test_body_source_guid_is_not_treated_as_frontmatter(self):
        from scripts.sync_to_obsidian import extract_source_guid

        with workspace_temp_dir() as folder:
            markdown_path = folder / "普通笔记.md"
            markdown_path.write_text(
                "# 正文\n\nsource_guid: body-only\n",
                encoding="utf-8",
            )

            guid = extract_source_guid(markdown_path)

        self.assertIsNone(guid)


class SyncPaginationTests(unittest.TestCase):
    def test_fetches_every_metadata_page(self):
        try:
            from scripts.sync_to_obsidian import find_all_note_metadata
        except ImportError:
            self.fail("尚未实现同步元数据分页查询")

        notes = [
            SimpleNamespace(guid=f"guid-{index}")
            for index in range(255)
        ]

        class FakeNoteStore:
            def __init__(self):
                self.offsets = []
                self.limits = []

            def findNotesMetadata(
                self,
                token,
                note_filter,
                offset,
                max_results,
                result_spec,
            ):
                self.offsets.append(offset)
                self.limits.append(max_results)
                return SimpleNamespace(
                    notes=notes[offset:offset + max_results],
                    totalNotes=len(notes),
                )

        note_store = FakeNoteStore()
        found = find_all_note_metadata(
            note_store,
            token="test-token",
            notebook_guid="notebook-guid",
            page_size=250,
        )

        self.assertEqual(len(found), 255)
        self.assertEqual(note_store.offsets, [0, 250])
        self.assertEqual(note_store.limits, [250, 250])


class SyncStateTests(unittest.TestCase):
    def test_changing_notebook_scope_resets_saved_progress(self):
        try:
            from scripts.sync_to_obsidian import prepare_sync_state
        except ImportError:
            self.fail("尚未实现同步范围变化时的断点重置")

        state = {
            "target_notebook": "旧笔记本",
            "progress": {"notebook_idx": 5, "note_idx": 20},
            "synced_guids": {},
        }

        prepared = prepare_sync_state(state, "新笔记本")

        self.assertEqual(
            prepared["progress"],
            {"notebook_idx": 0, "note_idx": 0},
        )
        self.assertEqual(prepared["target_notebook"], "新笔记本")

    def test_same_notebook_scope_keeps_saved_progress(self):
        from scripts.sync_to_obsidian import prepare_sync_state

        state = {
            "target_notebook": "2026",
            "progress": {"notebook_idx": 0, "note_idx": 12},
            "synced_guids": {},
        }

        prepared = prepare_sync_state(state, "2026")

        self.assertEqual(
            prepared["progress"],
            {"notebook_idx": 0, "note_idx": 12},
        )


class SyncDestinationSafetyTests(unittest.TestCase):
    def test_full_sync_rejects_unified_llm_wiki_root_before_loading_credentials(self):
        from scripts.sync_to_obsidian import sync_to_obsidian

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "00_首页.md").write_text("# 首页\n", encoding="utf-8")
            for name in ("10_项目", "20_知识笔记", "30_精选资料", "80_系统"):
                (vault / name).mkdir()

            with patch(
                "scripts.sync_to_obsidian.load_config",
                side_effect=AssertionError("统一根目录拒绝前不应读取凭据"),
            ), redirect_stdout(StringIO()):
                succeeded = sync_to_obsidian(vault, max_sync_per_run=1, api_delay=0)

            self.assertFalse(succeeded)
            self.assertFalse((vault / ".yinxiang_sync_state.json").exists())

    def test_old_system_directory_alone_is_not_the_new_root_marker(self):
        from scripts.sync_to_obsidian import is_unified_llm_wiki_root

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            (vault / "00_首页.md").write_text("# 首页\n", encoding="utf-8")
            for name in ("10_项目", "20_知识笔记", "30_精选资料", "90_系统"):
                (vault / name).mkdir()

            self.assertFalse(is_unified_llm_wiki_root(vault))


class FilenameTests(unittest.TestCase):
    def test_windows_reserved_name_and_trailing_dot_are_sanitized(self):
        from scripts.sync_to_obsidian import safe_filename

        self.assertEqual(safe_filename("CON"), "_CON")
        self.assertEqual(safe_filename("报告. "), "报告")
        self.assertLessEqual(len(safe_filename("很长" * 200)), 120)
        long_image_name = safe_filename("a" * 200 + ".png")
        self.assertLessEqual(len(long_image_name), 120)
        self.assertTrue(long_image_name.endswith(".png"))

    def test_clip_filename_uses_full_guid_identity(self):
        from scripts.sync_to_obsidian import clip_filename_for_guid

        first = clip_filename_for_guid("aaaaaaaa-1111-2222-3333")
        second = clip_filename_for_guid("aaaaaaaa-9999-8888-7777")

        self.assertNotEqual(first, second)
        self.assertIn("aaaaaaaa-1111-2222-3333", first)


if __name__ == "__main__":
    unittest.main()
