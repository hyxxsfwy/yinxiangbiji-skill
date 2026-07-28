from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from evernote.edam.error.ttypes import EDAMSystemException

from tests.support import workspace_temp_dir


def metadata(guid, title, updated, created=1775000000000):
    return SimpleNamespace(
        guid=guid,
        title=title,
        updated=updated,
        created=created,
        notebookGuid="notebook-guid",
        contentLength=100,
    )


def full_note(item, content):
    return SimpleNamespace(
        **item.__dict__,
        content=content,
        resources=[],
    )


def keyword_union_payload():
    return {
        "since": "2026-04-01",
        "until": "2026-08-01",
        "selection_mode": "keyword_union",
        "domains": {
            "软件工程": {
                "keywords": ["软件工程", "项目管理"],
            },
            "AI": {
                "keywords": ["AI", "LLM", "HugginFace"],
            },
        },
        "aliases": {
            "HugginFace": ["HuggingFace", "Hugging Face"],
        },
    }


def seed_keyword_markdown(
    vault,
    *,
    domain,
    title,
    guid,
    created,
    body,
    updated="2026-05-03 10:00:00",
    updated_ms=1777773600000,
):
    path = (
        vault
        / "30_精选资料"
        / domain
        / f"{created[:4]}年{created[5:7]}月"
        / f"{title}.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "---",
                "type: 资料",
                f"domain: {domain}",
                f"created: {created}",
                f"updated: {updated}",
                f"source_guid: {guid}",
                f"source_updated_ms: {updated_ms}",
                "notebook: 收件箱",
                "---",
                "",
                f"# {title}",
                "",
                body,
                "",
            )
        ),
        encoding="utf-8",
    )
    return path


def legacy_v1_job_id(payload):
    legacy_vault = Path(payload["vault"]).expanduser().resolve()
    job_id_payload = {
        "since": payload["since"],
        "until": payload["until"],
        "vault": str(legacy_vault).casefold(),
        "domains": {
            domain: list(
                dict.fromkeys(
                    str(keyword).strip()
                    for keyword in settings["keywords"]
                    if str(keyword).strip()
                )
            )
            for domain, settings in sorted(payload["domains"].items())
        },
    }
    return hashlib.sha256(
        json.dumps(
            job_id_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]


class FakeNoteStore:
    def __init__(self, searches, notes, forbid_body=False):
        self.searches = searches
        self.notes = notes
        self.forbid_body = forbid_body
        self.body_calls = []
        self.search_calls = []

    def findNotesMetadata(
        self,
        _token,
        note_filter,
        offset,
        limit,
        _result_spec,
    ):
        keyword = note_filter.words.split(" ", 2)[-1]
        values = self.searches.get(keyword, [])
        self.search_calls.append((keyword, offset, limit))
        return SimpleNamespace(
            totalNotes=len(values),
            notes=values[offset:offset + limit],
        )

    def listNotebooks(self, _token):
        return [
            SimpleNamespace(
                guid="notebook-guid",
                name="微信",
            )
        ]

    def getNote(self, _token, guid, *_args):
        self.body_calls.append(guid)
        if self.forbid_body:
            raise AssertionError("目录命中时不得重复请求正文")
        return self.notes[guid]


class MultiDomainJobTestMixin:
    def test_keyword_union_accepts_controlled_new_domains_and_aliases(self):
        from scripts.export_multi_domain import normalize_job

        with workspace_temp_dir() as vault:
            job = normalize_job(keyword_union_payload(), vault)

        self.assertEqual(job.selection_mode, "keyword_union")
        self.assertEqual(job.since.isoformat(), "2026-04-01")
        self.assertEqual(job.until.isoformat(), "2026-08-01")
        self.assertEqual(
            job.aliases["HugginFace"],
            ("HuggingFace", "Hugging Face"),
        )
        self.assertEqual(
            job.target_for("软件工程"),
            vault.resolve() / "30_精选资料" / "软件工程",
        )

    def test_keyword_union_rejects_path_escape_and_unknown_alias_key(self):
        from scripts.export_multi_domain import normalize_job

        with workspace_temp_dir() as vault:
            payload = keyword_union_payload()
            payload["domains"]["../逃逸"] = {"keywords": ["逃逸"]}
            with self.assertRaisesRegex(ValueError, "领域名称"):
                normalize_job(payload, vault)

            payload = keyword_union_payload()
            payload["aliases"]["不存在"] = ["missing"]
            with self.assertRaisesRegex(ValueError, "别名键"):
                normalize_job(payload, vault)

    def test_template_is_device_path_independent(self):
        template = (
            Path(__file__).resolve().parent.parent
            / "templates"
            / "multi-domain-export-job.json"
        )

        payload = json.loads(template.read_text(encoding="utf-8"))

        self.assertNotIn("vault", payload)

    def test_job_id_is_device_path_independent(self):
        from scripts.export_multi_domain import _job_id, normalize_job

        payload = {
            "since": "2026-04-01",
            "until": "2026-07-01",
            "domains": {
                "AI": {"keywords": ["AI", "Agent"]},
                "Quant": {"keywords": ["Quant"]},
            },
        }
        with workspace_temp_dir() as temp_dir:
            first_vault = temp_dir / "first-vault"
            second_vault = temp_dir / "second-vault"
            first_vault.mkdir()
            second_vault.mkdir()

            try:
                first = normalize_job(payload, first_vault)
                second = normalize_job(payload, second_vault)
            except TypeError as exc:
                self.fail(f"任务加载尚未接受正式 Vault 参数: {exc}")

        self.assertEqual(_job_id(first), _job_id(second))

    def test_legacy_vault_field_is_warned_and_ignored(self):
        from scripts.export_multi_domain import load_job

        with workspace_temp_dir() as temp_dir:
            current_vault = temp_dir / "current-vault"
            legacy_vault = temp_dir / "legacy-vault"
            current_vault.mkdir()
            legacy_vault.mkdir()
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(
                    {
                        "since": "2026-04-01",
                        "until": "2026-07-01",
                        "vault": str(legacy_vault),
                        "domains": {
                            "AI": {"keywords": ["AI"]},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                job = load_job(job_file, current_vault)

        self.assertEqual(job.vault, current_vault.resolve())
        self.assertIn("vault 字段已废弃", output.getvalue())

    def test_non_object_job_payload_is_rejected_as_validation_error(self):
        from scripts.export_multi_domain import load_job

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            for index, payload in enumerate((None, 42)):
                with self.subTest(payload=payload):
                    job_file = temp_dir / f"job-{index}.json"
                    job_file.write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )

                    with self.assertRaises(ValueError):
                        load_job(job_file, vault)

    def test_job_validation_and_target_derivation(self):
        from scripts.export_multi_domain import normalize_job

        with workspace_temp_dir() as vault:
            valid = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {
                        "AI": {"keywords": ["AI", "Agent"]},
                        "Quant": {"keywords": ["Quant"]},
                    },
                },
                vault,
            )
            self.assertEqual(
                valid.target_for("AI"),
                vault.resolve() / "30_精选资料" / "AI",
            )

            invalid_payloads = (
                {
                    "since": "2026-07-01",
                    "until": "2026-07-01",
                    "domains": {"AI": {"keywords": ["AI"]}},
                },
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {"未知领域": {"keywords": ["AI"]}},
                },
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {"AI": {"keywords": []}},
                },
            )
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        normalize_job(payload, vault)
            with self.assertRaises(ValueError):
                normalize_job(
                    {
                        "since": "2026-04-01",
                        "until": "2026-07-01",
                        "domains": {"AI": {"keywords": ["AI"]}},
                    },
                    vault / "30_精选资料",
                )


