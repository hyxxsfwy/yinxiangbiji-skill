#!/usr/bin/env python3
"""按日期区间和关键词搜索印象笔记，并导出到 Obsidian。"""

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote

import evernote.edam.notestore.NoteStore as NoteStore
from evernote.edam.type.ttypes import NoteSortOrder

try:
    from .knowledge_base import (
        extract_note_metadata,
        finalize_knowledge_base,
        month_folder_name,
    )
except ImportError:
    from knowledge_base import (
        extract_note_metadata,
        finalize_knowledge_base,
        month_folder_name,
    )

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
            "强化学习",
            "reinforcement learning",
            "rlhf",
            "rlaif",
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
            "workbuddy",
            "kimi",
            "minimax",
            "glm",
            "huggingface",
            "hugging face",
            "transformer",
            "rwkv",
            "stable diffusion",
            "diffusion model",
            "扩散模型",
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
            "attention",
            "注意力机制",
            "推理",
            "微调",
            "模型",
            "模型训练",
            "指令",
            "上下文",
            "工具调用",
            "上下文窗口",
            "mcp",
            "harness",
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
            "etf",
            "定投",
            "金融",
            "理财",
            "债券",
            "估值",
            "证券",
            "房地产投资",
            "财务自由",
            "区块链",
            "比特币",
            "bitcoin",
            "btc",
            "以太坊",
            "ethereum",
            "eth",
            "solana",
            "sol",
            "加密货币",
            "crypto",
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
EXPORT_POLICY_VERSION = 2


def domain_policy_hash():
    """返回领域词表和判定算法的稳定规则指纹。"""
    payload = {
        "version": EXPORT_POLICY_VERSION,
        "profiles": DOMAIN_PROFILES,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


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


def _term_count(text, term):
    folded_term = term.casefold()
    if re.fullmatch(r"[a-z0-9]+", folded_term):
        return len(
            re.findall(
                rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])",
                text,
            )
        )
    return text.count(folded_term)


