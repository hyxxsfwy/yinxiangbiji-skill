from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import zipfile


_SAFE_JOB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_EXPORT_SNAPSHOT_ARCHIVE_RE = re.compile(
    r"(?P<job_id>[0-9a-f]{16})-before[.]zip"
)
_EXPORT_SNAPSHOT_MANIFEST_RE = re.compile(
    r"(?P<job_id>[0-9a-f]{16})-before[.]sha256[.]json"
)


@dataclass(frozen=True)
class SnapshotResult:
    archive: Path
    manifest: Path
    archive_sha256: str
    archive_size: int
    members: tuple[dict, ...]
    reused: bool

    def to_dict(self):
        return {
            "archive": str(self.archive),
            "manifest": str(self.manifest),
            "archive_sha256": self.archive_sha256,
            "archive_size": self.archive_size,
            "member_count": len(self.members),
            "reused": self.reused,
        }


@dataclass(frozen=True)
class SnapshotCleanupResult:
    executed: bool
    kept_job_ids: tuple[str, ...]
    deleted: tuple[dict, ...]
    skipped: tuple[dict, ...]

    @property
    def deleted_files(self):
        return len(self.deleted)

    @property
    def deleted_bytes(self):
        return sum(int(item["size"]) for item in self.deleted)

    def to_dict(self):
        return {
            "executed": self.executed,
            "kept_job_ids": list(self.kept_job_ids),
            "deleted_files": self.deleted_files,
            "deleted_bytes": self.deleted_bytes,
            "deleted": list(self.deleted),
            "skipped": list(self.skipped),
        }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_within(path, root, description):
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(Path(root).resolve())
    except ValueError as exc:
        raise ValueError(f"{description}逃逸出 Vault: {path}") from exc
    return resolved


def _load_existing_snapshot(archive, manifest):
    if archive.exists() != manifest.exists():
        raise ValueError(
            f"快照不完整，ZIP 与清单必须同时存在: {archive}"
        )
    if not archive.exists():
        return None
    if not archive.is_file() or not manifest.is_file():
        raise ValueError(f"快照路径不是普通文件: {archive}")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        expected_hash = str(payload["archive_sha256"])
        expected_size = int(payload["archive_size"])
        members = tuple(payload["members"])
    except (
        KeyError,
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(f"快照清单无效: {manifest}") from exc
    actual_hash = _sha256(archive)
    actual_size = archive.stat().st_size
    if actual_hash != expected_hash or actual_size != expected_size:
        raise ValueError(f"快照 ZIP 哈希或大小不一致: {archive}")
    return SnapshotResult(
        archive=archive,
        manifest=manifest,
        archive_sha256=actual_hash,
        archive_size=actual_size,
        members=members,
        reused=True,
    )


def _collect_members(vault, domains):
    members = []
    seen_paths = set()
    for domain in domains:
        root = _require_within(
            vault / "30_精选资料" / domain,
            vault,
            "领域目录",
        )
        if not root.exists():
            continue
        if not root.is_dir():
            raise ValueError(f"领域路径不是目录: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            resolved = _require_within(path, vault, "快照成员")
            relative = resolved.relative_to(vault).as_posix()
            if relative in seen_paths:
                continue
            seen_paths.add(relative)
            members.append(
                {
                    "source": resolved,
                    "path": relative,
                    "size": resolved.stat().st_size,
                    "sha256": _sha256(resolved),
                }
            )
    return sorted(members, key=lambda item: item["path"])


def _write_deterministic_zip(path, members):
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for member in members:
            info = zipfile.ZipInfo(
                member["path"],
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with (
                member["source"].open("rb") as source,
                archive.open(info, "w") as target,
            ):
                shutil.copyfileobj(source, target, length=1024 * 1024)


def create_domain_snapshot(vault, domains, snapshot_dir, job_id):
    vault = Path(vault).expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"Vault 不存在: {vault}")
    if not isinstance(job_id, str) or not _SAFE_JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"job_id 无效: {job_id!r}")

    snapshot_dir = _require_within(snapshot_dir, vault, "快照目录")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    archive = snapshot_dir / f"{job_id}-before.zip"
    manifest = snapshot_dir / f"{job_id}-before.sha256.json"
    existing = _load_existing_snapshot(archive, manifest)
    if existing is not None:
        return existing

    members = _collect_members(vault, tuple(domains))
    temporary = snapshot_dir / f".{archive.name}.{uuid.uuid4().hex}.tmp"
    archive_created = False
    try:
        _write_deterministic_zip(temporary, members)
        archive_hash = _sha256(temporary)
        archive_size = temporary.stat().st_size
        try:
            os.link(temporary, archive)
        except FileExistsError as exc:
            raise ValueError(f"快照目标已并发出现，未覆盖: {archive}") from exc
        archive_created = True
        manifest_payload = {
            "archive_sha256": archive_hash,
            "archive_size": archive_size,
            "members": [
                {
                    "path": member["path"],
                    "size": member["size"],
                    "sha256": member["sha256"],
                }
                for member in members
            ],
        }
        try:
            with manifest.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    manifest_payload,
                    stream,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                stream.write("\n")
        except FileExistsError as exc:
            raise ValueError(
                f"快照清单已并发出现，未覆盖: {manifest}"
            ) from exc
    except BaseException:
        if archive_created:
            archive.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)

    return SnapshotResult(
        archive=archive,
        manifest=manifest,
        archive_sha256=archive_hash,
        archive_size=archive_size,
        members=tuple(manifest_payload["members"]),
        reused=False,
    )


