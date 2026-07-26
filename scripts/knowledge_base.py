"""AI 知识库的月度归档与目录索引工具。"""

from datetime import datetime


INDEX_FILENAME = "目录索引.md"


def month_folder_name(created: datetime) -> str:
    """把笔记创建时间转换为稳定的中文月份目录名。"""
    return created.strftime("%Y年%m月")
