#!/usr/bin/env python3
"""印象笔记脚本共享的配置、控制台和 NoteStore 客户端工具。"""

import os
from pathlib import Path
import sys

import evernote.edam.notestore.NoteStore as NoteStore
import thrift.protocol.TBinaryProtocol as TBinaryProtocol
import thrift.transport.THttpClient as THttpClient


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HTTP_TIMEOUT_MS = 60_000


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
