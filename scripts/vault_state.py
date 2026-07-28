#!/usr/bin/env python3
"""管理跟随 Obsidian Vault 同步的运行状态。"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import uuid


LEGACY_PATTERNS = (
    "export-catalog.sqlite3",
    "export-*.json",
    "multi-export-*.json",
    "jobs/*.json",
    "reports/*.json",
)


class StateMigrationConflict(RuntimeError):
    """旧状态无法安全迁移。"""


class StateLockConflict(RuntimeError):
    """Vault 写锁已被占用或无法安全恢复。"""


@dataclass(frozen=True)
class VaultStatePaths:
    root: Path
    catalog: Path
    jobs: Path
    runs: Path
    reports: Path
    single_domain: Path
    migrations: Path
    lock: Path

    @classmethod
    def for_vault(cls, vault):
        root = Path(vault).resolve() / ".state" / "yinxiang-notes"
        return cls(
            root=root,
            catalog=root / "export-catalog.sqlite3",
            jobs=root / "jobs",
            runs=root / "runs",
            reports=root / "reports",
            single_domain=root / "single-domain",
            migrations=root / "migrations",
            lock=root / "active-run.lock",
        )


@dataclass(frozen=True)
class MigrationEntry:
    source: str
    target: str
    size: int
    sha256: str


@dataclass(frozen=True)
class MigrationReport:
    copied: tuple[MigrationEntry, ...]
    skipped: tuple[MigrationEntry, ...]
    manifest: Path | None


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_within(path, root, description):
    resolved_root = Path(root).resolve()
    resolved_path = Path(path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise StateMigrationConflict(
            f"{description}逃逸允许目录: {path}"
        ) from exc
    return resolved_path


def _legacy_sources(legacy_root):
    sources = set()
    for pattern in LEGACY_PATTERNS:
        sources.update(legacy_root.glob(pattern))
    return sorted(sources, key=lambda path: path.as_posix())


def _target_for(paths, relative_source):
    if (
        relative_source.parent == Path(".")
        and relative_source.name.startswith("export-")
        and relative_source.suffix == ".json"
    ):
        return paths.single_domain / relative_source.name
    return paths.root / relative_source


def _atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        if target.exists():
            raise StateMigrationConflict(f"迁移目标已被占用: {target}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _write_manifest(paths, copied):
    paths.migrations.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    manifest = paths.migrations / (
        f"migration-{timestamp}-{uuid.uuid4().hex}.json"
    )
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "copied": [asdict(entry) for entry in copied],
    }
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest.name}.",
        suffix=".tmp",
        dir=paths.migrations,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, manifest)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def migrate_legacy_state(paths, legacy_root):
    """将允许的旧状态文件复制到 Vault 状态目录，绝不覆盖冲突目标。"""
    legacy_root = Path(legacy_root).resolve()
    state_root = paths.root.resolve()
    pending = []
    skipped = []

    for source in _legacy_sources(legacy_root):
        resolved_source = _require_within(source, legacy_root, "迁移源")
        if not resolved_source.is_file():
            continue
        relative_source = source.relative_to(legacy_root)
        target = _target_for(paths, relative_source)
        _require_within(target, state_root, "迁移目标")
        entry = MigrationEntry(
            source=relative_source.as_posix(),
            target=target.relative_to(paths.root).as_posix(),
            size=resolved_source.stat().st_size,
            sha256=_sha256(resolved_source),
        )
        if target.exists():
            if not target.is_file() or _sha256(target) != entry.sha256:
                raise StateMigrationConflict(
                    f"迁移目标与旧状态内容冲突: {target}"
                )
            skipped.append(entry)
        else:
            pending.append((resolved_source, target, entry))

    copied = []
    for source, target, entry in pending:
        _atomic_copy(source, target)
        copied.append(entry)

    manifest = _write_manifest(paths, copied) if copied else None
    return MigrationReport(
        copied=tuple(copied),
        skipped=tuple(skipped),
        manifest=manifest,
    )


def _read_lock_payload(lock):
    try:
        return json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _local_lock_is_live(payload):
    if not isinstance(payload, dict):
        return None
    if payload.get("device") != socket.gethostname():
        return None
    pid = payload.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH or getattr(exc, "winerror", None) == 87:
            return False
        return None
    return True


def _create_lock(lock, payload):
    lock.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    file_descriptor = os.open(lock, flags, 0o600)
    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as lock_file:
            json.dump(payload, lock_file, ensure_ascii=False)
            lock_file.write("\n")
            lock_file.flush()
            os.fsync(lock_file.fileno())
    except BaseException:
        lock.unlink(missing_ok=True)
        raise


def _archive_stale_lock(paths):
    paths.migrations.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    audit = paths.migrations / (
        f"stale-lock-{timestamp}-{uuid.uuid4().hex}.json"
    )
    try:
        os.replace(paths.lock, audit)
    except FileNotFoundError:
        return None
    return audit


def _remove_owned_lock(lock, lock_id):
    payload = _read_lock_payload(lock)
    if isinstance(payload, dict) and payload.get("lock_id") == lock_id:
        lock.unlink(missing_ok=True)


@contextmanager
def runtime_write_lock(paths, task_id, recover_stale=False):
    """独占持有 Vault 写锁，并仅清理当前上下文拥有的锁。"""
    lock_id = uuid.uuid4().hex
    payload = {
        "device": socket.gethostname(),
        "pid": os.getpid(),
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lock_id": lock_id,
    }
    try:
        _create_lock(paths.lock, payload)
    except FileExistsError as exc:
        existing = _read_lock_payload(paths.lock)
        if _local_lock_is_live(existing) is True:
            raise StateLockConflict(
                f"Vault 写锁仍由本机存活进程持有: {paths.lock}"
            ) from exc
        if not recover_stale:
            raise StateLockConflict(
                f"Vault 写锁存在且无法确认已失效: {paths.lock}"
            ) from exc
        _archive_stale_lock(paths)
        try:
            _create_lock(paths.lock, payload)
        except FileExistsError as rebuild_exc:
            raise StateLockConflict(
                f"恢复旧锁时 Vault 写锁被其他进程取得: {paths.lock}"
            ) from rebuild_exc

    try:
        yield payload
    finally:
        _remove_owned_lock(paths.lock, lock_id)
