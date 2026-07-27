"""逐篇整理 Obsidian 精选资料并维护受控双向链接。"""

from __future__ import annotations

import argparse
import json
import re
import hashlib
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

try:
    from scripts.knowledge_base import write_knowledge_base_index
    from scripts.restructure_obsidian_vault import iter_markdown_references
except ModuleNotFoundError:
    from knowledge_base import write_knowledge_base_index
    from restructure_obsidian_vault import iter_markdown_references


INDEX_FILENAME = "目录索引.md"
REVIEW_FIELDS = {"path", "decision", "reason", "topic", "links"}
VALID_DECISIONS = {"keep", "trash"}
AUTO_LINKS_START = "<!-- llmwiki:auto-links:start -->"
AUTO_LINKS_END = "<!-- llmwiki:auto-links:end -->"
AUTO_LINKS_SECTION = re.compile(
    r"(?:\r?\n)?## 相关笔记\r?\n\r?\n"
    + re.escape(AUTO_LINKS_START)
    + r"\r?\n.*?"
    + re.escape(AUTO_LINKS_END)
    + r"\r?\n?",
    re.DOTALL,
)
AUTO_LINK_TARGET = re.compile(
    r"\[\[(30_精选资料/[^\]|]+)(?:\|[^\]]+)?\]\]"
)
SNAPSHOT_BASENAME = "2026-07-27-精选资料整理前"
AUDIT_LOG_NAME = "2026-07-27-精选资料逐篇审阅.md"
EXTERNAL_SCHEMES = ("http:", "https:", "mailto:", "data:")


@dataclass(frozen=True)
class ReviewItem:
    path: PurePosixPath
    decision: str
    reason: str
    topic: str
    links: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class MoveItem:
    source: Path
    destination: Path


@dataclass(frozen=True)
class AssetCopy:
    source: Path
    destination: Path


@dataclass(frozen=True)
class MarkdownUpdate:
    path: Path
    expected: str


@dataclass(frozen=True)
class CurationPlan:
    vault: Path
    reviews: tuple[ReviewItem, ...]
    moves: tuple[MoveItem, ...]
    assets: tuple[AssetCopy, ...]
    updates: tuple[MarkdownUpdate, ...]
    snapshot_sources: tuple[Path, ...]
    snapshot_zip: Path
    snapshot_manifest: Path
    audit_log: Path


def _safe_review_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}必须是非空字符串")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower() != ".md"
    ):
        raise ValueError(f"{label}不是安全的 Markdown 相对路径: {value}")
    return path


def load_review_manifest(path: Path) -> tuple[ReviewItem, ...]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"审阅清单无法读取: {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("审阅清单根节点必须是数组")

    reviews = []
    for index, record in enumerate(payload):
        if not isinstance(record, dict) or set(record) != REVIEW_FIELDS:
            raise ValueError(
                f"审阅清单第 {index + 1} 项字段必须精确为: "
                + ", ".join(sorted(REVIEW_FIELDS))
            )
        links = record["links"]
        if not isinstance(links, list):
            raise ValueError(f"审阅清单第 {index + 1} 项 links 必须是数组")
        reviews.append(
            ReviewItem(
                path=_safe_review_path(record["path"], "path"),
                decision=str(record["decision"]),
                reason=str(record["reason"]).strip(),
                topic=str(record["topic"]).strip(),
                links=tuple(
                    _safe_review_path(value, "links")
                    for value in links
                ),
            )
        )
    return tuple(reviews)


def discover_documents(vault: Path) -> tuple[Path, ...]:
    root = Path(vault).resolve() / "30_精选资料"
    return tuple(
        path
        for path in sorted(root.rglob("*.md"))
        if path.is_file() and path.name != INDEX_FILENAME
    )