def _score_domain(text, profile):
    folded = text.casefold()
    core_hits = {
        term: _term_count(folded, term)
        for term in profile["core"]
        if _term_count(folded, term)
    }
    support_hits = {
        term: _term_count(folded, term)
        for term in profile["support"]
        if _term_count(folded, term)
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


def assess_primary_domain(title, content, allowed_domains):
    """在全部已知领域中选择唯一主领域，并限制到任务允许范围。"""
    allowed = tuple(dict.fromkeys(allowed_domains))
    unknown = sorted(set(allowed) - set(DOMAIN_PROFILES))
    if unknown:
        raise ValueError(f"不支持的领域: {', '.join(unknown)}")
    if not allowed:
        raise ValueError("allowed_domains 不能为空")

    body = full_body_text(content)
    scores = {
        name: _score_domain(body, profile)
        for name, profile in DOMAIN_PROFILES.items()
    }
    eligible = [
        (name, score, evidence)
        for name, (score, is_eligible, evidence) in scores.items()
        if is_eligible
    ]
    eligible.sort(key=lambda item: (-item[1], item[0]))
    if not eligible:
        return DomainAssessment(
            matched=False,
            domain="",
            score=0,
            evidence=(),
            reason="完整正文中没有满足门槛的主领域",
        )

    strongest = eligible[0]
    tied = [item for item in eligible if item[1] == strongest[1]]
    if len(tied) > 1:
        names = "、".join(item[0] for item in tied)
        return DomainAssessment(
            matched=False,
            domain="",
            score=strongest[1],
            evidence=strongest[2],
            reason=f"正文领域得分并列，无法确定主领域：{names}",
        )
    if strongest[0] not in allowed:
        return DomainAssessment(
            matched=False,
            domain=strongest[0],
            score=strongest[1],
            evidence=strongest[2],
            reason=f"正文主领域为任务外的 {strongest[0]}",
            competing_domain=strongest[0],
        )

    evidence_text = "、".join(strongest[2][:6])
    return DomainAssessment(
        matched=True,
        domain=strongest[0],
        score=strongest[1],
        evidence=strongest[2],
        reason=f"正文唯一主领域为 {strongest[0]}；证据：{evidence_text}",
    )


@dataclass(frozen=True)
class CandidateReview:
    metadata: object
    assessment: DomainAssessment
    notebook_name: str


@dataclass(frozen=True)
class DomainExportResult:
    selected: tuple
    rejected: tuple
    already_exported: tuple
    previously_rejected: tuple
    exported_paths: tuple


def discover_exported_versions(target_dir):
    """读取目标目录中已成功导出的 GUID 及其更新时间（秒）。"""
    target_dir = Path(target_dir)
    if not target_dir.exists():
        return {}

    versions = {}
    for markdown_path in target_dir.rglob("*.md"):
        if markdown_path.name == "目录索引.md":
            continue
        try:
            metadata = extract_note_metadata(markdown_path)
        except (OSError, UnicodeError, ValueError):
            continue
        updated_second = int(metadata.updated.timestamp())
        versions[metadata.guid] = max(
            versions.get(metadata.guid, 0),
            updated_second,
        )
    return versions


def export_state_path(target_dir, domain):
    """为目标目录生成不进入 Obsidian 的本地续跑状态路径。"""
    target_key = str(Path(target_dir).resolve()).casefold()
    digest = hashlib.sha256(target_key.encode("utf-8")).hexdigest()[:16]
    safe_domain = re.sub(r"[^\w-]+", "_", domain)
    return (
        Path(__file__).resolve().parent.parent
        / ".state"
        / f"export-{safe_domain}-{digest}.json"
    )


def _load_export_state(state_file):
    if state_file is None or not Path(state_file).is_file():
        return {}
    try:
        payload = json.loads(Path(state_file).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if payload.get("version") != EXPORT_POLICY_VERSION:
        return {}
    reviews = payload.get("reviews", {})
    return reviews if isinstance(reviews, dict) else {}


def _save_export_state(state_file, reviews):
    if state_file is None:
        return
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_suffix(state_file.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {"version": EXPORT_POLICY_VERSION, "reviews": reviews},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(state_file)


def markdown_attachments_complete(markdown_path):
    """确认导出 Markdown 引用的图片和附件均可解析。"""
    markdown_path = Path(markdown_path)
    if not markdown_path.is_file():
        return False
    try:
        try:
            from .restructure_obsidian_vault import iter_markdown_references
        except ImportError:
            from restructure_obsidian_vault import iter_markdown_references

        markdown = markdown_path.read_text(encoding="utf-8")
        for reference in iter_markdown_references(markdown):
            raw_target = reference.target.strip()
            if not raw_target or raw_target.lower().startswith(
                ("http:", "https:", "mailto:", "data:")
            ):
                continue
            normalized = raw_target.replace("\\", "/")
            if not reference.is_image and "_attachments/" not in normalized:
                continue
            if reference.is_wikilink:
                raw_target = raw_target.split("|", 1)[0]
            raw_target = raw_target.split("#", 1)[0].strip().strip("<>")
            if not raw_target:
                continue
            if not (
                markdown_path.parent / unquote(raw_target)
            ).resolve().is_file():
                return False
    except (OSError, UnicodeError):
        return False
    return True


def export_domain_candidates(
    note_store,
    token,
    candidates,
    notebook_map,
    target_dir,
    domain,
    limit,
    state_file=None,
    policy_hash=None,
):
    """逐篇拉完整正文并过领域门禁，匹配后才写 Markdown 和附件。"""
    policy_hash = policy_hash or domain_policy_hash()
    selected = []
    rejected = []
    already_exported = []
    previously_rejected = []
    exported_paths = []
    selected_titles = set()
    exported_versions = discover_exported_versions(target_dir)
    review_state = _load_export_state(state_file)

    for metadata in candidates:
        completed_count = len(selected) + len(already_exported)
        if limit is not None and completed_count >= limit:
            break

        title_key = (getattr(metadata, "title", "") or "").strip()
        if title_key in selected_titles:
            continue
        guid = str(getattr(metadata, "guid", "") or "")
        updated_second = int(
            (getattr(metadata, "updated", 0) or 0) / 1000
        )
        previous = review_state.get(guid, {})
        previous_path = previous.get("path")
        resolved_previous_path = None
        if previous_path:
            try:
                resolved_previous_path = (
                    Path(target_dir) / Path(*Path(previous_path).parts)
                ).resolve()
                resolved_previous_path.relative_to(
                    Path(target_dir).resolve()
                )
            except (OSError, ValueError):
                resolved_previous_path = None
        if (
            exported_versions.get(guid) == updated_second
            and previous.get("updated") == updated_second
            and previous.get("domain") == domain
            and previous.get("outcome") == "accepted"
            and previous.get("policy_hash") == policy_hash
            and resolved_previous_path is not None
            and markdown_attachments_complete(resolved_previous_path)
        ):
            selected_titles.add(title_key)
            already_exported.append(metadata)
            continue
        if (
            previous.get("updated") == updated_second
            and previous.get("domain") == domain
            and previous.get("outcome") == "rejected"
            and previous.get("policy_hash") == policy_hash
        ):
            previously_rejected.append(metadata)
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
            assessment=assessment,
            notebook_name=notebook_name,
        )
        if not assessment.matched:
            rejected.append(review)
            review_state[guid] = {
                "updated": updated_second,
                "domain": domain,
                "outcome": "rejected",
                "policy_hash": policy_hash,
                "reason": assessment.reason,
                "evidence": list(assessment.evidence[:12]),
            }
            _save_export_state(state_file, review_state)
            continue

        selected_titles.add(title_key)
        selected.append(review)
        exported_path = export_note_to_obsidian(
            note,
            notebook_name=notebook_name,
            target_dir=target_dir,
            domain=domain,
        )
        exported_paths.append(exported_path)
        review_state[guid] = {
            "updated": updated_second,
            "domain": domain,
            "outcome": "accepted",
            "policy_hash": policy_hash,
            "reason": assessment.reason,
            "evidence": list(assessment.evidence[:12]),
            "path": exported_path.relative_to(target_dir).as_posix(),
        }
        _save_export_state(state_file, review_state)

    return DomainExportResult(
        selected=tuple(selected),
        rejected=tuple(rejected),
        already_exported=tuple(already_exported),
        previously_rejected=tuple(previously_rejected),
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
        "source_updated_ms": updated_ms,
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
        state_file=export_state_path(args.target, args.domain),
    )
    for review in result.rejected:
        evidence = "、".join(review.assessment.evidence[:6]) or "无"
        print(
            f"[跳过] {review.metadata.title}: "
            f"{review.assessment.reason}（正文证据：{evidence}）"
        )

    if result.already_exported:
        print(
            f"\n续跑识别到 {len(result.already_exported)} 篇未变化的"
            "已导出笔记，已跳过重复正文和资源请求"
        )
    if result.previously_rejected:
        print(
            f"续跑识别到 {len(result.previously_rejected)} 篇未变化的"
            "已拒绝候选，已跳过重复正文请求"
        )

    if not result.selected and not result.already_exported:
        print(f"\n没有正文主旨匹配 {args.domain} 的候选，未写入任何文章或附件")
        return 1

    print(f"\n本次正文审核通过并新增或更新 {len(result.selected)} 篇：")
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
