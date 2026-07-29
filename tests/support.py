"""跨平台测试帮助函数。"""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import uuid


@contextmanager
def workspace_temp_dir():
    """在测试目录下创建可写临时目录，规避 Windows 0o700 ACL 问题。"""
    path = Path(__file__).resolve().parent / f".tmp-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def create_directory_symlink_or_skip(test_case, link, target):
    """创建目录符号链接；当前环境不支持时跳过依赖链接的用例。"""
    try:
        Path(link).symlink_to(Path(target), target_is_directory=True)
    except OSError as exc:
        test_case.skipTest(f"当前环境无法创建目录符号链接: {exc}")


def create_directory_link_or_skip(test_case, link, target):
    """创建真实目录链接；Windows 优先使用无需开发者模式的 Junction。"""
    link = Path(link)
    target = Path(target)
    if os.name != "nt":
        create_directory_symlink_or_skip(test_case, link, target)
        return
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        test_case.skipTest(
            "当前环境无法创建目录 Junction: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
