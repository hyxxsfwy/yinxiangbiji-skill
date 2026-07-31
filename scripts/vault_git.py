#!/usr/bin/env python3
"""管理 Obsidian Vault 的 Markdown-only Git 历史。"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


STABLE_OBSIDIAN_FILES = {
    ".obsidian/app.json",
    ".obsidian/appearance.json",
    ".obsidian/core-plugins.json",
    ".obsidian/graph.json",
}

GITIGNORE = """# 默认拒绝：仅放行 Markdown 和稳定 Obsidian 配置
*
!*/
!*.md
!.gitignore
!.gitattributes
!.obsidian/
!.obsidian/app.json
!.obsidian/appearance.json
!.obsidian/core-plugins.json
!.obsidian/graph.json
!.obsidian/snippets/
!.obsidian/snippets/*.css
!.obsidian/themes/
!.obsidian/themes/*/
!.obsidian/themes/*/manifest.json
!.obsidian/themes/*/theme.css
!.obsidian/plugins/
!.obsidian/plugins/*/
!.obsidian/plugins/*/manifest.json
!.obsidian/plugins/*/data.json

# 运行状态、附件、设备状态和凭据始终忽略
.state/
**/_attachments/
.obsidian/workspace*.json
**/.env
**/.env.*
**/credentials.json
**/secrets.json
**/*.enex
"""

GITATTRIBUTES = """* text=auto
*.md text eol=lf
*.json text eol=lf
*.css text eol=lf
"""


@dataclass(frozen=True)
class GitBaseline:
    enabled: bool
    branch: str | None
    head: str | None


@dataclass(frozen=True)
class GitHistoryResult:
    enabled: bool
    branch: str | None
    commit: str | None
    tracked_paths: int
    pushed: bool
    status: str

    def to_dict(self):
        return asdict(self)


def _git(vault, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(Path(vault).resolve()), *map(str, args)],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write_if_changed(path, content):
    path = Path(path)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def write_git_policy(vault):
    vault = Path(vault).resolve()
    vault.mkdir(parents=True, exist_ok=True)
    changed = []
    if _write_if_changed(vault / ".gitignore", GITIGNORE):
        changed.append(".gitignore")
    if _write_if_changed(vault / ".gitattributes", GITATTRIBUTES):
        changed.append(".gitattributes")
    return tuple(changed)


def _is_allowed_path(relative):
    path = PurePosixPath(str(relative).replace("\\", "/"))
    text = path.as_posix()
    parts = path.parts
    if text in {".gitignore", ".gitattributes"}:
        return True
    if ".state" in parts or "_attachments" in parts:
        return False
    if path.suffix.lower() == ".md":
        return True
    if text in STABLE_OBSIDIAN_FILES:
        return True
    if len(parts) == 3 and parts[:2] == (".obsidian", "snippets"):
        return path.suffix.lower() == ".css"
    if (
        len(parts) == 4
        and parts[0] == ".obsidian"
        and parts[1] in {"themes", "plugins"}
    ):
        if parts[1] == "themes":
            return parts[3] in {"manifest.json", "theme.css"}
        return parts[3] in {"manifest.json", "data.json"}
    return False


def _tracked_paths(vault):
    result = _git(vault, "ls-files", "-z")
    return tuple(sorted(path for path in result.stdout.split("\0") if path))


def verify_tracked_paths(vault):
    return tuple(
        path for path in _tracked_paths(vault) if not _is_allowed_path(path)
    )


def _branch(vault):
    result = _git(
        vault,
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
        check=False,
    )
    return result.stdout.strip() or None


def _head(vault):
    result = _git(
        vault,
        "rev-parse",
        "--verify",
        "HEAD",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _require_identity(vault):
    missing = []
    for key in ("user.name", "user.email"):
        result = _git(vault, "config", "--get", key, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            missing.append(key)
    if missing:
        raise RuntimeError(
            "Git 未配置提交身份: " + ", ".join(missing)
        )


def _allowed_existing_paths(vault):
    vault = Path(vault).resolve()
    allowed = []
    for directory, names, files in os.walk(vault):
        names[:] = [
            name
            for name in names
            if name not in {".git", ".state", "_attachments"}
        ]
        directory_path = Path(directory)
        for name in files:
            relative = (directory_path / name).relative_to(vault).as_posix()
            if _is_allowed_path(relative):
                allowed.append(relative)
    return tuple(sorted(allowed))


def _path_batches(paths, max_characters=12_000):
    batch = []
    characters = 0
    for path in paths:
        cost = len(str(path)) + 3
        if batch and characters + cost > max_characters:
            yield tuple(batch)
            batch = []
            characters = 0
        batch.append(path)
        characters += cost
    if batch:
        yield tuple(batch)


def _git_add(vault, paths):
    for batch in _path_batches(paths):
        _git(vault, "add", "--", *batch)


def initialize_vault_git(vault):
    vault = Path(vault).resolve()
    vault.mkdir(parents=True, exist_ok=True)
    if not (vault / ".git").is_dir():
        subprocess.run(
            ["git", "init", "-b", "main", str(vault)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    _git(vault, "config", "core.quotepath", "false")
    _require_identity(vault)
    write_git_policy(vault)
    allowed = _allowed_existing_paths(vault)
    if allowed:
        _git_add(vault, allowed)
    violations = verify_tracked_paths(vault)
    if violations:
        raise RuntimeError(f"Git 索引含禁用路径: {violations}")
    staged = _git(vault, "diff", "--cached", "--name-only", "-z").stdout
    if staged:
        _git(vault, "commit", "-m", "初始化 Obsidian Markdown 历史")
        status = "initialized"
    else:
        status = "existing"
    tracked = _tracked_paths(vault)
    return GitHistoryResult(
        enabled=True,
        branch=_branch(vault),
        commit=_head(vault),
        tracked_paths=len(tracked),
        pushed=False,
        status=status,
    )


def preflight_vault_git(vault):
    vault = Path(vault).resolve()
    if not (vault / ".git").is_dir():
        return GitBaseline(False, None, None)
    violations = verify_tracked_paths(vault)
    if violations:
        raise RuntimeError(f"Git 索引含禁用路径: {violations}")
    dirty = _git(
        vault,
        "status",
        "--porcelain",
        "--untracked-files=no",
    ).stdout
    if dirty:
        raise RuntimeError("Git 被跟踪工作树不干净，拒绝开始导出")
    _require_identity(vault)
    return GitBaseline(True, _branch(vault), _head(vault))


def _unstage(vault, paths):
    if not paths:
        return
    for batch in _path_batches(paths):
        if _head(vault):
            _git(vault, "restore", "--staged", "--", *batch, check=False)
        else:
            _git(
                vault,
                "rm",
                "--cached",
                "--ignore-unmatch",
                "--",
                *batch,
                check=False,
            )


def commit_transaction(vault, journal, baseline, message):
    vault = Path(vault).resolve()
    if not baseline.enabled:
        return GitHistoryResult(
            enabled=False,
            branch=None,
            commit=None,
            tracked_paths=0,
            pushed=False,
            status="disabled",
        )
    current_head = _head(vault)
    if current_head != baseline.head:
        raise RuntimeError("Git HEAD 在导出期间发生变化")
    allowed = tuple(
        path for path in journal.changed_paths() if _is_allowed_path(path)
    )
    if allowed:
        _git_add(vault, allowed)
    staged = tuple(
        path
        for path in _git(
            vault,
            "diff",
            "--cached",
            "--name-only",
            "-z",
        ).stdout.split("\0")
        if path
    )
    unexpected_staged = tuple(path for path in staged if path not in allowed)
    if unexpected_staged or any(not _is_allowed_path(path) for path in staged):
        _unstage(vault, allowed)
        raise RuntimeError(
            f"Git 暂存区包含事务外或禁用路径: {unexpected_staged}"
        )
    unstaged = tuple(
        path
        for path in _git(
            vault,
            "diff",
            "--name-only",
            "-z",
        ).stdout.split("\0")
        if path
    )
    if unstaged:
        _unstage(vault, allowed)
        raise RuntimeError(f"检测到事务外被跟踪修改: {unstaged}")
    if not staged:
        return GitHistoryResult(
            enabled=True,
            branch=_branch(vault),
            commit=current_head,
            tracked_paths=len(_tracked_paths(vault)),
            pushed=False,
            status="no_changes",
        )
    _git(vault, "commit", "-m", message)
    violations = verify_tracked_paths(vault)
    if violations:
        raise RuntimeError(f"提交后出现禁用路径: {violations}")
    return GitHistoryResult(
        enabled=True,
        branch=_branch(vault),
        commit=_head(vault),
        tracked_paths=len(_tracked_paths(vault)),
        pushed=False,
        status="committed",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "verify"))
    args = parser.parse_args(argv)
    try:
        from .runtime import configure_utf8_output, load_vault_root
    except ImportError:
        from runtime import configure_utf8_output, load_vault_root

    configure_utf8_output()
    vault = load_vault_root()
    if args.command == "init":
        payload = initialize_vault_git(vault).to_dict()
    else:
        violations = verify_tracked_paths(vault)
        payload = {
            "ok": not violations,
            "violations": list(violations),
            "tracked_paths": len(_tracked_paths(vault)),
        }
        if violations:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