def validate_review_manifest(
    vault: Path,
    reviews: tuple[ReviewItem, ...],
) -> tuple[str, ...]:
    vault = Path(vault).resolve()
    root = vault / "30_精选资料"
    issues = []
    counts = {}
    for review in reviews:
        key = review.path.as_posix()
        counts[key] = counts.get(key, 0) + 1
    issues.extend(
        f"审阅清单路径重复: {path}"
        for path, count in sorted(counts.items())
        if count > 1
    )

    actual_paths = {
        path.relative_to(root).as_posix()
        for path in discover_documents(vault)
    }
    review_paths = set(counts)
    issues.extend(
        f"审阅清单缺少: {path}"
        for path in sorted(actual_paths - review_paths)
    )
    issues.extend(
        f"审阅清单路径不存在: {path}"
        for path in sorted(review_paths - actual_paths)
    )

    review_by_path = {}
    for review in reviews:
        path = review.path.as_posix()
        review_by_path.setdefault(path, review)
        if review.decision not in VALID_DECISIONS:
            issues.append(f"decision 无效: {path}: {review.decision}")
        if not review.reason:
            issues.append(f"reason 为空: {path}")
        if not review.topic:
            issues.append(f"topic 为空: {path}")
        if len(review.links) > 3:
            issues.append(f"自动链接超过 3 条: {path}: {len(review.links)}")
        if len(set(review.links)) != len(review.links):
            issues.append(f"自动链接重复: {path}")
        if review.decision == "trash" and review.links:
            issues.append(f"待移入废纸篓文档不能建立自动链接: {path}")

    for review in reviews:
        source = review.path.as_posix()
        for target_path in review.links:
            target = target_path.as_posix()
            target_review = review_by_path.get(target)
            if target_review is None:
                issues.append(f"自动链接目标不在审阅清单: {source} -> {target}")
                continue
            if target_review.decision != "keep":
                issues.append(f"自动链接指向非保留文档: {source} -> {target}")
            if review.path not in target_review.links:
                issues.append(f"自动链接不是双向: {source} -> {target}")
    return tuple(dict.fromkeys(issues))


def render_auto_links(
    markdown: str,
    links: tuple[ReviewItem, ...],
) -> str:
    base = AUTO_LINKS_SECTION.sub("", markdown)
    if not links:
        return base
    link_lines = []
    for review in sorted(links, key=lambda item: item.path.as_posix()):
        target = PurePosixPath("30_精选资料", *review.path.parts)
        alias = review.path.stem.replace("|", "｜").replace("]", "］")
        link_lines.append(f"- [[{target.as_posix()}|{alias}]]")
    section = "\n".join(
        (
            "## 相关笔记",
            "",
            AUTO_LINKS_START,
            *link_lines,
            AUTO_LINKS_END,
            "",
        )
    )
    separator = "\n" if base.endswith(("\n", "\r")) else "\n\n"
    return base + separator + section


