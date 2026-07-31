#!/usr/bin/env python3
"""关键词导出的增量事务快照与显式恢复。"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys


ROLLBACK_CONFIRMATION = "ROLLBACK_KEYWORD_EXPORT"
MANIFEST_VERSION = 1


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@dataclass(frozen=True)
class TransactionSummary:
    job_id: str
    state: str
    changed_paths: int
    object_count: int
    stored_bytes: int
    sqlite_backup: str | None


class VaultMutationJournal:
    """仅保存被实际改动路径的原始内容。"""

    def __init__(self, vault, state_root, transaction_dir, manifest):
        self.vault = Path(vault).resolve()
        self.state_root = Path(state_root).resolve()
        self.transaction_dir = Path(transaction_dir)
        self.manifest_path = self.transaction_dir / "manifest.json"
        self.objects_dir = self.transaction_dir / "objects"
        self.manifest = manifest

    @classmethod
    def begin(
        cls,
        vault,
        state_root,
        job_id,
        selection_hash,
        catalog_path,
        baseline_git_head=None,
    ):
        vault = Path(vault).resolve()
        state_root = Path(state_root).resolve()
        if not vault.is_dir():
            vault.mkdir(parents=True, exist_ok=True)
        try:
            state_root.relative_to(vault)
        except ValueError as error:
            raise ValueError("事务状态目录必须位于 Vault 内") from error

        transaction_dir = state_root / "transactions" / str(job_id)
        manifest_path = transaction_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("version") != MANIFEST_VERSION
                or manifest.get("job_id") != str(job_id)
                or manifest.get("selection_hash") != selection_hash
                or Path(manifest.get("vault", "")).resolve() != vault
            ):
                raise ValueError("现有事务清单与当前任务不一致")
            return cls(vault, state_root, transaction_dir, manifest)

        transaction_dir.mkdir(parents=True, exist_ok=False)
        objects_dir = transaction_dir / "objects"
        objects_dir.mkdir()
        catalog_path = Path(catalog_path).resolve()
        catalog_existed = catalog_path.is_file()
        sqlite_backup = None
        sqlite_backup_sha256 = None
        if catalog_existed:
            sqlite_backup_path = transaction_dir / "export-catalog.sqlite3.before"
            source = sqlite3.connect(f"file:{catalog_path.as_posix()}?mode=ro", uri=True)
            destination = sqlite3.connect(sqlite_backup_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            sqlite_backup = sqlite_backup_path.name
            sqlite_backup_sha256 = _sha256(sqlite_backup_path)

        manifest = {
            "version": MANIFEST_VERSION,
            "job_id": str(job_id),
            "selection_hash": selection_hash,
            "vault": str(vault),
            "state": "prepared",
            "baseline_git_head": baseline_git_head,
            "catalog": {
                "path": cls._relative_static(vault, catalog_path),
                "existed": catalog_existed,
                "backup": sqlite_backup,
                "backup_sha256": sqlite_backup_sha256,
            },
            "entries": {},
            "order": [],
            "git_commit": None,
        }
        instance = cls(vault, state_root, transaction_dir, manifest)
        instance._save()
        return instance

    @staticmethod
    def _relative_static(vault, path):
        try:
            return Path(path).resolve().relative_to(Path(vault).resolve()).as_posix()
        except ValueError as error:
            raise ValueError(f"路径不在 Vault 内: {path}") from error

    def _relative(self, path):
        path = Path(path)
        if path.is_symlink():
            raise ValueError(f"事务不允许符号链接路径: {path}")
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.vault)
        except ValueError as error:
            raise ValueError(f"路径不在 Vault 内: {path}") from error
        current = self.vault
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink():
                raise ValueError(f"事务不允许符号链接父目录: {current}")
        return relative.as_posix()

    def _save(self):
        _atomic_json(self.manifest_path, self.manifest)

    def _snapshot_before(self, path):
        relative = self._relative(path)
        if relative in self.manifest["entries"]:
            return relative
        path = self.vault / relative
        existed = path.is_file()
        before_hash = None
        size = 0
        if existed:
            before_hash = _sha256(path)
            size = path.stat().st_size
            object_path = self.objects_dir / before_hash
            if not object_path.exists():
                temporary = object_path.with_suffix(".tmp")
                shutil.copyfile(path, temporary)
                os.replace(temporary, object_path)
        elif path.exists():
            raise ValueError(f"事务仅支持文件路径: {path}")
        self.manifest["entries"][relative] = {
            "before_exists": existed,
            "before_sha256": before_hash,
            "before_size": size,
            "after_exists": None,
            "after_sha256": None,
            "after_size": None,
        }
        if self.manifest["state"] == "prepared":
            self.manifest["state"] = "in_progress"
        self._save()
        return relative

    def _record_after(self, path):
        relative = self._relative(path)
        if relative not in self.manifest["entries"]:
            raise ValueError(f"路径尚未准备事务前像: {relative}")
        path = self.vault / relative
        if path.is_file():
            after_exists = True
            after_hash = _sha256(path)
            after_size = path.stat().st_size
        elif path.exists():
            raise ValueError(f"事务仅支持文件路径: {path}")
        else:
            after_exists = False
            after_hash = None
            after_size = 0
        entry = self.manifest["entries"][relative]
        entry.update(
            {
                "after_exists": after_exists,
                "after_sha256": after_hash,
                "after_size": after_size,
            }
        )
        if relative not in self.manifest["order"]:
            self.manifest["order"].append(relative)
        self._save()

    def prepare_write(self, path):
        return self._snapshot_before(path)

    def record_write(self, path):
        self._record_after(path)

    def prepare_delete(self, path):
        return self._snapshot_before(path)

    def record_delete(self, path):
        self._record_after(path)

    def prepare_move(self, source, destination):
        self._snapshot_before(source)
        self._snapshot_before(destination)

    def record_move(self, source, destination):
        self._record_after(source)
        self._record_after(destination)

    def changed_paths(self):
        changed = []
        for relative, entry in self.manifest["entries"].items():
            before = (entry["before_exists"], entry["before_sha256"])
            after = (entry["after_exists"], entry["after_sha256"])
            if entry["after_exists"] is not None and before != after:
                changed.append(relative)
        return tuple(sorted(changed))

    def _summary(self):
        objects = list(self.objects_dir.iterdir()) if self.objects_dir.exists() else []
        objects = [path for path in objects if path.is_file() and not path.name.endswith(".tmp")]
        backup_name = self.manifest["catalog"].get("backup")
        backup = str(self.transaction_dir / backup_name) if backup_name else None
        return TransactionSummary(
            job_id=self.manifest["job_id"],
            state=self.manifest["state"],
            changed_paths=len(self.changed_paths()),
            object_count=len(objects),
            stored_bytes=sum(path.stat().st_size for path in objects),
            sqlite_backup=backup,
        )

    def seal(self):
        pending = [
            relative
            for relative, entry in self.manifest["entries"].items()
            if entry["after_exists"] is None
        ]
        if pending:
            raise ValueError(f"事务仍有未记录的路径: {pending}")
        self._save()
        return self._summary()

    def mark_committed(self, git_commit=None):
        self.manifest["state"] = "committed"
        self.manifest["git_commit"] = git_commit
        self._save()
        return self._summary()

    def restore(self, confirm):
        if confirm != ROLLBACK_CONFIRMATION:
            raise ValueError(f"恢复确认词必须是 {ROLLBACK_CONFIRMATION}")
        lock = self.state_root / "active-run.lock"
        if lock.exists():
            raise RuntimeError(f"存在活动任务锁，拒绝恢复: {lock}")

        for relative in reversed(self.manifest["order"]):
            entry = self.manifest["entries"][relative]
            path = self.vault / relative
            if entry["after_exists"]:
                if not path.is_file() or _sha256(path) != entry["after_sha256"]:
                    raise RuntimeError(f"事务后内容已变化，拒绝覆盖: {relative}")
            elif path.exists():
                raise RuntimeError(f"事务后路径状态已变化，拒绝覆盖: {relative}")

        for relative in reversed(self.manifest["order"]):
            entry = self.manifest["entries"][relative]
            path = self.vault / relative
            if entry["before_exists"]:
                object_path = self.objects_dir / entry["before_sha256"]
                if not object_path.is_file() or _sha256(object_path) != object_path.name:
                    raise RuntimeError(f"事务前像损坏: {relative}")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix + ".rollback")
                shutil.copyfile(object_path, temporary)
                os.replace(temporary, path)
            elif path.exists():
                path.unlink()

        catalog = self.manifest["catalog"]
        catalog_path = self.vault / catalog["path"]
        if catalog["existed"]:
            backup = self.transaction_dir / catalog["backup"]
            if _sha256(backup) != catalog["backup_sha256"]:
                raise RuntimeError("SQLite 事务前像损坏")
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = catalog_path.with_suffix(catalog_path.suffix + ".rollback")
            shutil.copyfile(backup, temporary)
            os.replace(temporary, catalog_path)
        elif catalog_path.exists():
            catalog_path.unlink()

        self.manifest["state"] = "rolled_back"
        self._save()
        return self._summary()

    def to_dict(self):
        return asdict(self._summary())


def prune_committed_transactions(
    vault,
    state_root,
    current_job_id,
    retain_count=1,
):
    """保留当前事务及最近若干已提交事务；永不删除未完成事务。"""
    del vault
    transactions = Path(state_root) / "transactions"
    if not transactions.is_dir():
        return []
    committed = []
    for directory in transactions.iterdir():
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("state") == "committed":
            committed.append(directory)
    committed.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    keep = {str(current_job_id)}
    keep.update(path.name for path in committed[: max(0, retain_count)])
    removed = []
    for directory in committed:
        if directory.name not in keep:
            shutil.rmtree(directory)
            removed.append(str(directory))
    return removed


def _load_existing(vault, state_root, job_id):
    transaction_dir = Path(state_root) / "transactions" / str(job_id)
    manifest_path = transaction_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"事务不存在: {job_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return VaultMutationJournal(vault, state_root, transaction_dir, manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "restore"))
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    from scripts.runtime import load_vault_root

    vault = load_vault_root()
    state_root = vault / ".state" / "yinxiang-notes"
    journal = _load_existing(vault, state_root, args.job_id)
    if args.command == "restore":
        summary = journal.restore(args.confirm)
    else:
        summary = journal._summary()
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
