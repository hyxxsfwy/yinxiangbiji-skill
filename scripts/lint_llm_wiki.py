from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scripts.domain_taxonomy import MANAGED_DOMAINS
from scripts.restructure_obsidian_vault import split_frontmatter
from scripts.runtime import load_vault_root
from scripts.vault_state import require_path_within_vault


REQUIRED_PATHS = (
    Path("AGENTS.md"),
    Path("20_知识笔记"),
    Path("30_精选资料"),
    Path("80_系统/知识库治理"),
)
ALLOWED_TYPES = {"资料", "知识", "索引", "模板"}
ALLOWED_STATUS = {"待提炼", "常青"}
ALLOWED_REVIEW_STATUS = {"pending", "human-approved"}
ALLOWED_LLM_POLICY = {"standard", "strict", "off"}


@dataclass(frozen=True)
class LintIssue:
    code: str
    severity: str
    path: str
    detail: str
    fixable: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "detail": self.detail,
            "fixable": self.fixable,
        }


@dataclass(frozen=True)
class LintReport:
    vault: Path
    checked_at: datetime
    checked_files: int
    issues: tuple[LintIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.issues)

    def to_dict(self) -> dict[str, object]:
        counts = {"error": 0, "warning": 0, "manual_review": 0}
        for item in self.issues:
            counts[item.severity] += 1
        return {
            "ok": self.ok,
            "vault": str(self.vault),
            "checked_at": self.checked_at.isoformat(),
            "checked_files": self.checked_files,
            "summary": counts,
            "issues": [item.to_dict() for item in self.issues],
        }


def _relative(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def _managed_documents(vault: Path) -> tuple[Path, ...]:
    roots = (vault / "20_知识笔记", vault / "30_精选资料")
    documents = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            resolved = require_path_within_vault(
                path,
                vault,
                "Lint 扫描文件",
                allowed_root=root,
            )
            if resolved.is_file():
                documents.append(resolved)
    return tuple(sorted(set(documents)))


def lint_vault(
    vault: Path,
    *,
    checked_at: datetime | None = None,
) -> LintReport:
    vault = load_vault_root(explicit=vault)
    issues: list[LintIssue] = []
    for required in REQUIRED_PATHS:
        target = vault / required
        is_schema = required == Path("AGENTS.md")
        valid = target.is_file() if is_schema else target.is_dir()
        if not valid:
            if is_schema:
                code = "MISSING_SCHEMA"
            else:
                code = "MISSING_REQUIRED_DIRECTORY"
            issues.append(
                LintIssue(
                    code,
                    "error",
                    required.as_posix(),
                    "必需路径不存在",
                )
            )
    documents = _managed_documents(vault)
    allowed_values = {
        "type": ALLOWED_TYPES,
        "domain": set(MANAGED_DOMAINS),
        "status": ALLOWED_STATUS,
        "review_status": ALLOWED_REVIEW_STATUS,
        "llm_policy": ALLOWED_LLM_POLICY,
    }
    for path in documents:
        try:
            fields, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            if not fields:
                raise ValueError("缺少 Frontmatter")
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(
                LintIssue(
                    "INVALID_FRONTMATTER",
                    "error",
                    _relative(vault, path),
                    str(exc),
                )
            )
            continue
        for name, values in allowed_values.items():
            value = fields.get(name, "")
            if name == "domain" and fields.get("type") == "索引" and not value:
                continue
            if value not in values:
                issues.append(
                    LintIssue(
                        "INVALID_PROPERTY_VALUE",
                        "error",
                        _relative(vault, path),
                        f"{name}={value!r} 不在允许值中",
                    )
                )
    return LintReport(
        vault=vault,
        checked_at=checked_at or datetime.now(timezone.utc),
        checked_files=len(documents),
        issues=tuple(issues),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读检查 Obsidian LLM Wiki")
    parser.add_argument("--vault")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def _render_text(report: LintReport) -> str:
    lines = [
        f"ok: {str(report.ok).lower()}",
        f"checked_files: {report.checked_files}",
    ]
    lines.extend(
        f"[{item.severity}] {item.code} {item.path}: {item.detail}"
        for item in report.issues
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = lint_vault(load_vault_root(explicit=args.vault))
    except (OSError, ValueError) as exc:
        print(f"配置错误: {exc}")
        return 2
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
