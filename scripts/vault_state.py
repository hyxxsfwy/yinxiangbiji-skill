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

if os.name == "nt":
    import msvcrt
else:
    import fcntl


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


def require_path_within_vault(
    path,
    vault,
    description,
    *,
    allowed_root=None,
):
    """解析路径并拒绝任何通过既存链接逃逸 Vault 的目标。"""
    resolved_vault = Path(vault).expanduser().resolve()
    candidate = Path(path).expanduser()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_vault)
    except ValueError as exc:
        raise ValueError(
            f"{description}解析后必须位于 Vault 内: {resolved_vault}"
        ) from exc

    if allowed_root is not None:
        resolved_allowed_root = Path(allowed_root).expanduser().resolve()
        try:
            resolved_allowed_root.relative_to(resolved_vault)
            resolved_candidate.relative_to(resolved_allowed_root)
        except ValueError as exc:
            raise ValueError(
                f"{description}必须位于允许目录: {resolved_allowed_root}"
            ) from exc

    absolute_candidate = (
        candidate
        if candidate.is_absolute()
        else (Path.cwd() / candidate)
    )
    for ancestor in (absolute_candidate, *absolute_candidate.parents):
        if ancestor == resolved_vault:
            break
        if ancestor.exists() or ancestor.is_symlink():
            resolved_ancestor = ancestor.resolve()
            try:
                resolved_ancestor.relative_to(resolved_vault)
            except ValueError as exc:
                raise ValueError(
                    f"{description}的既存祖先解析后逃逸 Vault: {ancestor}"
                ) from exc
    return resolved_candidate


@dataclass(frozen=True)
class VaultStatePaths:
    vault: Path
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
        resolved_vault = Path(vault).expanduser().resolve()
        root = require_path_within_vault(
            resolved_vault / ".state" / "yinxiang-notes",
            resolved_vault,
            "Vault 状态目录",
        )
        return cls(
            vault=resolved_vault,
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
        and relative_source.name.startswith("multi-export-")
        and relative_source.suffix == ".json"
    ):
        return paths.runs / relative_source.name
    if (
        relative_source.parent == Path(".")
        and relative_source.name.startswith("export-")
        and relative_source.suffix == ".json"
    ):
        return paths.single_domain / relative_source.name
    return paths.root / relative_source


def _rollback_published(paths, published):
    if not published:
        return
    paths.migrations.mkdir(parents=True, exist_ok=True)
    quarantine_root = paths.migrations / (
        f"rollback-quarantine-{uuid.uuid4().hex}"
    )
    quarantine_root.mkdir()
    preserved = []
    failures = []
    for index, (staged, target) in enumerate(reversed(published)):
        quarantine = quarantine_root / f"{index:06d}-{target.name}"
        try:
            os.replace(target, quarantine)
        except FileNotFoundError:
            continue
        except OSError as exc:
            failures.append(f"{target}: {exc}")
            continue

        try:
            owned_by_batch = os.path.samefile(staged, quarantine)
        except OSError as exc:
            preserved.append(quarantine)
            failures.append(f"{quarantine}: 无法确认归属 ({exc})")
            continue

        if owned_by_batch:
            quarantine.unlink()
            continue

        try:
            os.link(quarantine, target)
        except FileExistsError:
            preserved.append(quarantine)
            failures.append(
                f"{target}: 恢复时已被占用，原文件保留在 {quarantine}"
            )
        except OSError as exc:
            preserved.append(quarantine)
            failures.append(
                f"{target}: 恢复失败，原文件保留在 {quarantine} ({exc})"
            )
        else:
            quarantine.unlink()

    if not preserved:
        quarantine_root.rmdir()
    if failures:
        raise StateMigrationConflict(
            "迁移回滚未能完全恢复并发文件: " + "; ".join(failures)
        )


def _publish_staged(paths, staged_items):
    published = []
    try:
        for staged, target, entry in staged_items:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(staged, target)
            except FileExistsError as exc:
                raise StateMigrationConflict(
                    f"迁移发布时目标被并发占用: {target}"
                ) from exc
            published.append((staged, target))
    except BaseException:
        _rollback_published(paths, published)
        raise
    return tuple(entry for _staged, _target, entry in staged_items)


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
    paths.root.mkdir(parents=True, exist_ok=True)
    state_root = paths.root.resolve()
    staging = paths.root / f".migration-staging-{uuid.uuid4().hex}"
    staging.mkdir()
    staged_items = []
    skipped = []
    published = []
    try:
        for index, source in enumerate(_legacy_sources(legacy_root)):
            resolved_source = _require_within(
                source,
                legacy_root,
                "迁移源",
            )
            if not resolved_source.is_file():
                continue
            relative_source = source.relative_to(legacy_root)
            target = _target_for(paths, relative_source)
            _require_within(target, state_root, "迁移目标")
            staged = staging / f"{index:06d}-{uuid.uuid4().hex}"
            shutil.copyfile(resolved_source, staged)
            entry = MigrationEntry(
                source=relative_source.as_posix(),
                target=target.relative_to(paths.root).as_posix(),
                size=staged.stat().st_size,
                sha256=_sha256(staged),
            )
            if target.exists():
                if not target.is_file() or _sha256(target) != entry.sha256:
                    raise StateMigrationConflict(
                        f"迁移目标与旧状态内容冲突: {target}"
                    )
                skipped.append(entry)
            else:
                staged_items.append((staged, target, entry))

        try:
            copied = _publish_staged(paths, staged_items)
            published = [
                (staged, target)
                for staged, target, _entry in staged_items
            ]
            manifest = _write_manifest(paths, copied) if copied else None
        except BaseException:
            _rollback_published(paths, published)
            raise
        return MigrationReport(
            copied=tuple(copied),
            skipped=tuple(skipped),
            manifest=manifest,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


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
    created_stat = os.fstat(file_descriptor)
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
        try:
            current_stat = lock.stat()
            if (
                current_stat.st_dev == created_stat.st_dev
                and current_stat.st_ino == created_stat.st_ino
            ):
                lock.unlink()
        except FileNotFoundError:
            pass
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


def _operation_guard_path(paths):
    return paths.lock.with_name(f"{paths.lock.name}.guard")


def _acquire_operation_mutex(mutex_file, guard):
    if os.fstat(mutex_file.fileno()).st_size == 0:
        mutex_file.write(b"\0")
        os.fsync(mutex_file.fileno())
    mutex_file.seek(0)
    try:
        if os.name == "nt":
            msvcrt.locking(
                mutex_file.fileno(),
                msvcrt.LK_NBLCK,
                1,
            )
        else:
            fcntl.flock(
                mutex_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise
        raise StateLockConflict(
            f"Vault 锁操作正在本机其他进程中执行: {guard}"
        ) from exc


@contextmanager
def _lock_operation_guard(paths, operation, recover_stale=False):
    del recover_stale
    guard = _operation_guard_path(paths)
    guard.parent.mkdir(parents=True, exist_ok=True)
    mutex_file = guard.open("a+b", buffering=0)
    try:
        _acquire_operation_mutex(mutex_file, guard)
        yield
    finally:
        mutex_file.close()


def _acquire_runtime_lock(paths, payload, recover_stale):
    try:
        _create_lock(paths.lock, payload)
        return
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
    with _lock_operation_guard(
        paths,
        "runtime",
        recover_stale=recover_stale,
    ):
        _acquire_runtime_lock(paths, payload, recover_stale)
        try:
            yield payload
        finally:
            _remove_owned_lock(paths.lock, lock_id)
