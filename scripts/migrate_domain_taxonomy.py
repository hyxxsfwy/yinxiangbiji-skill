#!/usr/bin/env python3
"""把 Obsidian Vault 的固定受管领域迁移到十二领域契约。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

try:
    from .domain_taxonomy import MANAGED_DOMAINS
    from .export_transaction import ROLLBACK_CONFIRMATION, VaultMutationJournal
    from .knowledge_base import write_knowledge_base_index
    from .reclassify_selected_materials import _verify_indexes
    from .restructure_obsidian_vault import render_home, render_knowledge_catalog
    from .runtime import configure_utf8_output, load_vault_root
    from .vault_state import VaultStatePaths, require_path_within_vault, runtime_write_lock
except ImportError:
    from domain_taxonomy import MANAGED_DOMAINS
    from export_transaction import ROLLBACK_CONFIRMATION, VaultMutationJournal
    from knowledge_base import write_knowledge_base_index
    from reclassify_selected_materials import _verify_indexes
    from restructure_obsidian_vault import render_home, render_knowledge_catalog
    from runtime import configure_utf8_output, load_vault_root
    from vault_state import VaultStatePaths, require_path_within_vault, runtime_write_lock


CONFIRMATION = "EXPAND_MANAGED_DOMAINS"
LAYERS = ("20_知识笔记", "30_精选资料")
LEGACY_DOMAIN = "软件工程"
TARGET_DOMAIN = "信息技术"
DOMAIN_LINE = re.compile(
    r"(?m)^domain:\s*(?:软件工程|'软件工程'|\"软件工程\")\s*$"
)
LEGACY_PATHS = (
    "20_知识笔记/软件工程",
    "30_精选资料/软件工程",
)


@dataclass
class MigrationPlan:
    vault: Path
    moves: list[tuple[Path, Path]] = field(default_factory=list)
    file_moves: list[tuple[Path, Path]] = field(default_factory=list)
    rewrites: dict[Path, str] = field(default_factory=dict)
    missing_domains: dict[str, list[str]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.issues

    @property
    def change_count(self):
        return len(self.file_moves) + len(self.rewrites) + sum(
            len(domains) for domains in self.missing_domains.values()
        )

    def to_dict(self):
        relative = lambda path: path.relative_to(self.vault).as_posix()
        return {
            "ok": self.ok,
            "vault": str(self.vault),
            "change_count": self.change_count,
            "moves": [
                {"source": relative(source), "target": relative(target)}
                for source, target in self.moves
            ],
            "file_moves": len(self.file_moves),
            "rewrites": sorted(relative(path) for path in self.rewrites),
            "missing_domains": self.missing_domains,
            "issues": self.issues,
        }


def _inside(path, vault, description):
    return require_path_within_vault(path, vault, description)


def _rewrite_contract(text):
    rewritten = DOMAIN_LINE.sub("domain: 信息技术", text)
    for old_path in LEGACY_PATHS:
        rewritten = rewritten.replace(
            old_path,
            old_path.replace(LEGACY_DOMAIN, TARGET_DOMAIN),
        )
    return rewritten


def _validate_frontmatter(path, text, issues):
    if not text.startswith("---\n"):
        return
    if "\n---\n" not in text[4:]:
        issues.append(f"frontmatter 未闭合: {path.as_posix()}")


def build_plan(vault):
    vault = Path(vault).expanduser().resolve()
    plan = MigrationPlan(vault=vault)
    if not vault.is_dir():
        plan.issues.append(f"Vault 不存在: {vault}")
        return plan

    for layer in LAYERS:
        root = _inside(vault / layer, vault, f"{layer} 根目录")
        if not root.is_dir():
            plan.issues.append(f"缺少目录: {layer}")
            continue
        missing = [domain for domain in MANAGED_DOMAINS if not (root / domain).is_dir()]
        plan.missing_domains[layer] = missing
        legacy = _inside(root / LEGACY_DOMAIN, vault, "旧领域目录")
        target = _inside(root / TARGET_DOMAIN, vault, "新领域目录")
        if legacy.exists():
            if not legacy.is_dir() or legacy.is_symlink():
                plan.issues.append(f"旧领域路径不是普通目录: {legacy.relative_to(vault)}")
                continue
            if target.exists() and (not target.is_dir() or target.is_symlink()):
                plan.issues.append(f"目标领域路径不是普通目录: {target.relative_to(vault)}")
                continue
            plan.moves.append((legacy, target))
            for source in sorted(legacy.rglob("*")):
                if source.is_dir():
                    continue
                if not source.is_file() or source.is_symlink():
                    plan.issues.append(f"迁移源不是普通文件: {source.relative_to(vault)}")
                    continue
                destination = target / source.relative_to(legacy)
                _inside(destination, vault, "领域迁移目标")
                if destination.exists():
                    if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                        plan.issues.append(
                            "迁移目标冲突: "
                            f"{source.relative_to(vault).as_posix()} -> "
                            f"{destination.relative_to(vault).as_posix()}"
                        )
                        continue
                plan.file_moves.append((source, destination))

    for path in sorted(vault.rglob("*.md")):
        if path.is_symlink() or ".state" in path.relative_to(vault).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            plan.issues.append(f"Markdown 无法读取: {path.relative_to(vault)} ({exc})")
            continue
        _validate_frontmatter(path.relative_to(vault), text, plan.issues)
        rewritten = _rewrite_contract(text)
        if rewritten != text:
            destination = path
            for source_root, target_root in plan.moves:
                try:
                    destination = target_root / path.relative_to(source_root)
                    break
                except ValueError:
                    continue
            plan.rewrites[destination] = rewritten
    return plan


def _atomic_text(path, text, journal):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    journal.prepare_write(path)
    temporary = path.with_suffix(path.suffix + ".taxonomy.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    journal.record_write(path)


def _remove_empty_tree(root):
    if not root.is_dir():
        return
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def _transaction_hash(plan):
    payload = json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_plan(plan, confirm):
    if confirm != CONFIRMATION:
        raise ValueError(f"迁移确认词必须是 {CONFIRMATION}")
    if not plan.ok:
        raise ValueError("迁移预检失败: " + "; ".join(plan.issues))

    paths = VaultStatePaths.for_vault(plan.vault)
    paths.root.mkdir(parents=True, exist_ok=True)
    job_id = "domain-taxonomy-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    journal = VaultMutationJournal.begin(
        plan.vault,
        paths.root,
        job_id,
        _transaction_hash(plan),
        paths.catalog,
    )
    created_directories = []
    failure = None
    try:
        with runtime_write_lock(paths, job_id):
            for layer, domains in plan.missing_domains.items():
                for domain in domains:
                    directory = plan.vault / layer / domain
                    directory.mkdir(parents=True, exist_ok=True)
                    created_directories.append(directory)

            for source, destination in plan.file_moves:
                destination.parent.mkdir(parents=True, exist_ok=True)
                journal.prepare_move(source, destination)
                if destination.exists():
                    source.unlink()
                else:
                    os.replace(source, destination)
                journal.record_move(source, destination)

            for path, rewritten in plan.rewrites.items():
                _atomic_text(path, rewritten, journal)

            for source_root, _ in plan.moves:
                _remove_empty_tree(source_root)

            for domain in MANAGED_DOMAINS:
                domain_root = plan.vault / "30_精选资料" / domain
                domain_root.mkdir(parents=True, exist_ok=True)
                write_knowledge_base_index(domain_root, domain=domain, journal=journal)

            _atomic_text(
                plan.vault / "20_知识笔记" / "目录索引.md",
                render_knowledge_catalog(plan.vault),
                journal,
            )
            _atomic_text(plan.vault / "00_首页.md", render_home(), journal)

            verification = verify_vault(plan.vault)
            if not verification["ok"]:
                raise RuntimeError("迁移验证失败: " + "; ".join(verification["issues"]))
            summary = journal.seal()
            journal.mark_committed()
            return {
                "ok": True,
                "job_id": job_id,
                "changed_paths": summary.changed_paths,
                "verification": verification,
            }
    except Exception as exc:
        failure = exc

    try:
        journal.restore(ROLLBACK_CONFIRMATION)
    finally:
        for directory in sorted(created_directories, key=lambda path: len(path.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
    raise failure


def verify_vault(vault):
    vault = Path(vault).expanduser().resolve()
    issues = []
    expected = set(MANAGED_DOMAINS)
    for layer in LAYERS:
        root = vault / layer
        if not root.is_dir():
            issues.append(f"缺少目录: {layer}")
            continue
        actual = {path.name for path in root.iterdir() if path.is_dir()}
        if actual != expected:
            issues.append(
                f"{layer} 领域目录不一致: missing={sorted(expected - actual)}, "
                f"unexpected={sorted(actual - expected)}"
            )
        if (root / LEGACY_DOMAIN).exists():
            issues.append(f"仍存在旧领域目录: {layer}/{LEGACY_DOMAIN}")

    for path in sorted(vault.rglob("*.md")):
        if path.is_symlink() or ".state" in path.relative_to(vault).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(f"Markdown 无法读取: {path.relative_to(vault)} ({exc})")
            continue
        if DOMAIN_LINE.search(text):
            issues.append(f"仍存在旧 domain: {path.relative_to(vault).as_posix()}")
        if any(old_path in text for old_path in LEGACY_PATHS):
            issues.append(f"仍存在旧领域链接: {path.relative_to(vault).as_posix()}")

    if (vault / "30_精选资料").is_dir():
        try:
            index_counts, index_issues = _verify_indexes(vault)
            issues.extend(index_issues)
        except (OSError, ValueError) as exc:
            index_counts = {}
            issues.append(f"精选资料索引验证失败: {exc}")
    else:
        index_counts = {}
    home = vault / "00_首页.md"
    if not home.is_file():
        issues.append("缺少首页: 00_首页.md")
    else:
        home_text = home.read_text(encoding="utf-8")
        for domain in MANAGED_DOMAINS:
            link = f"[[30_精选资料/{domain}/目录索引|{domain}]]"
            if link not in home_text:
                issues.append(f"首页缺少领域入口: {domain}")
    return {"ok": not issues, "issues": issues, "index_counts": index_counts}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "apply", "verify"))
    parser.add_argument("--vault")
    parser.add_argument("--confirm")
    return parser.parse_args(argv)


def main(argv=None):
    configure_utf8_output()
    args = parse_args(argv)
    vault = Path(args.vault).expanduser().resolve() if args.vault else load_vault_root()
    try:
        if args.command == "verify":
            payload = verify_vault(vault)
        else:
            plan = build_plan(vault)
            payload = plan.to_dict()
            if args.command == "apply":
                payload = apply_plan(plan, args.confirm)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
