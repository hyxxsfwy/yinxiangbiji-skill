#!/usr/bin/env python3
"""按日期区间和关键词搜索印象笔记，并导出到 Obsidian。"""

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
import re

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.type.ttypes import NoteSortOrder

try:
    from .knowledge_base import finalize_knowledge_base, month_folder_name
except ImportError:
    from knowledge_base import finalize_knowledge_base, month_folder_name

try:
    from .runtime import (
        configure_utf8_output,
        create_note_store,
        find_notes_metadata,
        load_config,
    )
except ImportError:
    from runtime import (
        configure_utf8_output,
        create_note_store,
        find_notes_metadata,
        load_config,
    )

try:
    from .sync_to_obsidian import (
        enml_to_markdown,
        extract_resources,
        frontmatter,
        has_en_media,
        html_to_md,
        is_enml_clip,
        is_web_clip_by_content,
        make_attachments_section,
        referenced_attachment_filenames,
        resolve_note_path,
        save_attachments,
        simplify_markdown,
    )
except ImportError:
    from sync_to_obsidian import (
        enml_to_markdown,
        extract_resources,
        frontmatter,
        has_en_media,
        html_to_md,
        is_enml_clip,
        is_web_clip_by_content,
        make_attachments_section,
        referenced_attachment_filenames,
        resolve_note_path,
        save_attachments,
        simplify_markdown,
    )


def build_keyword_queries(keywords, since, until=None):
    since_text = since.strftime("%Y%m%d")
    date_terms = f"created:{since_text}"
    if until is not None:
        date_terms += f" -created:{until:%Y%m%d}"
    return [f"{date_terms} {keyword}" for keyword in keywords]


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return parsed


def export_limit(value):
    """解析正整数或表示不限数量的 ``all``。"""
    if str(value).casefold() == "all":
        return None
    return positive_int(value)


def note_freshness_key(note):
    """按更新时间、创建时间和 GUID 判断同标题笔记的新旧。"""
    return (
        getattr(note, "updated", 0) or 0,
        getattr(note, "created", 0) or 0,
        str(getattr(note, "guid", "") or ""),
    )


def deduplicate_notes_by_title(notes):
    """标题完全一致时只保留最新的一篇。"""
    winners = {}
    for note in notes:
        title_key = (getattr(note, "title", "") or "").strip()
        existing = winners.get(title_key)
        if existing is None or note_freshness_key(note) > note_freshness_key(
            existing
        ):
            winners[title_key] = note
    return list(winners.values())


def rank_note_candidates(search_batches, keywords):
    """按 GUID 合并并排序候选，不在读取正文前按标题丢弃候选。"""
    notes_by_guid = {}
    for batch in search_batches:
        for note in batch:
            existing = notes_by_guid.get(note.guid)
            if existing is None or (getattr(note, "updated", 0) or 0) > (
                getattr(existing, "updated", 0) or 0
            ):
                notes_by_guid[note.guid] = note

    folded_keywords = [keyword.casefold() for keyword in keywords]

    def sort_key(note):
        title = (getattr(note, "title", "") or "").casefold()
        title_matches = any(keyword in title for keyword in folded_keywords)
        return (
            title_matches,
            getattr(note, "updated", 0) or 0,
            getattr(note, "created", 0) or 0,
            str(getattr(note, "guid", "") or ""),
        )

    return sorted(notes_by_guid.values(), key=sort_key, reverse=True)


def select_top_notes(search_batches, keywords, limit):
    """兼容旧调用：按元数据排序、标题去重并应用数量限制。"""
    ranked = rank_note_candidates(search_batches, keywords)
    unique_titles = deduplicate_notes_by_title(ranked)
    return sorted(
        unique_titles,
        key=lambda note: ranked.index(note),
    )[:limit]


