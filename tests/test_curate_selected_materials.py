import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import unittest
import zipfile

from tests.support import workspace_temp_dir


def seed_review_vault(vault):
    (vault / ".obsidian").mkdir()
    ai = vault / "30_精选资料" / "AI" / "2026年07月"
    quant = vault / "30_精选资料" / "Quant" / "2026年07月"
    ai.mkdir(parents=True)
    quant.mkdir(parents=True)
    (vault / "30_精选资料" / "AI" / "目录索引.md").write_text(
        "# 索引\n",
        encoding="utf-8",
    )
    (ai / "Agent 架构.md").write_text(
        "# Agent 架构\n\n正文。\n",
        encoding="utf-8",
    )
    (quant / "量化因子.md").write_text(
        "# 量化因子\n\n正文。\n",
        encoding="utf-8",
    )


def review_item(path, decision="keep", *, links=(), reason="领域匹配", topic="主题"):
    from scripts.curate_selected_materials import ReviewItem

    return ReviewItem(
        path=PurePosixPath(path),
        decision=decision,
        reason=reason,
        topic=topic,
        links=tuple(PurePosixPath(link) for link in links),
    )


class ReviewManifestTests(unittest.TestCase):
    def test_repository_review_manifest_is_explicit_and_symmetric(self):
        from scripts.curate_selected_materials import load_review_manifest

        manifest_path = Path(
            "reviews/2026-07-27-selected-materials-review.json"
        )
        raw_items = json.loads(manifest_path.read_text(encoding="utf-8"))
        reviews = load_review_manifest(manifest_path)
        by_path = {review.path: review for review in reviews}

        self.assertEqual(len(raw_items), 214)
        self.assertEqual(len(reviews), 214)
        self.assertEqual(
            sum(review.decision == "trash" for review in reviews),
            48,
        )
        self.assertTrue(
            all(
                set(item) == {"path", "decision", "reason", "topic", "links"}
                for item in raw_items
            )
        )
        self.assertTrue(
            all(review.reason and review.topic for review in reviews)
        )
        self.assertTrue(all(len(review.links) <= 3 for review in reviews))
        for review in reviews:
            for target in review.links:
                self.assertIn(target, by_path)
                self.assertEqual(by_path[target].decision, "keep")
                self.assertIn(review.path, by_path[target].links)

    def test_manifest_requires_exact_document_coverage(self):
        from scripts.curate_selected_materials import (
            validate_review_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_review_vault(vault)
            reviews = (
                review_item("AI/2026年07月/Agent 架构.md"),
                review_item("AI/2026年07月/不存在.md"),
            )

            issues = validate_review_manifest(vault, reviews)

        self.assertIn("审阅清单缺少: Quant/2026年07月/量化因子.md", issues)
        self.assertIn("审阅清单路径不存在: AI/2026年07月/不存在.md", issues)

    def test_manifest_rejects_duplicate_paths_invalid_decisions_and_four_links(self):
        from scripts.curate_selected_materials import (
            validate_review_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_review_vault(vault)
            duplicate_path = "AI/2026年07月/Agent 架构.md"
            reviews = (
                review_item(
                    duplicate_path,
                    decision="archive",
                    links=(
                        "Quant/2026年07月/量化因子.md",
                        "AI/2026年07月/A.md",
                        "AI/2026年07月/B.md",
                        "AI/2026年07月/C.md",
                    ),
                ),
                review_item(duplicate_path),
                review_item("Quant/2026年07月/量化因子.md"),
            )

            issues = validate_review_manifest(vault, reviews)

        self.assertIn(f"审阅清单路径重复: {duplicate_path}", issues)
        self.assertIn(f"decision 无效: {duplicate_path}: archive", issues)
        self.assertIn(f"自动链接超过 3 条: {duplicate_path}: 4", issues)

    def test_manifest_requires_symmetric_links_and_keep_targets(self):
        from scripts.curate_selected_materials import (
            validate_review_manifest,
        )

        with workspace_temp_dir() as vault:
            seed_review_vault(vault)
            ai_path = "AI/2026年07月/Agent 架构.md"
            quant_path = "Quant/2026年07月/量化因子.md"
            reviews = (
                review_item(ai_path, links=(quant_path,)),
                review_item(quant_path, decision="trash"),
            )

            issues = validate_review_manifest(vault, reviews)

        self.assertIn(f"自动链接指向非保留文档: {ai_path} -> {quant_path}", issues)
        self.assertIn(f"自动链接不是双向: {ai_path} -> {quant_path}", issues)

    def test_load_review_manifest_requires_explicit_fields(self):
        from scripts.curate_selected_materials import load_review_manifest

        with workspace_temp_dir() as root:
            manifest = root / "review.json"
            manifest.write_text(
                json.dumps(
                    [
                        {
                            "path": "AI/2026年07月/Agent 架构.md",
                            "decision": "keep",
                            "reason": "正文讨论 Agent 架构",
                            "topic": "Agent 工程",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "字段"):
                load_review_manifest(manifest)


class AutoLinkTests(unittest.TestCase):
    def test_rendered_path_with_dots_passes_full_vault_link_validation(self):
        from scripts.curate_selected_materials import render_auto_links
        from scripts.restructure_obsidian_vault import scan_local_links

        with workspace_temp_dir() as vault:
            (vault / ".obsidian").mkdir()
            month = vault / "30_精选资料" / "AI" / "2026年07月"
            month.mkdir(parents=True)
            source = month / "来源.md"
            target = month / "GPT-5.6 平台化.md"
            target.write_text("# GPT-5.6 平台化\n", encoding="utf-8")
            rendered = render_auto_links(
                "# 来源\n",
                (
                    review_item(
                        "AI/2026年07月/GPT-5.6 平台化.md",
                    ),
                ),
            )
            source.write_text(rendered, encoding="utf-8")

            issues = scan_local_links(vault)

        self.assertEqual(issues, ())

    def test_adds_sorted_links_without_changing_existing_body(self):
        from scripts.curate_selected_materials import render_auto_links

        original = "# Agent 架构\n\n正文保持不变。\n"
        links = (
            review_item(
                "AI/2026年07月/Z 文档.md",
                reason="关联",
                topic="Agent",
            ),
            review_item(
                "AI/2026年07月/A 文档.md",
                reason="关联",
                topic="Agent",
            ),
        )

        rendered = render_auto_links(original, links)

        self.assertTrue(rendered.startswith(original))
        self.assertEqual(
            rendered[len(original):],
            "\n## 相关笔记\n\n"
            "<!-- llmwiki:auto-links:start -->\n"
            "- [[30_精选资料/AI/2026年07月/A 文档.md|A 文档]]\n"
            "- [[30_精选资料/AI/2026年07月/Z 文档.md|Z 文档]]\n"
            "<!-- llmwiki:auto-links:end -->\n",
        )

    def test_replaces_existing_managed_block_idempotently(self):
        from scripts.curate_selected_materials import render_auto_links

        original = (
            "# Agent 架构\n\n正文。\n\n"
            "## 相关笔记\n\n"
            "<!-- llmwiki:auto-links:start -->\n"
            "- [[30_精选资料/AI/旧文档|旧文档]]\n"
            "<!-- llmwiki:auto-links:end -->\n"
        )
        links = (
            review_item(
                "AI/2026年07月/新文档.md",
                reason="关联",
                topic="Agent",
            ),
        )

        once = render_auto_links(original, links)
        twice = render_auto_links(once, links)

        self.assertEqual(twice, once)
        self.assertEqual(once.count("## 相关笔记"), 1)
        self.assertEqual(once.count("llmwiki:auto-links:start"), 1)
        self.assertIn(
            "[[30_精选资料/AI/2026年07月/新文档.md|新文档]]",
            once,
        )
        self.assertNotIn("旧文档", once)

    def test_removes_managed_section_when_links_become_empty(self):
        from scripts.curate_selected_materials import render_auto_links

        original = (
            "# Agent 架构\n\n正文。\n\n"
            "## 相关笔记\n\n"
            "<!-- llmwiki:auto-links:start -->\n"
            "- [[30_精选资料/AI/旧文档|旧文档]]\n"
            "<!-- llmwiki:auto-links:end -->\n"
        )

        rendered = render_auto_links(original, ())

        self.assertEqual(rendered, "# Agent 架构\n\n正文。\n")


def write_source_note(path, title, guid, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        'type: "资料"\n'
        f'domain: "{path.parents[1].name}"\n'
        'status: "待提炼"\n'
        'created: "2026-07-01 08:00:00"\n'
        'updated: "2026-07-01 09:00:00"\n'
        f'source_guid: "{guid}"\n'
        "---\n\n"
        f"# {title}\n\n{body}\n",
        encoding="utf-8",
    )


def seed_curation_vault(vault):
    (vault / ".obsidian").mkdir()
    ai_root = vault / "30_精选资料" / "AI"
    month = ai_root / "2026年07月"
    attachment = ai_root / "_attachments" / "car.png"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"car-image")
    write_source_note(
        month / "Agent 架构.md",
        "Agent 架构",
        "agent-guid",
        "讨论 Agent 的规划与执行。",
    )
    write_source_note(
        month / "Agent 状态.md",
        "Agent 状态",
        "state-guid",
        "讨论 Agent 状态管理。",
    )
    write_source_note(
        month / "汽车新闻.md",
        "汽车新闻",
        "car-guid",
        "这是一篇汽车评测。\n\n![汽车](../_attachments/car.png)",
    )
    (ai_root / "目录索引.md").write_text("# 旧索引\n", encoding="utf-8")
    (vault / "99_废纸篓").mkdir()
    (vault / "80_系统" / "知识库治理" / "变更快照").mkdir(
        parents=True
    )
    (vault / "80_系统" / "知识库治理" / "审核日志").mkdir()


def curation_reviews():
    agent = "AI/2026年07月/Agent 架构.md"
    state = "AI/2026年07月/Agent 状态.md"
    car = "AI/2026年07月/汽车新闻.md"
    return (
        review_item(
            agent,
            links=(state,),
            reason="正文讨论 Agent 架构",
            topic="Agent 工程",
        ),
        review_item(
            state,
            links=(agent,),
            reason="正文讨论 Agent 状态",
            topic="Agent 工程",
        ),
        review_item(
            car,
            decision="trash",
            reason="正文是汽车评测，与 AI 不符",
            topic="错域/汽车",
        ),
    )


class CurationIntegrationTests(unittest.TestCase):
    def test_apply_moves_trash_markdown_and_copies_referenced_asset(self):
        from scripts.curate_selected_materials import (
            apply_curation,
            build_curation_plan,
            create_snapshot,
        )

        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            plan = build_curation_plan(vault, curation_reviews())
            create_snapshot(
                plan,
                plan.snapshot_zip,
                plan.snapshot_manifest,
            )

            apply_curation(plan)

            source_note = (
                vault / "30_精选资料" / "AI" / "2026年07月" / "汽车新闻.md"
            )
            trash_note = (
                vault
                / "99_废纸篓"
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / "汽车新闻.md"
            )
            trash_asset = (
                vault
                / "99_废纸篓"
                / "30_精选资料"
                / "AI"
                / "_attachments"
                / "car.png"
            )
            self.assertFalse(source_note.exists())
            self.assertTrue(trash_note.is_file())
            self.assertEqual(trash_asset.read_bytes(), b"car-image")
            self.assertIn(
                "../_attachments/car.png",
                trash_note.read_text(encoding="utf-8"),
            )

    def test_preflight_rejects_different_existing_destination_before_snapshot(self):
        from scripts.curate_selected_materials import (
            build_curation_plan,
            preflight_issues,
        )

        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            conflict = (
                vault
                / "99_废纸篓"
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / "汽车新闻.md"
            )
            conflict.parent.mkdir(parents=True)
            conflict.write_text("用户已有内容\n", encoding="utf-8")
            plan = build_curation_plan(vault, curation_reviews())

            issues = preflight_issues(plan)

            self.assertIn("废纸篓目标内容冲突", "\n".join(issues))
            self.assertFalse(plan.snapshot_zip.exists())
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "AI"
                    / "2026年07月"
                    / "汽车新闻.md"
                ).is_file()
            )

    def test_snapshot_contains_every_modified_markdown_and_trash_asset(self):
        from scripts.curate_selected_materials import (
            build_curation_plan,
            create_snapshot,
        )

        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            plan = build_curation_plan(vault, curation_reviews())

            create_snapshot(
                plan,
                plan.snapshot_zip,
                plan.snapshot_manifest,
            )

            with zipfile.ZipFile(plan.snapshot_zip) as archive:
                names = set(archive.namelist())
            manifest = json.loads(
                plan.snapshot_manifest.read_text(encoding="utf-8")
            )
            manifest_names = {record["path"] for record in manifest["files"]}
            self.assertEqual(names, manifest_names)
            self.assertIn(
                "30_精选资料/AI/2026年07月/Agent 架构.md",
                names,
            )
            self.assertIn(
                "30_精选资料/AI/2026年07月/Agent 状态.md",
                names,
            )
            self.assertIn(
                "30_精选资料/AI/2026年07月/汽车新闻.md",
                names,
            )
            self.assertIn(
                "30_精选资料/AI/_attachments/car.png",
                names,
            )
            self.assertTrue(
                all(record["sha256"] for record in manifest["files"])
            )

    def test_completed_validation_checks_reciprocity_and_assets(self):
        from scripts.curate_selected_materials import (
            apply_curation,
            build_curation_plan,
            create_snapshot,
            validate_completed_curation,
        )

        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            plan = build_curation_plan(vault, curation_reviews())
            create_snapshot(
                plan,
                plan.snapshot_zip,
                plan.snapshot_manifest,
            )
            apply_curation(plan)
            trash_asset = (
                vault
                / "99_废纸篓"
                / "30_精选资料"
                / "AI"
                / "_attachments"
                / "car.png"
            )
            trash_asset.unlink()
            state_note = (
                vault
                / "30_精选资料"
                / "AI"
                / "2026年07月"
                / "Agent 状态.md"
            )
            state_text = state_note.read_text(encoding="utf-8")
            state_note.write_text(
                state_text.replace(
                    "- [[30_精选资料/AI/2026年07月/Agent 架构.md|Agent 架构]]\n",
                    "",
                ),
                encoding="utf-8",
            )

            issues = validate_completed_curation(plan)

        joined = "\n".join(issues)
        self.assertIn("废纸篓附件缺失", joined)
        self.assertIn("自动链接与审阅清单不一致", joined)


def write_review_json(path):
    payload = [
        {
            "path": review.path.as_posix(),
            "decision": review.decision,
            "reason": review.reason,
            "topic": review.topic,
            "links": [link.as_posix() for link in review.links],
        }
        for review in curation_reviews()
    ]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class CommandLineTests(unittest.TestCase):
    def test_preview_and_verify_default_to_global_vault(self):
        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            review_path = vault / "review.json"
            write_review_json(review_path)
            environment = os.environ.copy()
            environment["OBSIDIAN_VAULT_PATH"] = str(vault)

            preview = subprocess.run(
                [
                    sys.executable,
                    "scripts/curate_selected_materials.py",
                    "--review",
                    str(review_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            applied = subprocess.run(
                [
                    sys.executable,
                    "scripts/curate_selected_materials.py",
                    "--review",
                    str(review_path),
                    "--apply",
                    "--confirm",
                    "CURATE_SELECTED_MATERIALS",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            verified = subprocess.run(
                [
                    sys.executable,
                    "scripts/curate_selected_materials.py",
                    "--review",
                    str(review_path),
                    "--verify",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )

            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("预览模式", preview.stdout)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn("验证通过", verified.stdout)

    def test_preview_is_read_only_and_reports_counts(self):
        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            review_path = vault / "review.json"
            write_review_json(review_path)
            before = {
                path.relative_to(vault): path.read_bytes()
                for path in vault.rglob("*")
                if path.is_file()
            }

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/curate_selected_materials.py",
                    "--vault",
                    str(vault),
                    "--review",
                    str(review_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            after = {
                path.relative_to(vault): path.read_bytes()
                for path in vault.rglob("*")
                if path.is_file()
            }

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("审阅总数：3", result.stdout)
            self.assertIn("移入废纸篓：1", result.stdout)
            self.assertIn("双向链接边：1", result.stdout)
            self.assertEqual(after, before)

    def test_apply_requires_exact_confirmation(self):
        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            review_path = vault / "review.json"
            write_review_json(review_path)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/curate_selected_materials.py",
                    "--vault",
                    str(vault),
                    "--review",
                    str(review_path),
                    "--apply",
                    "--confirm",
                    "WRONG",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("CURATE_SELECTED_MATERIALS", result.stderr)
            self.assertFalse(
                (
                    vault
                    / "99_废纸篓"
                    / "30_精选资料"
                    / "AI"
                    / "2026年07月"
                    / "汽车新闻.md"
                ).exists()
            )

    def test_confirmed_apply_can_be_verified(self):
        with workspace_temp_dir() as vault:
            seed_curation_vault(vault)
            review_path = vault / "review.json"
            write_review_json(review_path)
            apply_command = [
                sys.executable,
                "scripts/curate_selected_materials.py",
                "--vault",
                str(vault),
                "--review",
                str(review_path),
                "--apply",
                "--confirm",
                "CURATE_SELECTED_MATERIALS",
            ]

            applied = subprocess.run(
                apply_command,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            verified = subprocess.run(
                [
                    sys.executable,
                    "scripts/curate_selected_materials.py",
                    "--vault",
                    str(vault),
                    "--review",
                    str(review_path),
                    "--verify",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn("验证通过", verified.stdout)
