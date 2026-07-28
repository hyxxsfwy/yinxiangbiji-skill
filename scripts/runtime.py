#!/usr/bin/env python3
"""印象笔记脚本共享的配置、控制台和 NoteStore 客户端工具。"""

import os
from pathlib import Path
import sys
import time

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.error.ttypes import EDAMErrorCode, EDAMSystemException
import thrift.protocol.TBinaryProtocol as TBinaryProtocol
import thrift.transport.THttpClient as THttpClient


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HTTP_TIMEOUT_MS = 60_000


class RateLimitBudgetExceeded(RuntimeError):
    """服务端限流需要的等待时间超过当前任务预算。"""

    def __init__(self, required_seconds, waited_seconds=0):
        self.required_seconds = required_seconds
        self.waited_seconds = waited_seconds
        super().__init__(
            "印象笔记 API 限流，仍需等待 "
            f"{required_seconds} 秒；本任务已等待 {waited_seconds} 秒"
        )


def _read_dotenv(env_path):
    values = {}
    if not env_path.exists():
        return values

    with env_path.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def load_config(env_path=None):
    """读取环境变量或 skill 根目录 .env，环境变量优先。"""
    path = Path(env_path) if env_path is not None else SKILL_ROOT / ".env"
    file_values = _read_dotenv(path)
    return (
        os.environ.get("EVERNOTE_TOKEN")
        or file_values.get("EVERNOTE_TOKEN"),
        os.environ.get("EVERNOTE_NOTESTORE_URL")
        or file_values.get("EVERNOTE_NOTESTORE_URL"),
    )


def load_setting(name, env_path=None):
    """读取任意环境配置项，环境变量优先于仓库根目录 .env。"""
    path = Path(env_path) if env_path is not None else SKILL_ROOT / ".env"
    return os.environ.get(name) or _read_dotenv(path).get(name)


def configure_utf8_output():
    """确保包含中文和 emoji 的命令输出在 Windows 上使用 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def create_note_store(
    note_store_url,
    token=None,
    request_timeout_ms=DEFAULT_HTTP_TIMEOUT_MS,
):
    """构造 NoteStore 客户端，不输出或持久化凭据。"""
    if not note_store_url:
        raise ValueError("未配置 EVERNOTE_NOTESTORE_URL")

    transport = THttpClient.THttpClient(note_store_url)
    transport.setTimeout(request_timeout_ms)
    if token:
        transport.setCustomHeaders({"Authorization": f"Bearer {token}"})
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    return NoteStore.Client(protocol)


def find_notes_metadata(
    note_store,
    token,
    note_filter,
    max_results,
    result_spec,
    page_size=250,
):
    """分页拉取最多 ``max_results`` 条元数据，并返回总命中数。"""
    if max_results <= 0:
        return [], 0

    notes = []
    offset = 0
    total_notes = 0
    while len(notes) < max_results:
        limit = min(page_size, max_results - len(notes))
        result = note_store.findNotesMetadata(
            token,
            note_filter,
            offset,
            limit,
            result_spec,
        )
        total_notes = result.totalNotes
        page = list(result.notes or [])
        if not page:
            break
        notes.extend(page)
        offset += len(page)
        if offset >= total_notes:
            break
    return notes, total_notes


def find_all_notes_metadata(
    note_store,
    token,
    note_filter,
    result_spec,
    page_size=250,
):
    """分页读取服务端报告的全部元数据，禁止静默截断。"""
    if page_size <= 0:
        raise ValueError("page_size 必须大于 0")

    notes = []
    offset = 0
    total_notes = None
    while total_notes is None or offset < total_notes:
        limit = (
            page_size
            if total_notes is None
            else min(page_size, total_notes - offset)
        )
        result = note_store.findNotesMetadata(
            token,
            note_filter,
            offset,
            limit,
            result_spec,
        )
        total_notes = int(result.totalNotes or 0)
        page = list(result.notes or [])
        if not page:
            if offset < total_notes:
                raise RuntimeError(
                    "印象笔记元数据分页提前返回空页："
                    f"已读取 {offset}，服务端报告 {total_notes}"
                )
            break
        notes.extend(page)
        offset += len(page)

    if len(notes) != total_notes:
        raise RuntimeError(
            "印象笔记元数据未完整拉取："
            f"实际 {len(notes)}，服务端报告 {total_notes}"
        )
    return notes, total_notes


def call_with_rate_limit_retry(
    operation,
    *,
    mode="wait",
    max_wait_seconds=3600,
    sleep=time.sleep,
    on_wait=None,
):
    """按服务端建议等待时间重试限流操作，并限制累计等待预算。"""
    if mode not in {"wait", "stop"}:
        raise ValueError("mode 只能是 wait 或 stop")
    if max_wait_seconds < 0:
        raise ValueError("max_wait_seconds 不能小于 0")

    waited_seconds = 0
    while True:
        try:
            return operation()
        except EDAMSystemException as exc:
            if exc.errorCode != EDAMErrorCode.RATE_LIMIT_REACHED:
                raise
            required_seconds = max(0, int(exc.rateLimitDuration or 0))
            if (
                mode == "stop"
                or waited_seconds + required_seconds > max_wait_seconds
            ):
                raise RateLimitBudgetExceeded(
                    required_seconds=required_seconds,
                    waited_seconds=waited_seconds,
                ) from exc
            if on_wait is not None:
                on_wait(required_seconds)
            sleep(required_seconds)
            waited_seconds += required_seconds