DOMAIN_PROFILES = {
    "AI": {
        "core": (
            "人工智能",
            "生成式ai",
            "generative ai",
            "大语言模型",
            "大模型",
            "language model",
            "llm",
            "机器学习",
            "深度学习",
            "神经网络",
            "智能体",
            "ai agent",
            "agentic",
            "rag",
            "chatgpt",
            "openai",
            "claude",
            "deepseek",
            "gpt",
            "qwen",
            "codex",
        ),
        "support": (
            "agent",
            "skill",
            "prompt",
            "提示词",
            "token",
            "embedding",
            "向量检索",
            "向量数据库",
            "transformer",
            "推理",
            "微调",
            "模型",
            "模型训练",
            "指令",
            "上下文",
            "工具调用",
            "上下文窗口",
            "mcp",
        ),
        "support_only_min": 4,
    },
    "Quant": {
        "core": (
            "量化交易",
            "量化投资",
            "量化研究",
            "因子投资",
            "多因子",
            "回测",
            "alpha",
            "高频交易",
            "algorithmic trading",
            "quantitative finance",
        ),
        "support": (
            "因子",
            "交易信号",
            "最大回撤",
            "夏普",
            "时间序列",
            "策略收益",
            "组合优化",
            "仓位",
        ),
    },
    "软件工程": {
        "core": (
            "软件工程",
            "软件开发",
            "程序设计",
            "代码重构",
            "系统架构",
            "微服务",
            "数据库",
            "编程语言",
            "devops",
            "持续集成",
            "continuous integration",
        ),
        "support": (
            "代码",
            "开发",
            "测试",
            "接口",
            "api",
            "部署",
            "编译器",
            "版本控制",
            "github",
            "容器",
        ),
    },
    "投资理财": {
        "core": (
            "投资理财",
            "资产配置",
            "投资组合",
            "股票",
            "基金",
            "债券",
            "估值",
            "证券",
            "房地产投资",
            "财务自由",
        ),
        "support": (
            "收益率",
            "市场",
            "仓位",
            "风险控制",
            "现金流",
            "分红",
            "利率",
            "财报",
            "牛市",
            "熊市",
        ),
    },
    "个人成长": {
        "core": (
            "个人成长",
            "自我管理",
            "时间管理",
            "职业规划",
            "习惯养成",
            "学习方法",
            "认知提升",
            "情绪管理",
            "自我反思",
        ),
        "support": (
            "复盘",
            "目标",
            "习惯",
            "专注",
            "阅读",
            "学习",
            "职业",
            "沟通",
            "效率",
        ),
    },
}


