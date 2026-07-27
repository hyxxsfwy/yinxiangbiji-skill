from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


CONFIRMATION = "MIGRATE_OBSIDIAN_VAULT"
DOMAINS = ("AI", "Quant", "软件工程", "投资理财", "个人成长")
OLD_DIRECTORIES = ("AI相关知识库", "Quant相关知识库", "HYXX个人知识库")
QUANT_FILENAME = "GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
CODEX_FILENAME = "Codex CLI 使用技巧记录.md"


@dataclass(frozen=True)
class MigrationItem:
    source: Path
    destination: Path
    operation: str


@dataclass(frozen=True)
class MigrationPlan:
    vault: Path
    items: tuple[MigrationItem, ...]
    old_directories: tuple[Path, ...]


def assert_vault(vault: Path) -> Path:
    resolved = Path(vault).resolve()
    if not (resolved / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault，缺少 .obsidian: {resolved}")
    return resolved


def build_migration_plan(vault: Path) -> MigrationPlan:
    vault = assert_vault(vault)
    items = (
        MigrationItem(
            vault / "AI相关知识库",
            vault / "30_精选资料" / "AI",
            "copy_tree",
        ),
        MigrationItem(
            vault / "Quant相关知识库" / QUANT_FILENAME,
            vault / "30_精选资料" / "Quant" / "2026年06月" / QUANT_FILENAME,
            "copy_file",
        ),
        MigrationItem(
            vault / "HYXX个人知识库" / CODEX_FILENAME,
            vault / "20_知识笔记" / "软件工程" / CODEX_FILENAME,
            "copy_file",
        ),
    )
    missing = [str(item.source) for item in items if not item.source.exists()]
    if missing:
        raise FileNotFoundError("缺少迁移源:\n" + "\n".join(missing))
    return MigrationPlan(
        vault=vault,
        items=items,
        old_directories=tuple(vault / name for name in OLD_DIRECTORIES),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_old_files(plan: MigrationPlan):
    for old_directory in plan.old_directories:
        for path in sorted(old_directory.rglob("*")):
            if path.is_file():
                yield path


def destination_for_source(plan: MigrationPlan, source: Path) -> Path | None:
    relative = source.relative_to(plan.vault)
    parts = relative.parts
    if parts[0] == "AI相关知识库":
        return plan.vault / "30_精选资料" / "AI" / Path(*parts[1:])
    if relative.as_posix() == (
        "Quant相关知识库/GPT-6也救不了平庸策略：Vibe Quant 的反思.md"
    ):
        return plan.vault / "30_精选资料" / "Quant" / "2026年06月" / QUANT_FILENAME
    if relative.as_posix() == "HYXX个人知识库/Codex CLI 使用技巧记录.md":
        return plan.vault / "20_知识笔记" / "软件工程" / CODEX_FILENAME
    return None


def create_backup(plan: MigrationPlan, backup_path: Path) -> Path:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        raise FileExistsError(f"备份已存在，拒绝覆盖: {backup_path}")
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for old_directory in plan.old_directories:
            for path in sorted(old_directory.rglob("*")):
                relative = path.relative_to(plan.vault).as_posix()
                if path.is_dir():
                    archive.writestr(relative.rstrip("/") + "/", b"")
                else:
                    archive.write(path, relative)
    return backup_path


def write_manifest(plan: MigrationPlan, manifest_path: Path) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "vault": str(plan.vault),
        "created_at": datetime.now().astimezone().isoformat(),
        "files": [
            {
                "source": path.relative_to(plan.vault).as_posix(),
                "destination": (
                    destination.relative_to(plan.vault).as_posix()
                    if (destination := destination_for_source(plan, path)) is not None
                    else None
                ),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "preserve_hash": path.suffix.lower() != ".md",
            }
            for path in iter_old_files(plan)
        ],
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def print_plan(plan: MigrationPlan):
    print("预览模式：不会修改 vault")
    for item in plan.items:
        print(
            f"- {item.source.relative_to(plan.vault)}"
            f" -> {item.destination.relative_to(plan.vault)}"
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="安全重组 HYXX Obsidian LLM Wiki")
    parser.add_argument("--vault", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    plan = build_migration_plan(args.vault)
    sys.stdout.reconfigure(encoding="utf-8")
    print_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