def prune_export_snapshots(
    vault,
    snapshot_dir,
    current_job_id,
    retain_count=1,
):
    vault = Path(vault).expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"Vault 不存在: {vault}")
    if (
        not isinstance(current_job_id, str)
        or not re.fullmatch(r"[0-9a-f]{16}", current_job_id)
    ):
        raise ValueError(f"current_job_id 无效: {current_job_id!r}")
    if (
        isinstance(retain_count, bool)
        or not isinstance(retain_count, int)
        or retain_count < 1
    ):
        raise ValueError("retain_count 必须是大于或等于 1 的整数")

    snapshot_dir = _require_within(snapshot_dir, vault, "快照目录")
    if not snapshot_dir.is_dir():
        raise ValueError(f"快照目录不存在: {snapshot_dir}")

    current_archive = (
        snapshot_dir / f"{current_job_id}-before.zip"
    )
    current_manifest = (
        snapshot_dir / f"{current_job_id}-before.sha256.json"
    )
    if current_archive.is_symlink() or current_manifest.is_symlink():
        raise ValueError("当前快照不能是符号链接")
    _load_existing_snapshot(current_archive, current_manifest)

    entries = tuple(
        sorted(snapshot_dir.iterdir(), key=lambda path: path.name)
    )
    recognized_job_ids = set()
    for entry in entries:
        archive_match = _EXPORT_SNAPSHOT_ARCHIVE_RE.fullmatch(entry.name)
        manifest_match = _EXPORT_SNAPSHOT_MANIFEST_RE.fullmatch(entry.name)
        match = archive_match or manifest_match
        if match is not None:
            recognized_job_ids.add(match.group("job_id"))

    pairs = {}
    skipped = []
    handled_names = set()
    for job_id in sorted(recognized_job_ids):
        archive = snapshot_dir / f"{job_id}-before.zip"
        manifest = snapshot_dir / f"{job_id}-before.sha256.json"
        existing = tuple(
            path for path in (archive, manifest) if path.exists()
        )
        handled_names.update(path.name for path in existing)
        if (
            len(existing) != 2
            or any(path.is_symlink() for path in existing)
            or any(not path.is_file() for path in existing)
        ):
            for path in existing:
                skipped.append(
                    {
                        "path": path.name,
                        "reason": "incomplete_or_unsafe_pair",
                    }
                )
            continue
        pairs[job_id] = {
            "archive": archive,
            "manifest": manifest,
            "mtime_ns": max(
                archive.stat().st_mtime_ns,
                manifest.stat().st_mtime_ns,
            ),
        }

    for entry in entries:
        if entry.name in handled_names:
            continue
        skipped.append(
            {
                "path": entry.name,
                "reason": "unmanaged_snapshot",
            }
        )

    if current_job_id not in pairs:
        raise ValueError("当前快照不是完整的普通文件对")

    kept_job_ids = {current_job_id}
    historical = sorted(
        (
            (job_id, pair)
            for job_id, pair in pairs.items()
            if job_id != current_job_id
        ),
        key=lambda item: (item[1]["mtime_ns"], item[0]),
        reverse=True,
    )
    kept_job_ids.update(
        job_id
        for job_id, _pair in historical[: retain_count - 1]
    )

    deleted = []
    for job_id, pair in historical:
        if job_id in kept_job_ids:
            continue
        for path in (pair["archive"], pair["manifest"]):
            if path.parent.resolve() != snapshot_dir:
                raise ValueError(f"快照删除目标逃逸出快照目录: {path}")
            size = path.stat().st_size
            path.unlink()
            deleted.append({"path": path.name, "size": size})

    return SnapshotCleanupResult(
        executed=True,
        kept_job_ids=tuple(sorted(kept_job_ids)),
        deleted=tuple(deleted),
        skipped=tuple(skipped),
    )