def extract_auto_link_targets(markdown: str) -> tuple[str, ...]:
    match = AUTO_LINKS_SECTION.search(markdown)
    if match is None:
        return ()
    return tuple(
        target.group(1)
        for target in AUTO_LINK_TARGET.finditer(match.group(0))
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _trash_destination(vault: Path, relative: PurePosixPath) -> Path:
    return (
        vault
        / "99_废纸篓"
        / "30_精选资料"
        / Path(*relative.parts)
    )


def _local_assets_for_move(
    vault: Path,
    source: Path,
    destination: Path,
) -> tuple[AssetCopy, ...]:
    assets = []
    markdown = source.read_text(encoding="utf-8")
    for reference in iter_markdown_references(markdown):
        if reference.is_wikilink:
            continue
        target_text = unquote(reference.target).split("#", 1)[0].strip()
        if (
            not target_text
            or target_text.lower().startswith(EXTERNAL_SCHEMES)
        ):
            continue
        source_asset = (source.parent / target_text).resolve()
        if (
            not _inside(vault, source_asset)
            or not source_asset.is_file()
            or source_asset.suffix.lower() == ".md"
        ):
            continue
        destination_asset = (destination.parent / target_text).resolve()
        trash_root = (vault / "99_废纸篓").resolve()
        if not _inside(trash_root, destination_asset):
            raise ValueError(
                f"废纸篓附件目标越界: {source.relative_to(vault)}: "
                f"{reference.target}"
            )
        assets.append(
            AssetCopy(
                source=source_asset,
                destination=destination_asset,
            )
        )
    unique = {
        (item.source, item.destination): item
        for item in assets
    }
    return tuple(
        unique[key]
        for key in sorted(
            unique,
            key=lambda pair: (str(pair[0]), str(pair[1])),
        )
    )


def _local_assets_for_completed_move(
    vault: Path,
    source: Path,
    destination: Path,
) -> tuple[AssetCopy, ...]:
    if not destination.is_file():
        return ()
    assets = []
    markdown = destination.read_text(encoding="utf-8")
    for reference in iter_markdown_references(markdown):
        if reference.is_wikilink:
            continue
        target_text = unquote(reference.target).split("#", 1)[0].strip()
        if (
            not target_text
            or target_text.lower().startswith(EXTERNAL_SCHEMES)
        ):
            continue
        source_asset = (source.parent / target_text).resolve()
        destination_asset = (destination.parent / target_text).resolve()
        if (
            source_asset.suffix.lower() == ".md"
            or not _inside(vault, source_asset)
            or not _inside(vault, destination_asset)
        ):
            continue
        assets.append(
            AssetCopy(
                source=source_asset,
                destination=destination_asset,
            )
        )
    unique = {
        (item.source, item.destination): item
        for item in assets
    }
    return tuple(
        unique[key]
        for key in sorted(
            unique,
            key=lambda pair: (str(pair[0]), str(pair[1])),
        )
    )


def build_curation_plan(
    vault: Path,
    reviews: tuple[ReviewItem, ...],
) -> CurationPlan:
    vault = Path(vault).resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault: {vault}")
    issues = validate_review_manifest(vault, reviews)
    if issues:
        raise ValueError("审阅清单验证失败:\n" + "\n".join(issues))

    source_root = vault / "30_精选资料"
    review_by_path = {
        review.path.as_posix(): review
        for review in reviews
    }
    moves = []
    assets = []
    updates = []
    for review in reviews:
        source = source_root / Path(*review.path.parts)
        if review.decision == "trash":
            destination = _trash_destination(vault, review.path)
            moves.append(MoveItem(source=source, destination=destination))
            assets.extend(
                _local_assets_for_move(vault, source, destination)
            )
            continue
        link_reviews = tuple(
            review_by_path[target.as_posix()]
            for target in review.links
        )
        original = source.read_text(encoding="utf-8")
        expected = render_auto_links(original, link_reviews)
        if expected != original:
            updates.append(MarkdownUpdate(path=source, expected=expected))

    asset_map = {
        (item.source, item.destination): item
        for item in assets
    }
    assets = [
        asset_map[key]
        for key in sorted(
            asset_map,
            key=lambda pair: (str(pair[0]), str(pair[1])),
        )
    ]
    snapshot_sources = {
        item.source for item in moves
    } | {
        item.path for item in updates
    } | {
        item.source for item in assets
    }
    for domain_root in source_root.iterdir():
        index = domain_root / INDEX_FILENAME
        if domain_root.is_dir() and index.is_file():
            snapshot_sources.add(index)

    governance = vault / "80_系统" / "知识库治理"
    snapshots = governance / "变更快照"
    return CurationPlan(
        vault=vault,
        reviews=tuple(reviews),
        moves=tuple(sorted(moves, key=lambda item: str(item.source))),
        assets=tuple(assets),
        updates=tuple(sorted(updates, key=lambda item: str(item.path))),
        snapshot_sources=tuple(sorted(snapshot_sources)),
        snapshot_zip=snapshots / f"{SNAPSHOT_BASENAME}.zip",
        snapshot_manifest=snapshots / f"{SNAPSHOT_BASENAME}.json",
        audit_log=governance / "审核日志" / AUDIT_LOG_NAME,
    )


def build_completed_curation_plan(
    vault: Path,
    reviews: tuple[ReviewItem, ...],
) -> CurationPlan:
    vault = Path(vault).resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault: {vault}")
    source_root = vault / "30_精选资料"
    moves = []
    assets = []
    for review in reviews:
        source = source_root / Path(*review.path.parts)
        if review.decision != "trash":
            continue
        destination = _trash_destination(vault, review.path)
        moves.append(MoveItem(source=source, destination=destination))
        assets.extend(
            _local_assets_for_completed_move(
                vault,
                source,
                destination,
            )
        )
    asset_map = {
        (item.source, item.destination): item
        for item in assets
    }
    governance = vault / "80_系统" / "知识库治理"
    snapshots = governance / "变更快照"
    return CurationPlan(
        vault=vault,
        reviews=tuple(reviews),
        moves=tuple(sorted(moves, key=lambda item: str(item.source))),
        assets=tuple(
            asset_map[key]
            for key in sorted(
                asset_map,
                key=lambda pair: (str(pair[0]), str(pair[1])),
            )
        ),
        updates=(),
        snapshot_sources=(),
        snapshot_zip=snapshots / f"{SNAPSHOT_BASENAME}.zip",
        snapshot_manifest=snapshots / f"{SNAPSHOT_BASENAME}.json",
        audit_log=governance / "审核日志" / AUDIT_LOG_NAME,
    )


def preflight_issues(plan: CurationPlan) -> tuple[str, ...]:
    issues = []
    for move in plan.moves:
        if move.destination.exists():
            if not move.destination.is_file():
                issues.append(
                    f"废纸篓目标类型冲突: "
                    f"{move.destination.relative_to(plan.vault)}"
                )
            elif move.destination.read_bytes() != move.source.read_bytes():
                issues.append(
                    f"废纸篓目标内容冲突: "
                    f"{move.destination.relative_to(plan.vault)}"
                )
    for asset in plan.assets:
        if asset.destination.exists():
            if not asset.destination.is_file():
                issues.append(
                    f"废纸篓附件目标类型冲突: "
                    f"{asset.destination.relative_to(plan.vault)}"
                )
            elif sha256_file(asset.destination) != sha256_file(asset.source):
                issues.append(
                    f"废纸篓附件目标内容冲突: "
                    f"{asset.destination.relative_to(plan.vault)}"
                )
    return tuple(issues)


def _snapshot_payload(plan: CurationPlan) -> dict[str, object]:
    return {
        "schema_version": 1,
        "vault": str(plan.vault),
        "created_at": datetime.now().astimezone().isoformat(),
        "files": [
            {
                "path": source.relative_to(plan.vault).as_posix(),
                "size": source.stat().st_size,
                "sha256": sha256_file(source),
            }
            for source in plan.snapshot_sources
        ],
    }


def create_snapshot(
    plan: CurationPlan,
    zip_path: Path,
    manifest_path: Path,
) -> None:
    issues = preflight_issues(plan)
    if issues:
        raise RuntimeError("整理预检失败:\n" + "\n".join(issues))
    zip_path = Path(zip_path)
    manifest_path = Path(manifest_path)
    if zip_path.exists() or manifest_path.exists():
        raise FileExistsError("整理快照或清单已存在，拒绝覆盖")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _snapshot_payload(plan)
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for source in plan.snapshot_sources:
            archive.write(
                source,
                source.relative_to(plan.vault).as_posix(),
            )
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _restore_snapshot(plan: CurationPlan) -> None:
    with zipfile.ZipFile(plan.snapshot_zip) as archive:
        for info in archive.infolist():
            destination = plan.vault / Path(*PurePosixPath(info.filename).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def _render_audit_log(plan: CurationPlan) -> str:
    keep_count = sum(
        review.decision == "keep"
        for review in plan.reviews
    )
    trash_count = len(plan.reviews) - keep_count
    edge_count = sum(len(review.links) for review in plan.reviews) // 2
    lines = [
        "# 精选资料逐篇审阅",
        "",
        f"- 审阅总数：{len(plan.reviews)}",
        f"- 保留：{keep_count}",
        f"- 移入废纸篓：{trash_count}",
        f"- 双向链接边：{edge_count}",
        "",
        "| 原路径 | 结论 | 主题 | 理由 | 自动链接数 |",
        "|---|---|---|---|---:|",
    ]
    for review in sorted(plan.reviews, key=lambda item: item.path.as_posix()):
        values = (
            review.path.as_posix(),
            "保留" if review.decision == "keep" else "移入废纸篓",
            review.topic,
            review.reason,
            str(len(review.links)),
        )
        escaped = [value.replace("|", "｜") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.append("")
    return "\n".join(lines)


def apply_curation(plan: CurationPlan) -> None:
    if not plan.snapshot_zip.is_file() or not plan.snapshot_manifest.is_file():
        raise RuntimeError("缺少整理前 ZIP 或 SHA-256 清单")
    issues = preflight_issues(plan)
    if issues:
        raise RuntimeError("整理预检失败:\n" + "\n".join(issues))
    created = []
    try:
        for asset in plan.assets:
            asset.destination.parent.mkdir(parents=True, exist_ok=True)
            if not asset.destination.exists():
                shutil.copy2(asset.source, asset.destination)
                created.append(asset.destination)
        for move in plan.moves:
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            if move.destination.exists():
                if move.source.exists():
                    move.source.unlink()
            else:
                shutil.move(move.source, move.destination)
                created.append(move.destination)
        for update in plan.updates:
            update.path.write_text(update.expected, encoding="utf-8")

        source_root = plan.vault / "30_精选资料"
        for domain_root in sorted(source_root.iterdir()):
            if domain_root.is_dir():
                write_knowledge_base_index(
                    domain_root,
                    domain=domain_root.name,
                )
        plan.audit_log.parent.mkdir(parents=True, exist_ok=True)
        plan.audit_log.write_text(
            _render_audit_log(plan),
            encoding="utf-8",
        )
        created.append(plan.audit_log)
    except Exception:
        _restore_snapshot(plan)
        for path in reversed(created):
            if path.exists() and path.is_file():
                path.unlink()
        raise


def _expected_link_targets(review: ReviewItem) -> tuple[str, ...]:
    return tuple(
        PurePosixPath("30_精选资料", *target.parts)
        .as_posix()
        for target in sorted(review.links)
    )


def validate_completed_curation(plan: CurationPlan) -> tuple[str, ...]:
    issues = []
    source_root = plan.vault / "30_精选资料"
    for review in plan.reviews:
        source = source_root / Path(*review.path.parts)
        if review.decision == "trash":
            destination = _trash_destination(plan.vault, review.path)
            if source.exists():
                issues.append(f"错域源文档仍存在: {review.path.as_posix()}")
            if not destination.is_file():
                issues.append(f"废纸篓文档缺失: {review.path.as_posix()}")
            continue
        if not source.is_file():
            issues.append(f"保留文档缺失: {review.path.as_posix()}")
            continue
        actual_links = tuple(
            sorted(
                extract_auto_link_targets(
                    source.read_text(encoding="utf-8")
                )
            )
        )
        expected_links = tuple(sorted(_expected_link_targets(review)))
        if actual_links != expected_links:
            issues.append(
                f"自动链接与审阅清单不一致: {review.path.as_posix()}"
            )
        if len(actual_links) > 3:
            issues.append(
                f"自动链接超过 3 条: {review.path.as_posix()}"
            )
    for asset in plan.assets:
        if not asset.destination.is_file():
            issues.append(
                f"废纸篓附件缺失: "
                f"{asset.destination.relative_to(plan.vault).as_posix()}"
            )
        elif sha256_file(asset.destination) != sha256_file(asset.source):
            issues.append(
                f"废纸篓附件哈希不一致: "
                f"{asset.destination.relative_to(plan.vault).as_posix()}"
            )
    if not plan.snapshot_zip.is_file():
        issues.append("整理前 ZIP 缺失")
    if not plan.snapshot_manifest.is_file():
        issues.append("整理前 SHA-256 清单缺失")
    if not plan.audit_log.is_file():
        issues.append("逐篇审阅日志缺失")
    return tuple(issues)


def _print_summary(reviews: tuple[ReviewItem, ...]) -> None:
    keep_count = sum(
        review.decision == "keep"
        for review in reviews
    )
    trash_count = len(reviews) - keep_count
    edge_count = sum(len(review.links) for review in reviews) // 2
    print(f"审阅总数：{len(reviews)}")
    print(f"保留：{keep_count}")
    print(f"移入废纸篓：{trash_count}")
    print(f"双向链接边：{edge_count}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="逐篇整理 Obsidian 精选资料并维护受控双向链接"
    )
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if args.apply and args.verify:
        print("--apply 与 --verify 不能同时使用", file=sys.stderr)
        return 2
    if args.apply and args.confirm != "CURATE_SELECTED_MATERIALS":
        print(
            "--apply 必须同时提供 "
            "--confirm CURATE_SELECTED_MATERIALS",
            file=sys.stderr,
        )
        return 2

    try:
        reviews = load_review_manifest(args.review)
        if args.verify:
            plan = build_completed_curation_plan(args.vault, reviews)
            issues = validate_completed_curation(plan)
            if issues:
                for issue in issues:
                    print(f"验证失败: {issue}", file=sys.stderr)
                return 1
            _print_summary(reviews)
            print("验证通过")
            return 0

        plan = build_curation_plan(args.vault, reviews)
        issues = preflight_issues(plan)
        if issues:
            for issue in issues:
                print(f"预检失败: {issue}", file=sys.stderr)
            return 1
        _print_summary(reviews)
        if not args.apply:
            print("预览模式：未修改 vault")
            return 0

        create_snapshot(
            plan,
            plan.snapshot_zip,
            plan.snapshot_manifest,
        )
        apply_curation(plan)
        completed_issues = validate_completed_curation(plan)
        if completed_issues:
            for issue in completed_issues:
                print(f"验证失败: {issue}", file=sys.stderr)
            return 1
        print("整理完成并验证通过")
        return 0
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
