"""跨平台测试帮助函数。"""

from contextlib import contextmanager
from pathlib import Path
import shutil
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