class _BodyTextParser(HTMLParser):
    """从 ENML/HTML 中提取可见正文，不把标签属性当作领域证据。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, _attrs):
        if tag.casefold() in {"script", "style"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag.casefold() in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


def full_body_text(content):
    """把完整 ENML/HTML 正文转换为领域判定使用的纯文本。"""
    parser = _BodyTextParser()
    parser.feed(content or "")
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


@dataclass(frozen=True)
class DomainAssessment:
    matched: bool
    domain: str
    score: int
    evidence: tuple
    reason: str
    competing_domain: str | None = None


def _score_domain(text, profile):
    folded = text.casefold()
    core_hits = {
        term: folded.count(term.casefold())
        for term in profile["core"]
        if term.casefold() in folded
    }
    support_hits = {
        term: folded.count(term.casefold())
        for term in profile["support"]
        if term.casefold() in folded
    }
    score = sum(3 * min(count, 3) for count in core_hits.values())
    score += sum(min(count, 2) for count in support_hits.values())
    eligible = (
        len(core_hits) >= 2
        or sum(core_hits.values()) >= 2
        or (len(core_hits) >= 1 and len(support_hits) >= 2)
        or len(support_hits) >= profile.get("support_only_min", 10**9)
    )
    evidence = tuple((*core_hits.keys(), *support_hits.keys()))
    return score, eligible, evidence


def assess_domain_relevance(domain, title, content):
    """基于完整正文主旨判断是否允许写入目标领域。

    标题只用于日志展示，不能单独构成通过条件。判定采用保守策略：
    目标领域证据不足、其他领域明显占优或领域并列时均拒绝。
    """
    if domain not in DOMAIN_PROFILES:
        raise ValueError(f"不支持的领域: {domain}")

    body = full_body_text(content)
    scores = {
        name: _score_domain(body, profile)
        for name, profile in DOMAIN_PROFILES.items()
    }
    target_score, target_eligible, target_evidence = scores[domain]
    eligible_competitors = [
        (name, score)
        for name, (score, eligible, _evidence) in scores.items()
        if name != domain and eligible
    ]
    eligible_competitors.sort(key=lambda item: (-item[1], item[0]))
    strongest = eligible_competitors[0] if eligible_competitors else None

    if not target_eligible:
        competitor = strongest[0] if strongest else None
        if competitor:
            reason = f"正文主旨更接近 {competitor}，目标领域 {domain} 证据不足"
        else:
            reason = f"完整正文中缺少足够的 {domain} 领域证据"
        return DomainAssessment(
            matched=False,
            domain=domain,
            score=target_score,
            evidence=target_evidence,
            reason=reason,
            competing_domain=competitor,
        )

    if strongest and strongest[1] >= target_score:
        relation = "并列，无法确定主领域" if strongest[1] == target_score else "更接近"
        return DomainAssessment(
            matched=False,
            domain=domain,
            score=target_score,
            evidence=target_evidence,
            reason=f"正文主旨{relation} {strongest[0]}，不写入 {domain}",
            competing_domain=strongest[0],
        )

    evidence_text = "、".join(target_evidence[:6])
    return DomainAssessment(
        matched=True,
        domain=domain,
        score=target_score,
        evidence=target_evidence,
        reason=f"正文主旨匹配 {domain}；证据：{evidence_text}",
    )


@dataclass(frozen=True)
class CandidateReview:
    metadata: object
    note: object
    assessment: DomainAssessment
    notebook_name: str


@dataclass(frozen=True)
class DomainExportResult:
    selected: tuple
    rejected: tuple
    exported_paths: tuple


def export_domain_candidates(
    note_store,
    token,
    candidates,
    notebook_map,
    target_dir,
    domain,
    limit,
):
    """逐篇拉完整正文并过领域门禁，匹配后才写 Markdown 和附件。"""
    selected = []
    rejected = []
    exported_paths = []
    selected_titles = set()

    for metadata in candidates:
        if limit is not None and len(selected) >= limit:
            break

        title_key = (getattr(metadata, "title", "") or "").strip()
        if title_key in selected_titles:
            continue

        note = note_store.getNote(
            token,
            metadata.guid,
            True,
            True,
            True,
            True,
        )
        assessment = assess_domain_relevance(
            domain=domain,
            title=getattr(note, "title", title_key),
            content=getattr(note, "content", "") or "",
        )
        notebook_name = notebook_map.get(
            getattr(metadata, "notebookGuid", ""),
            "未知笔记本",
        )
        review = CandidateReview(
            metadata=metadata,
            note=note,
            assessment=assessment,
            notebook_name=notebook_name,
        )
        if not assessment.matched:
            rejected.append(review)
            continue

        selected_titles.add(title_key)
        selected.append(review)
        exported_paths.append(
            export_note_to_obsidian(
                note,
                notebook_name=notebook_name,
                target_dir=target_dir,
                domain=domain,
            )
        )

    return DomainExportResult(
        selected=tuple(selected),
        rejected=tuple(rejected),
        exported_paths=tuple(exported_paths),
    )


def search_metadata_batches(
    note_store,
    token,
    keywords,
    since,
    max_per_keyword=250,
    until=None,
):
    result_spec = NoteStore.NotesMetadataResultSpec(
        includeTitle=True,
        includeContentLength=True,
        includeCreated=True,
        includeUpdated=True,
        includeNotebookGuid=True,
    )
    batches = []
    totals = []
    for query in build_keyword_queries(keywords, since, until=until):
        note_filter = NoteStore.NoteFilter(
            words=query,
            order=NoteSortOrder.UPDATED,
            ascending=False,
        )
        notes, total_notes = find_notes_metadata(
            note_store,
            token,
            note_filter,
            max_per_keyword,
            result_spec,
        )
        batches.append(notes)
        totals.append(total_notes)
    return batches, totals


def export_note_to_obsidian(note, notebook_name, target_dir, domain="AI"):
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    resources = extract_resources(note)
    hash_to_file = {}
    if resources:
        attachments_dir = target_dir / "_attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        hash_to_file = save_attachments(resources, str(attachments_dir))

    created = datetime.fromtimestamp(note.created / 1000)
    updated_ms = getattr(note, "updated", 0) or note.created
    updated = datetime.fromtimestamp(updated_ms / 1000)
    month_dir = target_dir / month_folder_name(created)
    month_dir.mkdir(parents=True, exist_ok=True)
    attachment_prefix = "../_attachments"
    content = note.content or ""
    is_web_clip = is_enml_clip(content) or is_web_clip_by_content(content)
    contains_media = has_en_media(content)
    if is_web_clip:
        body = html_to_md(
            content,
            hash_to_file,
            attachment_prefix=attachment_prefix,
        )
    elif contains_media:
        body = html_to_md(
            content,
            hash_to_file,
            attachment_prefix=attachment_prefix,
        )
    else:
        body = enml_to_markdown(content)
    body = simplify_markdown(body, note.title)
    extra = {
        "type": "资料",
        "domain": domain,
        "status": "待提炼",
        "tags": [],
        "review_status": "pending",
        "llm_policy": "strict",
    }

    markdown = frontmatter(
        note.title,
        notebook_name,
        note.guid,
        created,
        updated,
        extra,
        include_title=False,
    )
    markdown += f"# {note.title}\n"
    if body:
        markdown += f"\n{body}\n"
    if resources:
        markdown += make_attachments_section(
            hash_to_file,
            referenced_attachment_filenames(
                body,
                hash_to_file,
                prefix=attachment_prefix,
            ),
            prefix=attachment_prefix,
        )

    output_path = resolve_note_path(
        month_dir,
        note.title,
        note.guid,
        {},
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main():
    configure_utf8_output()

    parser = argparse.ArgumentParser(
        description="搜索最近一段时间内的相关笔记并导出到 Obsidian"
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        required=True,
        help="创建日期下限，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--until",
        type=date.fromisoformat,
        help="创建日期上限（不含当日），格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=["AI", "Agent", "人工智能"],
        help="任一匹配的关键词",
    )
    parser.add_argument(
        "--limit",
        type=export_limit,
        default=3,
        help="导出数量，使用 all 导出全部候选",
    )
    parser.add_argument(
        "--max-per-keyword",
        type=positive_int,
        default=250,
        help="每个关键词最多拉取的候选数",
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Obsidian 目标目录",
    )
    parser.add_argument(
        "--domain",
        choices=("AI", "Quant", "软件工程", "投资理财", "个人成长"),
        default="AI",
        help="精选资料所属领域（默认 AI）",
    )
    args = parser.parse_args()
    if args.until is not None and args.until <= args.since:
        parser.error("--until 必须晚于 --since")

    token, note_store_url = load_config()
    if not token or not note_store_url:
        parser.error("未找到 EVERNOTE_TOKEN 或 EVERNOTE_NOTESTORE_URL")

    note_store = create_note_store(note_store_url, token)

    batches, totals = search_metadata_batches(
        note_store,
        token,
        args.keywords,
        args.since,
        max_per_keyword=args.max_per_keyword,
        until=args.until,
    )
    for keyword, total, batch in zip(args.keywords, totals, batches):
        print(f"关键词 {keyword}: 共 {total} 条，拉取 {len(batch)} 条候选")

    candidates = rank_note_candidates(batches, args.keywords)
    if not candidates:
        print("未找到符合条件的笔记")
        return 1

    notebooks = note_store.listNotebooks(token)
    notebook_map = {notebook.guid: notebook.name for notebook in notebooks}

    result = export_domain_candidates(
        note_store=note_store,
        token=token,
        candidates=candidates,
        notebook_map=notebook_map,
        target_dir=args.target,
        domain=args.domain,
        limit=args.limit,
    )
    for review in result.rejected:
        evidence = "、".join(review.assessment.evidence[:6]) or "无"
        print(
            f"[跳过] {review.metadata.title}: "
            f"{review.assessment.reason}（正文证据：{evidence}）"
        )

    if not result.selected:
        print(f"\n没有正文主旨匹配 {args.domain} 的候选，未写入任何文章或附件")
        return 1

    print(f"\n正文审核通过并导出 {len(result.selected)} 篇：")
    for index, review in enumerate(result.selected, 1):
        metadata = review.metadata
        created = datetime.fromtimestamp(metadata.created / 1000)
        updated = datetime.fromtimestamp(metadata.updated / 1000)
        print(
            f"{index}. {metadata.title} "
            f"(创建 {created:%Y-%m-%d}，更新 {updated:%Y-%m-%d}，"
            f"笔记本 {review.notebook_name})；"
            f"{review.assessment.reason}"
        )

    finalization = finalize_knowledge_base(args.target, domain=args.domain)
    print(f"\n已导出到: {args.target}")
    for exported_path in result.exported_paths:
        print(f"- {exported_path.relative_to(args.target)}")
    print(f"- 目录索引: {finalization.index_path}")
    if finalization.errors:
        for error in finalization.errors:
            print(f"迁移失败: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