class CommandLinePathTests(unittest.TestCase):
    @staticmethod
    def _payload():
        return {
            "since": "2026-04-01",
            "until": "2026-07-01",
            "domains": {
                "AI": {"keywords": ["AI"]},
            },
        }

    def _run_main(self, vault, job_file, *extra_args):
        from scripts import export_multi_domain
        from scripts.vault_state import VaultStatePaths

        paths = VaultStatePaths.for_vault(vault)
        dispatched = {}

        def fake_run_export_job(_job, _store, _token, **kwargs):
            self.assertTrue(
                paths.lock.is_file(),
                "run_export_job 必须在 runtime_write_lock 内执行",
            )
            dispatched.update(kwargs)
            if _job.selection_mode == "keyword_union":
                return {
                    "ok": True,
                    "candidates": {
                        "unique_guids": 0,
                        "body_requests": 0,
                        "accepted": 0,
                        "rejected": 0,
                        "duplicate_titles": 0,
                    },
                    "cache": {
                        "hits": 0,
                        "body_requests_saved": 0,
                    },
                    "materialization": {
                        "written": 0,
                        "already_exported": 0,
                    },
                }
            return {
                "ok": True,
                "candidates": {
                    "unique_guids": 0,
                    "body_requests": 0,
                    "catalog_hits": 0,
                    "body_requests_saved": 0,
                },
            }

        argv = [
            "export_multi_domain.py",
            "--job",
            str(job_file),
            *map(str, extra_args),
        ]
        environment = {
            "OBSIDIAN_VAULT_PATH": str(vault),
            "EVERNOTE_TOKEN": "test-token",
            "EVERNOTE_NOTESTORE_URL": "https://example.invalid",
        }
        with (
            patch.object(sys, "argv", argv),
            patch.dict(os.environ, environment, clear=False),
            patch.object(
                export_multi_domain,
                "create_note_store",
                return_value=object(),
            ),
            patch.object(
                export_multi_domain,
                "run_export_job",
                side_effect=fake_run_export_job,
            ),
            redirect_stdout(io.StringIO()),
        ):
            result = export_multi_domain.main()
        self.assertFalse(paths.lock.exists())
        return result, dispatched

    def test_keyword_union_main_prints_new_report_shape_without_key_error(self):
        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(
                    keyword_union_payload(),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result, _dispatched = self._run_main(vault, job_file)

        self.assertEqual(result, 0)

    def test_defaults_follow_each_vault_state_namespace(self):
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(self._payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            dispatched_by_vault = []
            task_ids = []
            for name in ("first-vault", "second-vault"):
                vault = temp_dir / name
                (vault / ".obsidian").mkdir(parents=True)
                result, dispatched = self._run_main(vault, job_file)
                dispatched_by_vault.append((vault, dispatched))
                task_ids.append(_job_id(normalize_job(self._payload(), vault)))
                self.assertEqual(result, 0)

        self.assertEqual(task_ids[0], task_ids[1])
        for vault, dispatched in dispatched_by_vault:
            paths = VaultStatePaths.for_vault(vault)
            self.assertEqual(dispatched["catalog_path"], paths.catalog)
            self.assertEqual(
                dispatched["state_file"],
                paths.runs / f"multi-export-{task_ids[0]}.json",
            )
            self.assertEqual(
                dispatched["report_file"],
                paths.reports / f"{task_ids[0]}.json",
            )

    def test_main_migrates_legacy_default_state_into_paths_it_uses(self):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            repo_root = temp_dir / "repo"
            legacy_state = repo_root / ".state"
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            job_file = temp_dir / "job.json"
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job_file.write_text(
                json.dumps(legacy_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(normalize_job(self._payload(), vault))
            legacy_state.mkdir(parents=True)
            (legacy_state / "reports").mkdir()
            catalog_bytes = b"legacy-catalog"
            run_bytes = json.dumps(
                {
                    "version": 1,
                    "job_id": v1_task_id,
                    "processed": {"legacy-guid": {"outcome": "accepted"}},
                },
                ensure_ascii=False,
            ).encode("utf-8")
            report_bytes = json.dumps(
                {
                    "job": {
                        "id": v1_task_id,
                        "since": legacy_payload["since"],
                        "until": legacy_payload["until"],
                        "vault": str(legacy_vault.resolve()),
                        "domains": {
                            domain: settings["keywords"]
                            for domain, settings in legacy_payload[
                                "domains"
                            ].items()
                        },
                    },
                    "ok": True,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            (legacy_state / "export-catalog.sqlite3").write_bytes(
                catalog_bytes
            )
            (legacy_state / f"multi-export-{v1_task_id}.json").write_bytes(
                run_bytes
            )
            (legacy_state / "reports" / f"{v1_task_id}.json").write_bytes(
                report_bytes
            )

            with patch.object(export_multi_domain, "REPO_ROOT", repo_root):
                result, dispatched = self._run_main(vault, job_file)

            paths = VaultStatePaths.for_vault(vault)
            self.assertEqual(result, 0)
            self.assertEqual(dispatched["catalog_path"], paths.catalog)
            self.assertEqual(
                dispatched["state_file"],
                paths.runs / f"multi-export-{v2_task_id}.json",
            )
            self.assertEqual(
                dispatched["report_file"],
                paths.reports / f"{v2_task_id}.json",
            )
            self.assertEqual(paths.catalog.read_bytes(), catalog_bytes)
            self.assertEqual(
                dispatched["state_file"].read_bytes(),
                run_bytes,
            )
            self.assertEqual(
                dispatched["report_file"].read_bytes(),
                report_bytes,
            )

    def test_active_lock_blocks_migration_and_v1_state_takeover(self):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import (
            StateLockConflict,
            VaultStatePaths,
            runtime_write_lock,
        )

        with workspace_temp_dir() as temp_dir:
            repo_root = temp_dir / "repo"
            legacy_state = repo_root / ".state"
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_state.mkdir(parents=True)
            (legacy_state / "export-catalog.sqlite3").write_bytes(
                b"migratable-catalog"
            )
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(legacy_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(normalize_job(self._payload(), vault))
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            paths.reports.mkdir(parents=True)
            v1_run = paths.runs / f"multi-export-{v1_task_id}.json"
            v1_report = paths.reports / f"{v1_task_id}.json"
            v1_run.write_bytes(b'{"source":"v1-run"}\n')
            v1_report.write_bytes(b'{"source":"v1-report"}\n')
            v2_run = paths.runs / f"multi-export-{v2_task_id}.json"
            v2_report = paths.reports / f"{v2_task_id}.json"

            with (
                runtime_write_lock(paths, "active-task"),
                patch.object(export_multi_domain, "REPO_ROOT", repo_root),
                self.assertRaises(StateLockConflict),
            ):
                self._run_main(vault, job_file)

            self.assertFalse(paths.catalog.exists())
            self.assertEqual(
                tuple(paths.migrations.glob("migration-*.json")),
                (),
            )
            self.assertEqual(v1_run.read_bytes(), b'{"source":"v1-run"}\n')
            self.assertEqual(
                v1_report.read_bytes(),
                b'{"source":"v1-report"}\n',
            )
            self.assertFalse(v2_run.exists())
            self.assertFalse(v2_report.exists())

    def test_legacy_state_takeover_refuses_conflicting_v2_target(self):
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(legacy_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(normalize_job(self._payload(), vault))
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            v1_run = paths.runs / f"multi-export-{v1_task_id}.json"
            v2_run = paths.runs / f"multi-export-{v2_task_id}.json"
            v1_run.write_bytes(b'{"source":"v1"}\n')
            v2_run.write_bytes(b'{"source":"v2"}\n')

            with self.assertRaises(SystemExit) as raised:
                self._run_main(vault, job_file)

            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(v1_run.read_bytes(), b'{"source":"v1"}\n')
            self.assertEqual(v2_run.read_bytes(), b'{"source":"v2"}\n')

    def test_legacy_state_takeover_preflights_all_targets_before_copying(self):
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(legacy_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(normalize_job(self._payload(), vault))
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            paths.reports.mkdir(parents=True)
            (paths.runs / f"multi-export-{v1_task_id}.json").write_bytes(
                b'{"source":"v1-run"}\n'
            )
            (paths.reports / f"{v1_task_id}.json").write_bytes(
                b'{"source":"v1-report"}\n'
            )
            v2_run = paths.runs / f"multi-export-{v2_task_id}.json"
            v2_report = paths.reports / f"{v2_task_id}.json"
            v2_report.write_bytes(b'{"source":"v2-report"}\n')

            with self.assertRaises(SystemExit):
                self._run_main(vault, job_file)

            self.assertFalse(v2_run.exists())
            self.assertEqual(
                v2_report.read_bytes(),
                b'{"source":"v2-report"}\n',
            )

    def test_legacy_state_takeover_rolls_back_run_after_report_race(self):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job = normalize_job(self._payload(), vault)
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(job)
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            paths.reports.mkdir(parents=True)
            v1_run = paths.runs / f"multi-export-{v1_task_id}.json"
            v1_report = paths.reports / f"{v1_task_id}.json"
            v2_run = paths.runs / f"multi-export-{v2_task_id}.json"
            v2_report = paths.reports / f"{v2_task_id}.json"
            v1_run_bytes = b'{"source":"v1-run"}\n'
            v1_report_bytes = b'{"source":"v1-report"}\n'
            concurrent_report_bytes = b'{"source":"concurrent-report"}\n'
            v1_run.write_bytes(v1_run_bytes)
            v1_report.write_bytes(v1_report_bytes)
            real_link = os.link
            link_calls = 0

            def publish_with_report_race(staged, target):
                nonlocal link_calls
                link_calls += 1
                if link_calls == 2:
                    Path(target).write_bytes(concurrent_report_bytes)
                return real_link(staged, target)

            with (
                patch.object(
                    export_multi_domain.os,
                    "link",
                    side_effect=publish_with_report_race,
                ),
                self.assertRaises(ValueError),
            ):
                export_multi_domain._adopt_legacy_job_state(
                    paths,
                    job,
                    legacy_payload,
                )

            self.assertEqual(link_calls, 2)
            self.assertFalse(v2_run.exists())
            self.assertEqual(v2_report.read_bytes(), concurrent_report_bytes)
            self.assertEqual(v1_run.read_bytes(), v1_run_bytes)
            self.assertEqual(v1_report.read_bytes(), v1_report_bytes)

    def test_legacy_state_takeover_rollback_preserves_replaced_target(self):
        from scripts.export_multi_domain import _rollback_adopted_targets

        with workspace_temp_dir() as temp_dir:
            target = temp_dir / "run.json"
            replacement = temp_dir / "replacement.json"
            content = b'{"same":"content"}\n'
            target.write_bytes(content)
            created_stat = target.stat()
            replacement.write_bytes(content)
            os.replace(replacement, target)
            replacement_stat = target.stat()

            _rollback_adopted_targets([(target, created_stat)])

            restored_stat = target.stat()
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(restored_stat.st_dev, replacement_stat.st_dev)
            self.assertEqual(restored_stat.st_ino, replacement_stat.st_ino)

    def test_legacy_state_takeover_preserves_publish_error_when_rollback_fails(
        self,
    ):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job = normalize_job(self._payload(), vault)
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(job)
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            paths.reports.mkdir(parents=True)
            (paths.runs / f"multi-export-{v1_task_id}.json").write_bytes(
                b'{"source":"v1-run"}\n'
            )
            (paths.reports / f"{v1_task_id}.json").write_bytes(
                b'{"source":"v1-report"}\n'
            )
            v2_run = paths.runs / f"multi-export-{v2_task_id}.json"
            v2_report = paths.reports / f"{v2_task_id}.json"
            replacement = temp_dir / "replacement-run.json"
            real_link = os.link
            link_calls = 0

            def publish_and_fail_rollback(staged, target):
                nonlocal link_calls
                link_calls += 1
                if link_calls == 2:
                    replacement.write_bytes(b'{"source":"replacement-run"}\n')
                    os.replace(replacement, v2_run)
                    v2_report.write_bytes(
                        b'{"source":"concurrent-report"}\n'
                    )
                elif link_calls == 3:
                    v2_run.write_bytes(b'{"source":"third-run"}\n')
                return real_link(staged, target)

            with (
                patch.object(
                    export_multi_domain.os,
                    "link",
                    side_effect=publish_and_fail_rollback,
                ),
                self.assertRaises(ValueError) as raised,
            ):
                export_multi_domain._adopt_legacy_job_state(
                    paths,
                    job,
                    legacy_payload,
                )

            self.assertIn("v1 状态与并发创建的 v2 状态冲突", str(raised.exception))
            notes = getattr(raised.exception, "__notes__", ())
            self.assertTrue(
                any(
                    "接管回滚时目标被再次占用" in note
                    and ".rollback" in note
                    for note in notes
                )
            )
            self.assertEqual(link_calls, 3)
            self.assertEqual(v2_run.read_bytes(), b'{"source":"third-run"}\n')

    def test_legacy_state_takeover_preserves_control_flow_base_exceptions(
        self,
    ):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job = normalize_job(self._payload(), vault)
            v1_task_id = legacy_v1_job_id(legacy_payload)
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            (paths.runs / f"multi-export-{v1_task_id}.json").write_bytes(
                b'{"source":"v1-run"}\n'
            )

            for original in (KeyboardInterrupt("中断"), SystemExit(73)):
                with self.subTest(exception=type(original).__name__):
                    with (
                        patch.object(
                            export_multi_domain,
                            "_copy_without_overwrite",
                            side_effect=original,
                        ),
                        patch.object(
                            export_multi_domain,
                            "_rollback_adopted_targets",
                            side_effect=RuntimeError("回滚失败"),
                        ),
                        self.assertRaises(type(original)) as raised,
                    ):
                        export_multi_domain._adopt_legacy_job_state(
                            paths,
                            job,
                            legacy_payload,
                        )

                    self.assertIs(raised.exception, original)
                    self.assertTrue(
                        any(
                            "回滚失败" in note
                            for note in getattr(original, "__notes__", ())
                        )
                    )

    def test_legacy_state_takeover_reuses_identical_v2_targets(self):
        from scripts.export_multi_domain import _job_id, normalize_job
        from scripts.vault_state import VaultStatePaths

        with workspace_temp_dir() as temp_dir:
            legacy_vault = temp_dir / "legacy-device-vault"
            vault = temp_dir / "vault"
            legacy_vault.mkdir()
            (vault / ".obsidian").mkdir(parents=True)
            legacy_payload = {
                **self._payload(),
                "vault": str(legacy_vault),
            }
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(legacy_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            v1_task_id = legacy_v1_job_id(legacy_payload)
            v2_task_id = _job_id(normalize_job(self._payload(), vault))
            paths = VaultStatePaths.for_vault(vault)
            paths.runs.mkdir(parents=True)
            content = b'{"same":"state"}\n'
            for task_id in (v1_task_id, v2_task_id):
                (paths.runs / f"multi-export-{task_id}.json").write_bytes(
                    content
                )

            result, dispatched = self._run_main(vault, job_file)

            self.assertEqual(result, 0)
            self.assertEqual(dispatched["state_file"].read_bytes(), content)

    def test_explicit_output_paths_cannot_escape_state_namespace(self):
        from scripts import export_multi_domain

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            job_file = temp_dir / "job.json"
            job_file.write_text(
                json.dumps(self._payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            environment = {
                "OBSIDIAN_VAULT_PATH": str(vault),
                "EVERNOTE_TOKEN": "test-token",
                "EVERNOTE_NOTESTORE_URL": "https://example.invalid",
            }
            for flag in ("--catalog", "--state-file", "--report-file"):
                with self.subTest(flag=flag):
                    argv = [
                        "export_multi_domain.py",
                        "--job",
                        str(job_file),
                        flag,
                        str(temp_dir / "outside.json"),
                    ]
                    with (
                        patch.object(sys, "argv", argv),
                        patch.dict(os.environ, environment, clear=False),
                        patch.object(
                            export_multi_domain,
                            "create_note_store",
                            return_value=object(),
                        ),
                        patch.object(
                            export_multi_domain,
                            "run_export_job",
                            return_value={
                                "ok": True,
                                "candidates": {
                                    "unique_guids": 0,
                                    "body_requests": 0,
                                    "catalog_hits": 0,
                                    "body_requests_saved": 0,
                                },
                            },
                        ),
                        redirect_stdout(io.StringIO()),
                        redirect_stderr(io.StringIO()),
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            export_multi_domain.main()
                    self.assertEqual(raised.exception.code, 2)


class MultiDomainJobTests(MultiDomainJobTestMixin, unittest.TestCase):
    def test_keyword_report_accounts_for_every_unique_guid(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        newest = metadata("guid-new", "同标题 AI", 1780000000000)
        older = metadata("guid-old", "同标题 AI", 1779000000000)
        rejected = metadata("guid-rejected", "training", 1778000000000)
        store = FakeNoteStore(
            {"AI": [newest, older, rejected]},
            {
                "guid-new": full_note(
                    newest,
                    "<en-note>AI</en-note>",
                ),
                "guid-old": full_note(
                    older,
                    "<en-note>AI</en-note>",
                ),
                "guid-rejected": full_note(
                    rejected,
                    "<en-note>training</en-note>",
                ),
            },
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(keyword_union_payload(), vault)
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

        counts = report["candidates"]
        self.assertEqual(
            counts["unique_guids"],
            counts["accepted"]
            + counts["rejected"]
            + counts["duplicate_titles"],
        )
        self.assertEqual(
            report["cache"]["rows_for_candidates"],
            counts["unique_guids"],
        )
        self.assertEqual(len(store.body_calls), 3)
        self.assertTrue(report["searches_complete"])
        self.assertTrue(report["ok"], report)
        self.assertTrue(
            all(value == 0 for value in report["integrity_summary"].values())
        )

    def test_keyword_snapshot_exists_before_first_materialization(self):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import (
            _job_id,
            normalize_job,
            run_export_job,
        )

        item = metadata("guid-1", "AI Agent", 1780000000000)
        store = FakeNoteStore(
            {"AI": [item]},
            {
                "guid-1": full_note(
                    item,
                    "<en-note>AI Agent</en-note>",
                )
            },
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            seed_keyword_markdown(
                vault,
                domain="AI",
                title="AI 旧文章",
                guid="existing-guid",
                created="2026-05-01 10:00:00",
                body="AI before",
            )
            job = normalize_job(keyword_union_payload(), vault)
            snapshot = (
                vault
                / ".state"
                / "yinxiang-notes"
                / "snapshots"
                / f"{_job_id(job)}-before.zip"
            )
            real_export = export_multi_domain.export_note_to_obsidian

            def assert_snapshot_first(note, *args, **kwargs):
                self.assertTrue(snapshot.is_file())
                return real_export(note, *args, **kwargs)

            with patch(
                "scripts.export_multi_domain.export_note_to_obsidian",
                side_effect=assert_snapshot_first,
            ):
                report = run_export_job(
                    job,
                    store,
                    "token",
                    catalog_path=temp_dir / "catalog.sqlite3",
                    state_file=temp_dir / "state.json",
                    report_file=temp_dir / "report.json",
                    rate_limit_mode="stop",
                    max_rate_limit_wait=0,
                )

            self.assertEqual(
                Path(report["snapshot"]["archive"]),
                snapshot,
            )
            self.assertTrue(
                Path(report["snapshot"]["manifest"]).is_file()
            )

    def test_keyword_union_searches_every_query_term_and_merges_guid(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.keyword_selection import expanded_query_terms

        same = metadata("same", "软件工程 AI", 1780000000000)
        hugging_face = metadata("hf", "HuggingFace", 1779000000000)
        store = FakeNoteStore(
            {
                "软件工程": [same],
                "AI": [same],
                "HuggingFace": [hugging_face],
                "Hugging Face": [hugging_face],
            },
            {
                "same": full_note(
                    same,
                    "<en-note>软件工程 AI</en-note>",
                ),
                "hf": full_note(
                    hugging_face,
                    "<en-note>Hugging Face</en-note>",
                ),
            },
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(keyword_union_payload(), vault)
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

        expected_terms = {
            query_term
            for _domain, _canonical, query_term in expanded_query_terms(
                job.domains,
                job.aliases,
            )
        }
        self.assertEqual(
            {item["query_term"] for item in report["searches"]},
            expected_terms,
        )
        self.assertEqual(report["candidates"]["unique_guids"], 2)
        self.assertEqual(store.body_calls.count("same"), 1)
        self.assertEqual(store.body_calls.count("hf"), 1)
        self.assertTrue(
            all(
                item["pulled"] == item["total"]
                for item in report["searches"]
            )
        )

    def test_keyword_union_records_current_candidate_before_body_fetch(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        item = metadata("stalled-guid", "AI Agent", 1780000000000)

        class FailingBodyStore(FakeNoteStore):
            def getNote(self, _token, guid, *_args):
                raise RuntimeError(f"body fetch failed: {guid}")

        store = FailingBodyStore({"AI": [item]}, {})

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(keyword_union_payload(), vault)
            state_file = temp_dir / "state.json"

            with self.assertRaisesRegex(RuntimeError, "body fetch failed"):
                run_export_job(
                    job,
                    store,
                    "token",
                    catalog_path=temp_dir / "catalog.sqlite3",
                    state_file=state_file,
                    report_file=temp_dir / "report.json",
                    rate_limit_mode="stop",
                    max_rate_limit_wait=0,
                )

            state = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(
            state["current_candidate"],
            {
                "guid": "stalled-guid",
                "phase": "fetch_note",
                "updated_ms": 1780000000000,
            },
        )
        self.assertEqual(state["candidate_count"], 1)

    def test_keyword_analysis_is_committed_before_materialization(self):
        from scripts.export_catalog import ExportCatalog
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.keyword_selection import keyword_selection_hash

        item = metadata("guid-1", "AI Agent", 1780000000000)
        store = FakeNoteStore(
            {"AI": [item]},
            {
                "guid-1": full_note(
                    item,
                    "<en-note>AI Agent</en-note>",
                )
            },
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(keyword_union_payload(), vault)
            catalog_path = temp_dir / "catalog.sqlite3"
            with patch(
                "scripts.export_multi_domain.export_note_to_obsidian",
                side_effect=RuntimeError("模拟写入中断"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "模拟写入中断",
                ):
                    run_export_job(
                        job,
                        store,
                        "token",
                        catalog_path=catalog_path,
                        state_file=temp_dir / "state.json",
                        report_file=temp_dir / "report.json",
                        rate_limit_mode="stop",
                        max_rate_limit_wait=0,
                    )

            state = json.loads(
                (temp_dir / "state.json").read_text(encoding="utf-8")
            )
            selection_hash = keyword_selection_hash(
                job.domains,
                job.aliases,
            )
            with ExportCatalog(catalog_path) as catalog:
                entry = catalog.get_keyword_current(
                    "guid-1",
                    item.updated,
                    selection_hash,
                )

        self.assertEqual(entry.outcome, "accepted")
        self.assertIsNone(entry.canonical_path)
        self.assertEqual(
            state["current_candidate"]["phase"],
            "materialize",
        )

    def test_no_literal_boundary_match_is_cached_as_rejected(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        item = metadata("guid-1", "training", 1780000000000)
        store = FakeNoteStore(
            {"AI": [item]},
            {
                "guid-1": full_note(
                    item,
                    "<en-note>training</en-note>",
                )
            },
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(keyword_union_payload(), vault)
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

        self.assertEqual(report["candidates"]["rejected"], 1)
        self.assertEqual(report["materialization"]["written"], 0)

    def test_keyword_job_resumes_from_sqlite_without_refetching_analysis(self):
        from scripts import export_multi_domain
        from scripts.export_multi_domain import normalize_job, run_export_job

        first = metadata("guid-1", "AI Agent", 1780000000000)
        second = metadata("guid-2", "LLM", 1779000000000)
        searches = {"AI": [first], "LLM": [second]}
        notes = {
            "guid-1": full_note(
                first,
                "<en-note>AI Agent</en-note>",
            ),
            "guid-2": full_note(
                second,
                "<en-note>LLM</en-note>",
            ),
        }

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(keyword_union_payload(), vault)
            catalog_path = temp_dir / "catalog.sqlite3"
            real_export = export_multi_domain.export_note_to_obsidian

            def fail_second(note, *args, **kwargs):
                if note.guid == "guid-2":
                    raise RuntimeError("模拟第二篇物化中断")
                return real_export(note, *args, **kwargs)

            first_store = FakeNoteStore(searches, notes)
            with patch(
                "scripts.export_multi_domain.export_note_to_obsidian",
                side_effect=fail_second,
            ):
                with self.assertRaisesRegex(RuntimeError, "物化中断"):
                    run_export_job(
                        job,
                        first_store,
                        "token",
                        catalog_path=catalog_path,
                        state_file=temp_dir / "state.json",
                        report_file=temp_dir / "report.json",
                        rate_limit_mode="stop",
                        max_rate_limit_wait=0,
                    )

            second_store = FakeNoteStore(searches, notes)
            report = run_export_job(
                job,
                second_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

        self.assertNotIn("guid-1", second_store.body_calls)
        self.assertEqual(second_store.body_calls.count("guid-2"), 1)
        self.assertGreaterEqual(report["cache"]["hits"], 2)

    def test_existing_keyword_markdown_bootstraps_keyword_cache(self):
        from scripts.export_catalog import ExportCatalog
        from scripts.export_multi_domain import (
            bootstrap_keyword_catalog_from_vault,
            normalize_job,
        )
        from scripts.keyword_selection import keyword_selection_hash

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            seed_keyword_markdown(
                vault,
                domain="AI",
                title="AI Agent",
                guid="guid-existing",
                created="2026-05-02 10:00:00",
                body="AI Agent 与 MCP",
            )
            job = normalize_job(keyword_union_payload(), vault)
            selection_hash = keyword_selection_hash(
                job.domains,
                job.aliases,
            )
            catalog_path = temp_dir / "export-catalog.sqlite3"

            with ExportCatalog(catalog_path) as catalog:
                count = bootstrap_keyword_catalog_from_vault(
                    job,
                    catalog,
                    selection_hash,
                    "2026-07-29T10:00:00+08:00",
                )
                entry = catalog.get_keyword_current(
                    "guid-existing",
                    1777773600000,
                    selection_hash,
                )

            self.assertEqual(count, 1)
            self.assertEqual(entry.primary_domain, "AI")
            self.assertIn("AI", entry.matched_keywords)
            self.assertTrue(
                entry.canonical_path.endswith("AI Agent.md")
            )

    def test_keyword_bootstrap_skips_out_of_range_or_missing_attachment(self):
        from scripts.export_catalog import ExportCatalog
        from scripts.export_multi_domain import (
            bootstrap_keyword_catalog_from_vault,
            normalize_job,
        )
        from scripts.keyword_selection import keyword_selection_hash

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            seed_keyword_markdown(
                vault,
                domain="AI",
                title="AI 旧资料",
                guid="old",
                created="2026-03-31 23:59:59",
                body="AI",
            )
            seed_keyword_markdown(
                vault,
                domain="AI",
                title="AI 缺图",
                guid="broken",
                created="2026-04-01 00:00:00",
                body="AI ![图](../_attachments/missing.png)",
            )
            job = normalize_job(keyword_union_payload(), vault)
            selection_hash = keyword_selection_hash(
                job.domains,
                job.aliases,
            )
            catalog_path = temp_dir / "export-catalog.sqlite3"

            with ExportCatalog(catalog_path) as catalog:
                count = bootstrap_keyword_catalog_from_vault(
                    job,
                    catalog,
                    selection_hash,
                    "2026-07-29T10:00:00+08:00",
                )

            self.assertEqual(count, 0)

    def test_each_guid_is_fetched_once_and_titles_are_globally_deduplicated(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        shared = metadata("shared-guid", "跨关键词文章", 1780000000000)
        newest = metadata("new-guid", "完全一致标题", 1779000000000)
        oldest = metadata("old-guid", "完全一致标题", 1778000000000)
        searches = {
            "AI": [shared],
            "Agent": [shared],
            "Quant": [newest, oldest],
        }
        notes = {
            "shared-guid": full_note(
                shared,
                "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
            ),
            "new-guid": full_note(
                newest,
                "<en-note>量化交易、量化研究、因子投资、回测和最大回撤。</en-note>",
            ),
            "old-guid": full_note(
                oldest,
                "<en-note>量化交易、量化研究、多因子、回测和夏普。</en-note>",
            ),
        }

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {
                        "AI": {"keywords": ["AI", "Agent"]},
                        "Quant": {"keywords": ["Quant"]},
                    },
                },
                vault,
            )
            store = FakeNoteStore(searches, notes)
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(
                store.body_calls,
                ["shared-guid", "new-guid"],
            )
            self.assertEqual(report["candidates"]["unique_guids"], 3)
            self.assertEqual(report["candidates"]["body_requests"], 2)
            self.assertEqual(report["candidates"]["duplicate_titles"], 1)
            self.assertTrue(report["ok"])
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "AI"
                    / "2026年04月"
                    / "跨关键词文章.md"
                ).is_file()
            )
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "Quant"
                    / "2026年04月"
                    / "完全一致标题.md"
                ).is_file()
            )
            self.assertEqual(
                len(
                    list(
                        (vault / "30_精选资料").rglob(
                            "完全一致标题.md"
                        )
                    )
                ),
                1,
            )

    def test_changed_keywords_reuse_catalog_without_refetching_body(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        item = metadata("cached-guid", "可复用文章", 1780000000000)
        note = full_note(
            item,
            "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            common = {
                "since": "2026-04-01",
                "until": "2026-07-01",
            }
            first_job = normalize_job(
                {
                    **common,
                    "domains": {
                        "AI": {"keywords": ["Claude"]},
                    },
                },
                vault,
            )
            catalog_path = temp_dir / "catalog.sqlite3"
            first_store = FakeNoteStore(
                {"Claude": [item]},
                {"cached-guid": note},
            )
            run_export_job(
                first_job,
                first_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "first-state.json",
                report_file=temp_dir / "first-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )
            self.assertEqual(first_store.body_calls, ["cached-guid"])

            second_job = normalize_job(
                {
                    **common,
                    "domains": {
                        "AI": {"keywords": ["LLM"]},
                    },
                },
                vault,
            )
            second_store = FakeNoteStore(
                {"LLM": [item]},
                {},
                forbid_body=True,
            )
            report = run_export_job(
                second_job,
                second_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "second-state.json",
                report_file=temp_dir / "second-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(second_store.body_calls, [])
            self.assertEqual(report["candidates"]["catalog_hits"], 1)
            self.assertEqual(
                report["candidates"]["body_requests_saved"],
                1,
            )
            self.assertTrue(report["ok"])
            persisted = json.loads(
                (temp_dir / "second-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                persisted["candidates"]["catalog_hits"],
                1,
            )

    def test_cached_outside_domain_is_rechecked_when_domain_is_added(self):
        from scripts.export_multi_domain import normalize_job, run_export_job

        item = metadata("investment-guid", "跨任务领域变化", 1780000000123)
        note = full_note(
            item,
            "<en-note>基金配置、股票估值、投资组合、资产配置和风险控制。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            catalog_path = temp_dir / "catalog.sqlite3"
            common = {
                "since": "2026-04-01",
                "until": "2026-07-01",
            }
            first_job = normalize_job(
                {
                    **common,
                    "domains": {"AI": {"keywords": ["AI"]}},
                },
                vault,
            )
            first_store = FakeNoteStore(
                {"AI": [item]},
                {"investment-guid": note},
            )
            run_export_job(
                first_job,
                first_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "first-state.json",
                report_file=temp_dir / "first-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            second_job = normalize_job(
                {
                    **common,
                    "domains": {
                        "投资理财": {"keywords": ["基金"]},
                    },
                },
                vault,
            )
            second_store = FakeNoteStore(
                {"基金": [item]},
                {"investment-guid": note},
            )
            second_report = run_export_job(
                second_job,
                second_store,
                "token",
                catalog_path=catalog_path,
                state_file=temp_dir / "second-state.json",
                report_file=temp_dir / "second-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(first_store.body_calls, ["investment-guid"])
            self.assertEqual(second_store.body_calls, ["investment-guid"])
            self.assertEqual(second_report["candidates"]["accepted"], 1)
            self.assertTrue(
                (
                    vault
                    / "30_精选资料"
                    / "投资理财"
                    / "2026年04月"
                    / "跨任务领域变化.md"
                ).is_file()
            )

    def test_integrity_scans_existing_domains_outside_current_job(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.export_search_results import export_note_to_obsidian
        from scripts.knowledge_base import finalize_knowledge_base

        existing = metadata("existing-investment", "跨领域同标题", 1779000000000)
        candidate = metadata("new-ai", "跨领域同标题", 1780000000000)
        existing_note = full_note(
            existing,
            "<en-note>基金配置、股票估值、投资组合、资产配置和风险控制。</en-note>",
        )
        candidate_note = full_note(
            candidate,
            "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            investment_target = vault / "30_精选资料" / "投资理财"
            export_note_to_obsidian(
                existing_note,
                notebook_name="微信",
                target_dir=investment_target,
                domain="投资理财",
            )
            finalize_knowledge_base(investment_target, domain="投资理财")
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {"AI": {"keywords": ["AI"]}},
                },
                vault,
            )
            report = run_export_job(
                job,
                FakeNoteStore(
                    {"AI": [candidate]},
                    {"new-ai": candidate_note},
                ),
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertFalse(report["ok"])
            self.assertEqual(
                set(report["integrity"]["cross_domain_title_duplicates"]),
                {"跨领域同标题"},
            )

    def test_existing_export_bootstraps_catalog_before_new_keyword_task(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.export_search_results import export_note_to_obsidian

        item = metadata("historical-guid", "历史已拉取文章", 1780000000000)
        note = full_note(
            item,
            "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
        )

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            export_note_to_obsidian(
                note,
                notebook_name="微信",
                target_dir=vault / "30_精选资料" / "AI",
                domain="AI",
            )
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {
                        "AI": {"keywords": ["新关键词"]},
                    },
                },
                vault,
            )
            store = FakeNoteStore(
                {"新关键词": [item]},
                {},
                forbid_body=True,
            )
            report = run_export_job(
                job,
                store,
                "token",
                catalog_path=temp_dir / "catalog.sqlite3",
                state_file=temp_dir / "state.json",
                report_file=temp_dir / "report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(store.body_calls, [])
            self.assertEqual(
                report["candidates"]["catalog_bootstrapped"],
                1,
            )
            self.assertEqual(report["candidates"]["catalog_hits"], 1)
            self.assertEqual(
                report["candidates"]["body_requests_saved"],
                1,
            )
            self.assertTrue(report["ok"])

    def test_interrupted_job_resumes_from_catalog_without_refetching_completed_body(self):
        from scripts.export_multi_domain import normalize_job, run_export_job
        from scripts.runtime import RateLimitBudgetExceeded

        first = metadata("first-guid", "第一篇", 1780000000000)
        second = metadata("second-guid", "第二篇", 1779000000000)
        notes = {
            "first-guid": full_note(
                first,
                "<en-note>大语言模型、RAG、智能体、机器学习和模型推理。</en-note>",
            ),
            "second-guid": full_note(
                second,
                "<en-note>大语言模型、RAG、智能体、深度学习和模型训练。</en-note>",
            ),
        }

        class InterruptedStore(FakeNoteStore):
            def getNote(self, token, guid, *args):
                if guid == "second-guid":
                    self.body_calls.append(guid)
                    raise EDAMSystemException(
                        errorCode=19,
                        rateLimitDuration=30,
                    )
                return super().getNote(token, guid, *args)

        with workspace_temp_dir() as temp_dir:
            vault = temp_dir / "vault"
            vault.mkdir()
            job = normalize_job(
                {
                    "since": "2026-04-01",
                    "until": "2026-07-01",
                    "domains": {"AI": {"keywords": ["AI"]}},
                },
                vault,
            )
            catalog_path = temp_dir / "catalog.sqlite3"
            state_path = temp_dir / "state.json"
            first_store = InterruptedStore(
                {"AI": [first, second]},
                notes,
            )
            with self.assertRaises(RateLimitBudgetExceeded):
                run_export_job(
                    job,
                    first_store,
                    "token",
                    catalog_path=catalog_path,
                    state_file=state_path,
                    report_file=temp_dir / "interrupted-report.json",
                    rate_limit_mode="stop",
                    max_rate_limit_wait=0,
                )
            state = json.loads(
                state_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                state["processed"]["first-guid"]["outcome"],
                "accepted",
            )

            resumed_store = FakeNoteStore(
                {"AI": [first, second]},
                notes,
            )
            report = run_export_job(
                job,
                resumed_store,
                "token",
                catalog_path=catalog_path,
                state_file=state_path,
                report_file=temp_dir / "resumed-report.json",
                rate_limit_mode="stop",
                max_rate_limit_wait=0,
            )

            self.assertEqual(resumed_store.body_calls, ["second-guid"])
            self.assertEqual(report["candidates"]["catalog_hits"], 1)
            self.assertEqual(
                report["candidates"]["body_requests_saved"],
                1,
            )
            self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
