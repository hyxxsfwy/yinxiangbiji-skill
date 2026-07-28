import unittest
from datetime import datetime

from tests.support import workspace_temp_dir


def write_article(root, domain, month, filename, guid, title, created, body="正文内容"):
    path = root / "30_精选资料" / domain / month / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'created: "{created}"\n'
        f'updated: "{created}"\n'
        f'source_guid: "{guid}"\n'
        'type: "资料"\n'
        f'domain: "{domain}"\n'
        "---\n\n"
        f"# {title}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def write_index(root, domain, relative_paths):
    path = root / "30_精选资料" / domain / "目录索引.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: 索引",
        f"domain: {domain}",
        "---",
        "",
        f"# {domain} 目录",
        "",
    ]
    for relative in relative_paths:
        lines.extend(
            [
                f"- [[{relative}|文章]]",
                f"  - 位置：`{relative}`",
                "  - 简介：测试简介。",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ExportIntegrityTests(unittest.TestCase):
    def test_scanner_reports_index_attachment_and_range_facts(self):
        from scripts.export_integrity import scan_export_integrity

        with workspace_temp_dir() as vault:
            write_article(
                vault,
                "AI",
                "2026年04月",
                "范围内.md",
                "inside-guid",
                "范围内",
                "2026-04-15 10:00:00",
                body="![缺图](../_attachments/missing.png)",
            )
            write_article(
                vault,
                "AI",
                "2026年07月",
                "范围外.md",
                "outside-guid",
                "范围外",
                "2026-07-03 10:00:00",
            )
            write_index(
                vault,
                "AI",
                ["2026年04月/不存在.md"],
            )

            report = scan_export_integrity(
                vault,
                domains=("AI",),
                since=datetime.fromisoformat("2026-04-01"),
                until=datetime.fromisoformat("2026-07-01"),
            )

            domain = report.domains["AI"]
            self.assertEqual(domain.total_articles, 2)
            self.assertEqual(domain.in_range_articles, 1)
            self.assertEqual(domain.index_entries, 1)
            self.assertEqual(domain.image_references, 1)
            self.assertEqual(
                {issue.kind for issue in domain.issues},
                {
                    "missing_attachment",
                    "missing_index_target",
                    "index_missing_article",
                },
            )
            self.assertFalse(report.ok)
            self.assertEqual(
                report.to_dict()["domains"]["AI"]["in_range_articles"],
                1,
            )

    def test_scanner_finds_cross_domain_guid_and_title_duplicates(self):
        from scripts.export_integrity import scan_export_integrity

        with workspace_temp_dir() as vault:
            created = "2026-05-10 09:00:00"
            fixtures = (
                ("AI", "shared-guid", "同 GUID 同标题", "共同.md"),
                ("投资理财", "shared-guid", "同 GUID 同标题", "共同.md"),
                ("AI", "title-guid-ai", "仅标题重复", "AI标题.md"),
                (
                    "投资理财",
                    "title-guid-invest",
                    "仅标题重复",
                    "投资标题.md",
                ),
            )
            paths = {"AI": [], "投资理财": []}
            for domain, guid, title, filename in fixtures:
                path = write_article(
                    vault,
                    domain,
                    "2026年05月",
                    filename,
                    guid,
                    title,
                    created,
                )
                paths[domain].append(
                    path.relative_to(
                        vault / "30_精选资料" / domain
                    ).as_posix()
                )
            for domain, relative_paths in paths.items():
                write_index(vault, domain, relative_paths)

            report = scan_export_integrity(
                vault,
                domains=("AI", "投资理财"),
                since=datetime.fromisoformat("2026-04-01"),
                until=datetime.fromisoformat("2026-07-01"),
            )

            self.assertEqual(
                set(report.cross_domain_guid_duplicates),
                {"shared-guid"},
            )
            self.assertEqual(
                set(report.cross_domain_title_duplicates),
                {"同 GUID 同标题", "仅标题重复"},
            )
            self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