def prune_legacy_export_snapshots(vault, snapshot_dir):
    """删除所有完整且校验通过的 16 位任务 ID 全量 ZIP 快照。"""
    vault = Path(vault).expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"Vault 不存在: {vault}")
    snapshot_dir = _require_within(snapshot_dir, vault, "快照目录")
    if not snapshot_dir.exists():
        return SnapshotCleanupResult(
            executed=True,
            kept_job_ids=(),
            deleted=(),
            skipped=(),
        )
    if not snapshot_dir.is_dir() or snapshot_dir.is_symlink():
        raise ValueError(f"快照目录不是安全的普通目录: {snapshot_dir}")

    entries = tuple(sorted(snapshot_dir.iterdir(), key=lambda path: path.name))
    job_ids = set()
    for entry in entries:
        match = (
            _EXPORT_SNAPSHOT_ARCHIVE_RE.fullmatch(entry.name)
            or _EXPORT_SNAPSHOT_MANIFEST_RE.fullmatch(entry.name)
        )
        if match:
            job_ids.add(match.group("job_id"))

    validated_pairs = []
    handled = set()
    skipped = []
    for job_id in sorted(job_ids):
        archive = snapshot_dir / f"{job_id}-before.zip"
        manifest = snapshot_dir / f"{job_id}-before.sha256.json"
        existing = tuple(path for path in (archive, manifest) if path.exists())
        handled.update(path.name for path in existing)
        if (
            len(existing) != 2
            or any(path.is_symlink() or not path.is_file() for path in existing)
        ):
            skipped.extend(
                {
                    "path": path.name,
                    "reason": "incomplete_or_unsafe_pair",
                }
                for path in existing
            )
            continue
        _load_existing_snapshot(archive, manifest)
        validated_pairs.append((archive, manifest))

    for entry in entries:
        if entry.name not in handled:
            skipped.append(
                {
                    "path": entry.name,
                    "reason": "unmanaged_snapshot",
                }
            )

    deleted = []
    for archive, manifest in validated_pairs:
        for path in (archive, manifest):
            if path.parent.resolve() != snapshot_dir:
                raise ValueError(f"快照删除目标逃逸出快照目录: {path}")
            size = path.stat().st_size
            path.unlink()
            deleted.append({"path": path.name, "size": size})

    return SnapshotCleanupResult(
        executed=True,
        kept_job_ids=(),
        deleted=tuple(deleted),
        skipped=tuple(skipped),
    )
