import hashlib
import json
from pathlib import Path
import unittest
import zipfile

from tests.support import workspace_temp_dir


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExportSnapshotTests(unittest.TestCase):
    def test_snapshot_contains_only_declared_domain_files_and_manifest(self):
        from scripts.export_snapshot import create_domain_snapshot

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            ai = vault / "30_精选资料" / "AI"
            ai.mkdir(parents=True)
            (ai / "文章.md").write_text("AI", encoding="utf-8")
            outside = vault / "20_知识笔记"
            outside.mkdir(parents=True)
            (outside / "不要打包.md").write_text(
                "outside",
                encoding="utf-8",
            )

            result = create_domain_snapshot(
                vault,
                ("AI",),
                vault / ".state" / "yinxiang-notes" / "snapshots",
                "job-1",
            )

            with zipfile.ZipFile(result.archive) as archive:
                names = set(archive.namelist())
            manifest = json.loads(
                result.manifest.read_text(encoding="utf-8")
            )
            archive_hash = sha256(result.archive)

        self.assertIn("30_精选资料/AI/文章.md", names)
        self.assertNotIn("20_知识笔记/不要打包.md", names)
        self.assertEqual(
            manifest["archive_sha256"],
            archive_hash,
        )
        self.assertEqual(
            manifest["members"],
            [
                {
                    "path": "30_精选资料/AI/文章.md",
                    "sha256": hashlib.sha256(b"AI").hexdigest(),
                    "size": 2,
                }
            ],
        )

    def test_existing_valid_snapshot_is_reused_without_repacking(self):
        from scripts.export_snapshot import create_domain_snapshot

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            ai = vault / "30_精选资料" / "AI"
            ai.mkdir(parents=True)
            source = ai / "文章.md"
            source.write_text("before", encoding="utf-8")
            snapshot_dir = (
                vault / ".state" / "yinxiang-notes" / "snapshots"
            )
            first = create_domain_snapshot(
                vault,
                ("AI",),
                snapshot_dir,
                "job-1",
            )
            first_bytes = first.archive.read_bytes()
            source.write_text("after", encoding="utf-8")

            second = create_domain_snapshot(
                vault,
                ("AI",),
                snapshot_dir,
                "job-1",
            )
            reused = second.reused
            second_bytes = second.archive.read_bytes()

        self.assertTrue(reused)
        self.assertEqual(second_bytes, first_bytes)

    def test_corrupted_or_partial_existing_snapshot_is_never_overwritten(self):
        from scripts.export_snapshot import create_domain_snapshot

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            (vault / "30_精选资料" / "AI").mkdir(parents=True)
            snapshot_dir = (
                vault / ".state" / "yinxiang-notes" / "snapshots"
            )
            snapshot_dir.mkdir(parents=True)
            archive = snapshot_dir / "job-1-before.zip"
            archive.write_bytes(b"corrupted")

            with self.assertRaisesRegex(ValueError, "不完整"):
                create_domain_snapshot(
                    vault,
                    ("AI",),
                    snapshot_dir,
                    "job-1",
                )
            self.assertEqual(archive.read_bytes(), b"corrupted")

            manifest = snapshot_dir / "job-1-before.sha256.json"
            manifest.write_text(
                json.dumps(
                    {
                        "archive_sha256": "0" * 64,
                        "archive_size": len(b"corrupted"),
                        "members": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "哈希"):
                create_domain_snapshot(
                    vault,
                    ("AI",),
                    snapshot_dir,
                    "job-1",
                )
            self.assertEqual(archive.read_bytes(), b"corrupted")


if __name__ == "__main__":
    unittest.main()
