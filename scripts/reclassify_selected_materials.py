"""重新审阅并整理 Obsidian 精选资料。"""

import argparse
from dataclasses import dataclass
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from urllib.parse import quote, unquote
import zipfile

try:
    from scripts.curate_selected_materials import (
        AUTO_LINKS_END,
        AUTO_LINKS_SECTION,
        AUTO_LINKS_START,
    )
    from scripts.knowledge_base import (
        _split_frontmatter,
        extract_note_metadata_from_text,
        iter_indexable_note_paths,
        write_knowledge_base_index,
    )
    from scripts.runtime import configure_utf8_output, load_vault_root
    from scripts.vault_state import (
        StateLockConflict,
        VaultStatePaths,
        require_path_within_vault,
        runtime_write_lock,
    )
except ModuleNotFoundError:
    from curate_selected_materials import (
        AUTO_LINKS_END,
        AUTO_LINKS_SECTION,
        AUTO_LINKS_START,
    )
    from knowledge_base import (
        _split_frontmatter,
        extract_note_metadata_from_text,
        iter_indexable_note_paths,
        write_knowledge_base_index,
    )
    from runtime import configure_utf8_output, load_vault_root
    from vault_state import (
        StateLockConflict,
        VaultStatePaths,
        require_path_within_vault,
        runtime_write_lock,
    )


SELECTED_ROOT = "30_精选资料"
INDEX_FILENAME = "目录索引.md"
_ASSET_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_WIKILINK = re.compile(r"\[\[([^|\]]+)(?:\|[^\]]*)?\]\]")
_MONTH_DIRECTORY = re.compile(r"^\d{4}年(?:0[1-9]|1[0-2])月$")
_REMOTE_TARGET = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CLASSIFICATION_POLICY_VERSION = 12

DOMAIN_PROFILES = {
    "AI": {
        "core": (
            "ai", "人工智能", "生成式ai", "大模型", "大语言模型", "llm",
            "机器学习", "深度学习", "神经网络", "强化学习", "智能体",
            "ai agent", "rag", "chatgpt", "openai", "claude", "deepseek",
            "gpt", "qwen", "codex", "transformer", "扩散模型",
            "开源模型", "模型推理", "参数规模",
            "agent", "agent skills", "skill", "本体论", "推理技术",
            "openclaw", "workbuddy", "coding agent",
            "anthropic", "glm", "kimi", "minimax", "huggingface",
            "hugging face", "rwkv", "rlhf",
            "ai时代", "ai创业", "vibe coding", "文生视频", "视频生成",
            "自动出视频", "吴恩达", "andrew ng", "loop engineering",
        ),
        "support": (
            "agent", "prompt", "提示词", "token", "embedding", "向量检索",
            "微调", "模型训练", "mcp", "harness",
        ),
    },
    "Quant": {
        "core": (
            "量化交易", "量化投资", "量化研究", "因子投资", "多因子",
            "回测", "高频交易", "algorithmic trading", "quantitative finance",
            "交易策略", "技术交易", "量化金融",
            "止损", "交易系统", "历史行情",
            "交易法", "短线交易", "交易信号", "量化策略",
            "quant", "因子", "日内交易", "截面反转", "反转策略",
            "高频", "做市", "量化分析", "量化分析师",
        ),
        "support": (
            "alpha", "因子", "交易信号", "最大回撤", "夏普", "时间序列",
            "策略收益", "组合优化", "实盘", "动量", "ea", "缠论",
        ),
    },
    "软件工程": {
        "core": (
            "软件工程", "软件开发", "程序设计", "代码重构", "系统架构",
            "微服务", "编程语言", "devops", "持续集成", "开源社区",
            "linux 内核", "c++", "javascript", "数据库", "kubernetes",
            "rocketmq", "kafka", "electron", "程序员", "开源项目",
            "postgresql", "mysql", "bug", "源码", "编程", "软件",
            "好产品", "产品开发", "需求验证", "产品体验", "技术评估",
            "开发排期", "项目管理",
        ),
        "support": (
            "代码", "开发", "测试", "接口", "api", "部署", "编译器",
            "版本维护", "版本控制", "github", "容器",
            "bug", "windows", "源码", "框架",
        ),
    },
    "投资理财": {
        "core": (
            "投资理财", "资产配置", "投资组合", "股票", "证券", "基金",
            "etf", "定投", "金融", "理财", "债券", "财务自由",
            "区块链", "比特币", "加密货币",
            "币圈", "defi", "美股", "a股", "白银", "黄金", "挖矿",
            "储蓄", "存钱", "个人理财",
            "港股", "港卡", "现金流", "交易商", "银行卡", "信用卡",
            "以太坊", "ethereum", "eth", "solana", "sol", "期权",
        ),
        "support": (
            "收益率", "仓位", "现金流", "分红", "利率", "财报", "牛市",
            "熊市", "房贷", "贷款", "估值", "交易", "爆仓", "银行",
            "预算",
        ),
    },
    "知识管理": {
        "core": (
            "知识管理", "个人知识管理", "第二大脑", "双向链接", "卡片笔记",
            "zettelkasten", "obsidian", "notion", "pkm", "gtd",
        ),
        "support": (
            "笔记系统", "知识库", "信息整理", "标签体系", "收件箱",
        ),
    },
    "健康医学": {
        "core": (
            "健康医学", "临床", "疾病", "诊断", "治疗", "患者", "医生",
            "医院", "药物", "癌症", "肿瘤", "血压", "血糖", "免疫",
            "公共卫生", "疾控", "医学研究",
            "猝死", "基因组", "医疗", "护士",
            "bmi", "代谢", "体重", "脂肪",
            "减肥", "减重", "盆底肌", "卵巢", "疲劳", "睡眠", "心血管",
            "脑梗", "中风", "抑郁", "抑郁症",
        ),
        "support": (
            "健康", "症状", "手术", "感染", "营养", "睡眠", "心脏",
            "大脑", "寿命",
        ),
    },
    "中医": {
        "core": (
            "中医", "中药", "经络", "针灸", "穴位", "方剂", "辨证论治",
            "阴阳", "气血", "脏腑", "黄帝内经", "五运六气", "气机",
            "寒湿", "疏肝", "舒肝", "散结",
        ),
        "support": ("调理", "体质", "养生", "脉象", "舌象"),
    },
    "两性情感": {
        "core": (
            "两性", "婚姻", "伴侣", "夫妻", "恋爱", "亲密关系", "情感关系",
            "婚恋", "离婚", "彩礼", "婚房", "婆媳", "择偶",
            "出轨", "老公", "老婆", "丈夫", "妻子", "男友", "女友",
            "媳妇", "结婚", "小三",
            "关系冲突", "心理边界", "人际关系",
            "亲亲抱抱", "女权", "男权", "性格", "课题分离",
        ),
        "support": (
            "爱情", "相亲", "家庭关系", "男性责任", "女性", "男人", "女人",
            "沟通", "情绪",
        ),
    },
    "个人成长": {
        "core": (
            "个人成长", "自我管理", "时间管理", "职业规划", "习惯养成",
            "学习方法", "认知提升", "情绪管理", "自我反思",
            "人生选择", "前额叶", "拖延", "生活方式", "自我提升",
            "工作倦怠", "辞职", "失业", "裁员", "跳槽", "找工作",
            "职业转型", "离职", "招聘", "学历", "资历", "人才成长",
        ),
        "support": (
            "复盘", "目标管理", "专注", "阅读", "学习", "职业", "沟通",
            "效率",
        ),
    },
}
MANAGED_DOMAINS = tuple(DOMAIN_PROFILES)
SPECIFIC_DOMAINS = {
    "Quant",
    "投资理财",
    "中医",
    "两性情感",
    "知识管理",
}
FORCED_SPECIFIC_TITLE_PATTERNS = (
    (
        "Quant",
        re.compile(
            r"量化(?:研究|分析|策略|交易|投资|因子)|AI量化",
            re.I,
        ),
    ),
    (
        "中医",
        re.compile(r"中医|中药|倪海厦|徐文兵|黄帝内经|五运六气"),
    ),
    (
        "知识管理",
        re.compile(r"Obsidian|PKM|GTD|卡片笔记|第二大脑", re.I),
    ),
)
TITLE_FALLBACKS = (
    ("Quant", re.compile(
        r"量化|TDXQuant|因子|回测|缠论|交易策略|交易系统|"
        r"短线交易|技术交易|实盘|日内|截面反转|高频|做市|"
        r"(?=.*交易者)(?=.*时间周期)",
        re.I,
    )),
    ("知识管理", re.compile(r"知识库|Obsidian|PKM|GTD|卡片笔记", re.I)),
    ("投资理财", re.compile(
        r"币安|币圈|港股|港卡|牛市|熊市|现金流|房贷|贷款|银行|万事达|"
        r"VISA|财富自由|OKE|V神|以太坊|比特币|交易商|股票|证券|基金|"
        r"美股|A股|黄金(?!时代)|白银|理财|以太坊|Ethereum|ETH|SOL|期权",
        re.I,
    )),
    ("中医", re.compile(
        r"中医|中药|倪海厦|徐文兵|针灸|穴位|气血|灸|药酒|"
        r"黄帝内经|五运六气|气机|寒湿|疏肝|舒肝|散结"
    )),
    ("健康医学", re.compile(
        r"癌|肺|基因|细胞|免疫|病毒|医生|医学|医疗|医院|猝死|睡眠|"
        r"体重|减肥|脂肪|代谢|卵巢|盆底肌|心脏|健康|器官|犯困|"
        r"脑梗|中风|抑郁",
    )),
    ("两性情感", re.compile(
        r"婚|妻|夫|老公|老婆|伴侣|恋爱|女友|男友|小三|出轨|两性|"
        r"情感|亲密关系|相亲|女权|男权",
    )),
    ("个人成长", re.compile(
        r"个人成长|人生选择|自我|前额叶|拖延|生活方式|内卷|职业规划|"
        r"失业|裁员|跳槽|找工作|辞职|离职|工作倦怠|职业转型|"
        r"招聘|学历|资历|人才成长|沟通",
    )),
    ("软件工程", re.compile(
        r"C\+\+|JavaScript|PostgreSQL|MySQL|Win11|Windows|BUG|GitHub|"
        r"代码|编程|数据库|开发者|SSD|硬盘|软件|架构师|开源协议|API",
        re.I,
    )),
    ("AI", re.compile(
        r"(?<![A-Za-z0-9])(?:AI|LLM|GPT\d*|Qwen\d*(?:\.\d+)?|"
        r"GLM(?:-\d+(?:\.\d+)?)?|Kimi|Claude|Anthropic|"
        r"Agent|Skills?|Cursor|Qoder|OpenClaw|Hermes|LightGBM|YOLO|RAG)"
        r"(?![A-Za-z0-9])|"
        r"大模型|机器学习|开源模型|本体论|推理技术|模型|AI时代|AI创业|"
        r"Vibe Coding|文生视频|视频生成|自动出视频|吴恩达|Andrew Ng|"
        r"Loop Engineering",
        re.I,
    )),
)


@dataclass(frozen=True)
class Classification:
    decision: str
    target_domain: str | None
    scores: dict[str, int]
    evidence: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class AssetReference:
    raw_target: str
    source: Path


@dataclass(frozen=True)
class PlannedAsset:
    source: Path
    destination: Path


@dataclass(frozen=True)
class PlannedDocument:
    source: Path
    destination: Path
    rendered: str
    remove_source: bool


@dataclass(frozen=True)
class ReviewPlan:
    vault: Path
    selected: Path
    trash_root: Path
    moves: dict[Path, str]
    trash: tuple[Path, ...]
    links: dict[Path, tuple[Path, ...]]
    final_relative_by_source: dict[Path, Path]
    documents: tuple[PlannedDocument, ...]
    assets: tuple[PlannedAsset, ...]
    index_roots: tuple[Path, ...]
    snapshot_sources: tuple[Path, ...]


class ReviewExecutionError(RuntimeError):
    """业务执行失败且已回滚，保留快照位置供报告使用。"""

    def __init__(self, message, snapshot):
        super().__init__(message)
        self.snapshot = snapshot


def _term_count(text, term):
    folded = text.casefold()
    needle = term.casefold()
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._-]*", needle):
        if needle in {"gpt", "qwen", "glm"}:
            return len(
                re.findall(
                    rf"(?<![a-z0-9]){re.escape(needle)}(?=\d|[^a-z0-9]|$)",
                    folded,
                )
            )
        return len(
            re.findall(
                rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])",
                folded,
            )
        )
    count = folded.count(needle)
    if needle == "基金":
        count -= folded.count("基金会")
    return max(count, 0)


def _score_profile(title, body, profile):
    score = 0
    evidence = []
    for weight, field in ((5, title), (1, body)):
        for term in profile["core"]:
            count = min(_term_count(field, term), 3)
            if count:
                score += weight * 4 * count
                evidence.append(term)
        for term in profile["support"]:
            count = min(_term_count(field, term), 2)
            if count:
                score += weight * count
                evidence.append(term)
    return score, tuple(dict.fromkeys(evidence))


def _fallback_classification(title, current_domain, scores, evidence):
    fallback_domain = next(
        (
            domain
            for domain, pattern in TITLE_FALLBACKS
            if pattern.search(title)
        ),
        None,
    )
    if fallback_domain == current_domain:
        return Classification("keep", current_domain, scores, evidence)
    if fallback_domain is not None:
        return Classification("move", fallback_domain, scores, evidence)
    return Classification("unclassified", None, scores, evidence)


def _title_fallback_domains(title):
    return tuple(
        domain
        for domain, pattern in TITLE_FALLBACKS
        if pattern.search(title)
    )


def classify_document(title, body, current_domain):
    scored = {
        domain: _score_profile(title, body, profile)
        for domain, profile in DOMAIN_PROFILES.items()
    }
    scores = {domain: value[0] for domain, value in scored.items()}
    evidence = {domain: value[1] for domain, value in scored.items()}
    title_scored = {
        domain: _score_profile(title, "", profile)
        for domain, profile in DOMAIN_PROFILES.items()
    }
    title_scores = {
        domain: value[0] for domain, value in title_scored.items()
    }
    current_title_score = title_scores.get(current_domain, 0)
    fallback_domains = _title_fallback_domains(title)
    forced_specific_title = next(
        (
            domain
            for domain, pattern in FORCED_SPECIFIC_TITLE_PATTERNS
            if pattern.search(title)
        ),
        None,
    )
    has_competing_specific_title = any(
        domain in SPECIFIC_DOMAINS and domain != current_domain
        for domain in fallback_domains
    )
    if (
        forced_specific_title in {None, current_domain}
        and current_domain in fallback_domains
        and (
            len(fallback_domains) == 1
            or current_domain in SPECIFIC_DOMAINS
            or (
                not has_competing_specific_title
                and current_title_score
                >= max(title_scores.values(), default=0) - 5
            )
        )
    ):
        return Classification("keep", current_domain, scores, evidence)
    if (
        forced_specific_title in {None, current_domain}
        and current_domain in SPECIFIC_DOMAINS
        and current_title_score >= 8
    ):
        return Classification("keep", current_domain, scores, evidence)
    if (
        forced_specific_title in {None, current_domain}
        and current_title_score >= 8
        and current_title_score == max(title_scores.values(), default=0)
        and (
            current_domain in SPECIFIC_DOMAINS
            or not has_competing_specific_title
        )
    ):
        return Classification("keep", current_domain, scores, evidence)
    if forced_specific_title is not None:
        target_domain = forced_specific_title
        target_score = scores[target_domain]
    elif max(title_scores.values(), default=0) >= 8:
        target_domain, target_score = max(
            scores.items(),
            key=lambda item: (
                title_scores[item[0]],
                item[1],
                item[0],
            ),
        )
    else:
        target_domain, target_score = max(
            scores.items(),
            key=lambda item: (item[1], item[0]),
        )
    target_has_core = any(
        term in evidence[target_domain]
        for term in DOMAIN_PROFILES[target_domain]["core"]
    )
    if target_score < 8 or not target_has_core:
        return _fallback_classification(
            title, current_domain, scores, evidence
        )
    if target_domain == current_domain:
        return Classification("keep", current_domain, scores, evidence)
    if forced_specific_title is not None:
        return Classification("move", target_domain, scores, evidence)
    current_score = scores.get(current_domain, 0)
    title_evidence = title_scored[target_domain][1]
    title_has_core = any(
        term in title_evidence
        for term in DOMAIN_PROFILES[target_domain]["core"]
    ) or target_domain in fallback_domains
    body_core_hits = sum(
        term in evidence[target_domain]
        for term in DOMAIN_PROFILES[target_domain]["core"]
    )
    if (
        not title_has_core
        and current_score >= 8
        and target_score < current_score + 8
    ):
        return Classification("keep", current_domain, scores, evidence)
    if not title_has_core and body_core_hits < 3:
        if current_score >= 8:
            return Classification("keep", current_domain, scores, evidence)
        return _fallback_classification(
            title, current_domain, scores, evidence
        )
    if target_score < current_score + 4:
        return Classification("ambiguous", None, scores, evidence)
    return Classification("move", target_domain, scores, evidence)


def _update_domain(markdown, domain):
    newline = "\r\n" if "\r\n" in markdown else "\n"
    lines = markdown.replace("\r\n", "\n").split("\n")
    if not lines or lines[0] != "---":
        raise ValueError("文档缺少 domain frontmatter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("文档 frontmatter 未闭合") from exc
    domain_lines = []
    for index, line in enumerate(lines[1:closing], 1):
        if line.startswith((" ", "\t")):
            continue
        field, separator, value = line.partition(":")
        if separator and field == "domain":
            if value.strip() in {"|", ">"}:
                raise ValueError("domain frontmatter 必须是普通标量")
            domain_lines.append(index)
    if len(domain_lines) != 1:
        raise ValueError("文档必须包含唯一 domain frontmatter")
    lines[domain_lines[0]] = f'domain: "{domain}"'
    return newline.join(lines)


def _require_domain_root(parent, domain, vault, description):
    """要求领域根解析后仍保持 parent/domain 的规范身份。"""
    parent = Path(parent)
    expected = parent / domain
    resolved = require_path_within_vault(
        expected,
        vault,
        description,
        allowed_root=parent,
    )
    if resolved != expected:
        raise ValueError(
            f"{description}解析后必须保持规范领域路径: {expected}"
        )
    return resolved


def _validated_vault_roots(vault):
    vault = Path(vault).expanduser().resolve()
    obsidian = require_path_within_vault(
        vault / ".obsidian",
        vault,
        "Obsidian 配置目录",
    )
    if not obsidian.is_dir():
        raise ValueError(f"目标不是 Obsidian vault: {vault}")
    selected = require_path_within_vault(
        vault / SELECTED_ROOT,
        vault,
        "精选资料根目录",
    )
    trash_root = require_path_within_vault(
        vault / "99_废纸篓" / SELECTED_ROOT,
        vault,
        "精选资料废纸篓根目录",
    )
    for domain in MANAGED_DOMAINS:
        domain_root = _require_domain_root(
            selected,
            domain,
            vault,
            f"{domain} 领域目录",
        )
        require_path_within_vault(
            domain_root / "_attachments",
            vault,
            f"{domain} 来源附件目录",
            allowed_root=domain_root,
        )
        trash_domain = _require_domain_root(
            trash_root,
            domain,
            vault,
            f"{domain} 废纸篓目录",
        )
        require_path_within_vault(
            trash_domain / "_attachments",
            vault,
            f"{domain} 废纸篓附件目录",
            allowed_root=trash_domain,
        )
    return vault, selected, trash_root


def _canonical_asset_target(destination, fragment=""):
    encoded = quote(destination.name, safe="-._~")
    target = f"../_attachments/{encoded}"
    return f"{target}#{fragment}" if fragment else target


def _referenced_assets(note, vault, selected, domain):
    domain_root = _require_domain_root(
        selected,
        domain,
        vault,
        f"{domain} 来源领域目录",
    )
    note = require_path_within_vault(
        note,
        vault,
        "附件所属文档",
        allowed_root=domain_root,
    )
    attachment_root = require_path_within_vault(
        domain_root / "_attachments",
        vault,
        f"{domain} 来源附件目录",
        allowed_root=domain_root,
    )
    text = note.read_text(encoding="utf-8")
    for raw_target in _ASSET_LINK.findall(text):
        stripped = raw_target.strip().strip("<>")
        raw_path, separator, fragment = stripped.partition("#")
        target = unquote(raw_path)
        if not target or target.lower().endswith(".md"):
            continue
        if "://" in target or (
            _REMOTE_TARGET.match(target)
            and not Path(target).is_absolute()
        ):
            continue
        target_path = Path(target)
        if target_path.is_absolute():
            raise ValueError(f"附件不允许绝对路径: {raw_target}")
        try:
            path = require_path_within_vault(
                note.parent / target_path,
                vault,
                "附件",
                allowed_root=attachment_root,
            )
        except ValueError as exc:
            raise ValueError(
                f"附件超出受管目录: {raw_target}"
            ) from exc
        if not path.is_file():
            raise FileNotFoundError(f"附件不存在: {path}")
        yield AssetReference(
            raw_target=raw_target,
            source=path,
        )


def _asset_destination_payload(destination, planned_assets):
    payloads = []
    if destination.exists():
        payloads.append(destination.read_bytes())
    planned = planned_assets.get(destination)
    if planned is not None:
        payloads.append(planned.source.read_bytes())
    if len(set(payloads)) > 1:
        raise FileExistsError(destination)
    return payloads[0] if payloads else None


def _collision_safe_asset_destination(
    asset,
    target_dir,
    planned_assets=None,
):
    asset = Path(asset)
    target_dir = Path(target_dir)
    if planned_assets is None:
        planned_assets = {}
    destination = target_dir / asset.name
    payload = asset.read_bytes()
    destination_payload = _asset_destination_payload(
        destination,
        planned_assets,
    )
    if destination_payload is None or destination_payload == payload:
        return destination
    digest = hashlib.sha256(payload).hexdigest()[:12]
    destination = target_dir / f"{asset.stem}_{digest}{asset.suffix}"
    destination_payload = _asset_destination_payload(
        destination,
        planned_assets,
    )
    if destination_payload is not None and destination_payload != payload:
        raise FileExistsError(destination)
    return destination


def _rewrite_asset_references(markdown, renames):
    def replace(match):
        raw_target = match.group(1)
        replacement = renames.get(raw_target)
        if replacement is None:
            return match.group(0)
        return match.group(0).replace(raw_target, replacement, 1)

    return _ASSET_LINK.sub(replace, markdown)


def _render_links(markdown, targets):
    base = AUTO_LINKS_SECTION.sub("", markdown)
    if not targets:
        return base
    lines = []
    for target in sorted(targets, key=lambda item: item.as_posix()):
        vault_target = PurePosixPath(SELECTED_ROOT, *target.with_suffix("").parts)
        alias = target.stem.replace("|", "｜").replace("]", "］")
        lines.append(f"- [[{vault_target.as_posix()}|{alias}]]")
    section = "\n".join(
        (
            "## 相关笔记",
            "",
            AUTO_LINKS_START,
            *lines,
            AUTO_LINKS_END,
            "",
        )
    )
    separator = "\n" if base.endswith(("\n", "\r")) else "\n\n"
    return base + separator + section


def _is_within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


def _validate_target_domain(target_domain):
    if not isinstance(target_domain, str) or target_domain not in DOMAIN_PROFILES:
        raise ValueError("move 目标领域必须是已知领域")
    return target_domain


def _validate_domain_tree(vault, selected, domain_root):
    if not domain_root.exists():
        return
    domain_root = _require_domain_root(
        selected,
        domain_root.name,
        vault,
        f"{domain_root.name} 领域目录",
    )
    for child in domain_root.iterdir():
        require_path_within_vault(
            child,
            vault,
            f"{domain_root.name} 领域子路径",
            allowed_root=domain_root,
        )
        if not child.is_dir() or not _MONTH_DIRECTORY.fullmatch(child.name):
            continue
        for note in child.glob("*.md"):
            require_path_within_vault(
                note,
                vault,
                "领域资料",
                allowed_root=domain_root,
            )


def _asset_target_plan(
    reference,
    target_root,
    vault,
    allowed_root,
    planned_assets,
):
    destination = _collision_safe_asset_destination(
        reference.source,
        target_root,
        planned_assets,
    )
    destination = require_path_within_vault(
        destination,
        vault,
        "附件目标",
        allowed_root=allowed_root,
    )
    stripped = reference.raw_target.strip().strip("<>")
    _, separator, fragment = stripped.partition("#")
    rewritten = _canonical_asset_target(
        destination,
        fragment if separator else "",
    )
    return PlannedAsset(reference.source, destination), rewritten


def _validate_final_index_inputs(plan):
    rendered_by_destination = {
        document.destination: document.rendered
        for document in plan.documents
        if _is_within(document.destination, plan.selected)
    }
    removed = {
        document.source
        for document in plan.documents
        if document.remove_source and document.source != document.destination
    }
    for domain, domain_root in zip(MANAGED_DOMAINS, plan.index_roots):
        candidates = {}
        if domain_root.is_dir():
            for path in iter_indexable_note_paths(domain_root, domain):
                path = require_path_within_vault(
                    path,
                    plan.vault,
                    "索引资料",
                    allowed_root=domain_root,
                )
                if path not in removed:
                    candidates[path] = path.read_text(encoding="utf-8")
        for destination, rendered in rendered_by_destination.items():
            try:
                relative = destination.relative_to(domain_root)
            except ValueError:
                continue
            if (
                len(relative.parts) != 2
                or not _MONTH_DIRECTORY.fullmatch(relative.parts[0])
                or destination.suffix.casefold() != ".md"
            ):
                continue
            fields, _ = _split_frontmatter(rendered)
            if fields.get("type") == "资料" and fields.get("domain") == domain:
                candidates[destination] = rendered
            else:
                candidates.pop(destination, None)
        for path, rendered in candidates.items():
            extract_note_metadata_from_text(path, rendered)


def _iter_managed_notes(vault, selected):
    for domain in MANAGED_DOMAINS:
        domain_root = _require_domain_root(
            selected,
            domain,
            vault,
            f"{domain} 领域目录",
        )
        _validate_domain_tree(vault, selected, domain_root)
        if not domain_root.is_dir():
            continue
        for month_dir in domain_root.iterdir():
            if (
                not month_dir.is_dir()
                or not _MONTH_DIRECTORY.fullmatch(month_dir.name)
            ):
                continue
            for note in sorted(month_dir.glob("*.md")):
                if note.name == INDEX_FILENAME:
                    continue
                yield require_path_within_vault(
                    note,
                    vault,
                    "受管资料",
                    allowed_root=domain_root,
                )


def _prepare_review_plan(vault, moves, trash, links):
    decisions = _normalize_review_decisions(moves, trash, links)
    moves = decisions["moves"]
    trash = decisions["trash"]
    links = decisions["links"]
    vault, selected, trash_root = _validated_vault_roots(vault)
    if not selected.is_dir():
        raise FileNotFoundError(f"精选资料根目录不存在: {selected}")
    for domain in MANAGED_DOMAINS:
        _validate_domain_tree(
            vault,
            selected,
            selected / domain,
        )

    final_relative_by_source = {}
    destinations = {}
    documents = {}
    assets_by_destination = {}
    for relative, target_domain in moves.items():
        source_domain = relative.parts[0]
        source_domain_root = _require_domain_root(
            selected,
            source_domain,
            vault,
            f"{source_domain} 移动来源领域目录",
        )
        source = require_path_within_vault(
            selected / relative,
            vault,
            "移动来源",
            allowed_root=source_domain_root,
        )
        if not source.is_file():
            raise FileNotFoundError(source)
        if _frontmatter_domain(source) != source_domain:
            raise ValueError(f"移动来源 domain 与路径不匹配: {relative}")
        target_domain_root = _require_domain_root(
            selected,
            target_domain,
            vault,
            f"{target_domain} 移动目标领域目录",
        )
        destination = require_path_within_vault(
            _review_move_destination(vault, relative, target_domain),
            vault,
            "移动目标",
            allowed_root=target_domain_root,
        )
        if destination.exists():
            raise FileExistsError(destination)
        if destination in destinations:
            raise ValueError(
                "多个 move 不能规划到同一目标: "
                f"{relative} 与 {destinations[destination]}"
            )
        destinations[destination] = relative
        final_relative_by_source[relative] = destination.relative_to(selected)
        target_root = require_path_within_vault(
            target_domain_root / "_attachments",
            vault,
            f"{target_domain} 目标附件目录",
            allowed_root=target_domain_root,
        )
        renames = {}
        for reference in _referenced_assets(
            source,
            vault,
            selected,
            source_domain,
        ):
            planned_asset, rewritten = _asset_target_plan(
                reference,
                target_root,
                vault,
                target_root,
                assets_by_destination,
            )
            existing = assets_by_destination.get(planned_asset.destination)
            if (
                existing is not None
                and existing.source.read_bytes()
                != planned_asset.source.read_bytes()
            ):
                raise FileExistsError(planned_asset.destination)
            assets_by_destination[planned_asset.destination] = planned_asset
            renames[reference.raw_target] = rewritten
        rendered = _update_domain(
            source.read_text(encoding="utf-8"),
            target_domain,
        )
        rendered = _rewrite_asset_references(rendered, renames)
        documents[relative] = PlannedDocument(
            source=source,
            destination=destination,
            rendered=rendered,
            remove_source=True,
        )

    for relative in trash:
        domain = relative.parts[0]
        source_domain_root = _require_domain_root(
            selected,
            domain,
            vault,
            f"{domain} 废纸篓来源领域目录",
        )
        source = require_path_within_vault(
            selected / relative,
            vault,
            "废纸篓来源",
            allowed_root=source_domain_root,
        )
        if not source.is_file():
            raise FileNotFoundError(source)
        trash_domain_root = _require_domain_root(
            trash_root,
            domain,
            vault,
            f"{domain} 废纸篓目标领域目录",
        )
        destination = require_path_within_vault(
            _review_trash_destination(vault, relative),
            vault,
            "废纸篓目标",
            allowed_root=trash_domain_root,
        )
        if destination.exists():
            raise FileExistsError(destination)
        target_root = require_path_within_vault(
            trash_domain_root / "_attachments",
            vault,
            f"{domain} 废纸篓附件目录",
            allowed_root=trash_domain_root,
        )
        renames = {}
        for reference in _referenced_assets(
            source,
            vault,
            selected,
            domain,
        ):
            planned_asset, rewritten = _asset_target_plan(
                reference,
                target_root,
                vault,
                target_root,
                assets_by_destination,
            )
            existing = assets_by_destination.get(planned_asset.destination)
            if (
                existing is not None
                and existing.source.read_bytes()
                != planned_asset.source.read_bytes()
            ):
                raise FileExistsError(planned_asset.destination)
            assets_by_destination[planned_asset.destination] = planned_asset
            renames[reference.raw_target] = rewritten
        documents[relative] = PlannedDocument(
            source=source,
            destination=destination,
            rendered=_rewrite_asset_references(
                source.read_text(encoding="utf-8"),
                renames,
            ),
            remove_source=True,
        )

    for note in _iter_managed_notes(vault, selected):
        relative = note.relative_to(selected)
        if relative in set(trash):
            continue
        markdown = note.read_text(encoding="utf-8")
        if AUTO_LINKS_SECTION.search(markdown) and relative not in links:
            raise ValueError(
                f"decisions.links 缺少现有受控链接文档: {relative}"
            )

    for relative, targets in links.items():
        final_relative = final_relative_by_source.get(relative, relative)
        final_domain_root = _require_domain_root(
            selected,
            final_relative.parts[0],
            vault,
            f"{final_relative.parts[0]} links 最终领域目录",
        )
        destination = require_path_within_vault(
            selected / final_relative,
            vault,
            "links 最终来源",
            allowed_root=final_domain_root,
        )
        original_domain_root = _require_domain_root(
            selected,
            relative.parts[0],
            vault,
            f"{relative.parts[0]} links 原始领域目录",
        )
        original = require_path_within_vault(
            selected / relative,
            vault,
            "links 原始来源",
            allowed_root=original_domain_root,
        )
        if not original.is_file():
            raise FileNotFoundError(original)
        for target in targets:
            target_domain_root = _require_domain_root(
                selected,
                target.parts[0],
                vault,
                f"{target.parts[0]} links 目标领域目录",
            )
            target_original = require_path_within_vault(
                selected / target,
                vault,
                "links 目标",
                allowed_root=target_domain_root,
            )
            if not target_original.is_file():
                raise FileNotFoundError(target_original)
        existing_document = documents.get(relative)
        base = (
            existing_document.rendered
            if existing_document is not None
            else original.read_text(encoding="utf-8")
        )
        if existing_document is None:
            for _ in _referenced_assets(
                original,
                vault,
                selected,
                relative.parts[0],
            ):
                pass
        rendered = _render_links(
            base,
            tuple(
                final_relative_by_source.get(target, target)
                for target in targets
            ),
        )
        documents[relative] = PlannedDocument(
            source=original,
            destination=destination,
            rendered=rendered,
            remove_source=(
                existing_document.remove_source
                if existing_document is not None
                else False
            ),
        )

    index_roots = tuple(
        _require_domain_root(
            selected,
            domain,
            vault,
            f"{domain} 索引目录",
        )
        for domain in MANAGED_DOMAINS
    )
    snapshot_sources = {
        document.source
        for document in documents.values()
    }
    for domain_root in index_roots:
        index = require_path_within_vault(
            domain_root / INDEX_FILENAME,
            vault,
            "目录索引",
            allowed_root=domain_root,
        )
        if index.is_file():
            snapshot_sources.add(index)
    plan = ReviewPlan(
        vault=vault,
        selected=selected,
        trash_root=trash_root,
        moves=moves,
        trash=trash,
        links=links,
        final_relative_by_source=final_relative_by_source,
        documents=tuple(
            documents[key]
            for key in sorted(documents, key=lambda path: path.as_posix())
        ),
        assets=tuple(
            assets_by_destination[key]
            for key in sorted(
                assets_by_destination,
                key=lambda path: path.as_posix(),
            )
        ),
        index_roots=index_roots,
        snapshot_sources=tuple(
            sorted(snapshot_sources, key=lambda path: path.as_posix())
        ),
    )
    _validate_final_index_inputs(plan)
    return plan


def _preflight_review(vault, moves, trash, links):
    return _prepare_review_plan(vault, moves, trash, links)


def _create_directory(path, created_directories):
    missing = []
    current = Path(path)
    while not current.exists():
        missing.append(current)
        current = current.parent
    Path(path).mkdir(parents=True, exist_ok=True)
    created_directories.extend(reversed(missing))


def _restore_review_snapshot(snapshot, vault):
    archive, _ = snapshot
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            destination = require_path_within_vault(
                vault / Path(*PurePosixPath(info.filename).parts),
                vault,
                "快照恢复目标",
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(zipped.read(info.filename))


def execute_review(vault, moves, trash, links):
    plan = _prepare_review_plan(vault, moves, trash, links)
    snapshot = _create_review_snapshot(plan)
    created_files = set()
    created_directories = []
    try:
        for asset in plan.assets:
            _create_directory(asset.destination.parent, created_directories)
            if not asset.destination.exists():
                created_files.add(asset.destination)
                shutil.copy2(asset.source, asset.destination)
        for document in plan.documents:
            _create_directory(document.destination.parent, created_directories)
            if not document.destination.exists():
                created_files.add(document.destination)
            document.destination.write_text(
                document.rendered,
                encoding="utf-8",
            )
        for document in plan.documents:
            if (
                document.remove_source
                and document.source != document.destination
            ):
                document.source.unlink()
        for domain, domain_root in zip(MANAGED_DOMAINS, plan.index_roots):
            _create_directory(domain_root, created_directories)
            index = domain_root / INDEX_FILENAME
            temporary = domain_root / f".{INDEX_FILENAME}.tmp"
            if not index.exists():
                created_files.add(index)
            if not temporary.exists():
                created_files.add(temporary)
            write_knowledge_base_index(domain_root, domain)
            created_files.discard(temporary)
        for asset in plan.assets:
            if not asset.source.is_file():
                raise RuntimeError(f"来源附件在执行后缺失: {asset.source}")
    except Exception as exc:
        rollback_issues = []
        try:
            _restore_review_snapshot(snapshot, plan.vault)
        except Exception as rollback_exc:
            rollback_issues.append(f"恢复快照失败: {rollback_exc}")
        for path in sorted(
            created_files,
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            if path.exists() and path.is_file():
                try:
                    path.unlink()
                except OSError as cleanup_exc:
                    rollback_issues.append(
                        f"清理新增文件失败: {path} ({cleanup_exc})"
                    )
        for directory in reversed(created_directories):
            if directory.exists() and directory.is_dir():
                try:
                    directory.rmdir()
                except OSError:
                    pass
        rollback_status = (
            "回滚不完整: " + "; ".join(rollback_issues)
            if rollback_issues
            else "已回滚"
        )
        raise ReviewExecutionError(
            f"重分类执行失败，{rollback_status}: {exc}",
            snapshot,
        ) from exc
    return snapshot


def _managed_target_relative(raw_target):
    decoded = unquote(raw_target).strip()
    target = PurePosixPath(decoded)
    if not target.parts or target.parts[0] != SELECTED_ROOT:
        raise ValueError(f"受控链接必须指向 {SELECTED_ROOT}: {raw_target}")
    relative = PurePosixPath(*target.parts[1:])
    if relative.suffix.casefold() != ".md":
        relative = relative.parent / f"{relative.name}.md"
    return _decision_relative_path(
        Path(*relative.parts),
        "受控链接目标",
    )


def _read_managed_links(vault, selected):
    links_by_source = {}
    issues = []
    for note in _iter_managed_notes(vault, selected):
        markdown = note.read_text(encoding="utf-8")
        sections = tuple(AUTO_LINKS_SECTION.finditer(markdown))
        if not sections:
            continue
        source = note.relative_to(selected)
        if len(sections) > 1:
            issues.append(f"受控链接区重复: {source}")
        raw_targets = tuple(
            target.group(1)
            for section in sections
            for target in _WIKILINK.finditer(section.group(0))
        )
        targets = []
        for raw_target in raw_targets:
            try:
                target = _managed_target_relative(raw_target)
                target_path = require_path_within_vault(
                    selected / target,
                    vault,
                    "受控链接目标",
                    allowed_root=selected,
                )
            except ValueError as exc:
                issues.append(f"受控链接无效: {source} -> {raw_target} ({exc})")
                continue
            targets.append(target)
            if not target_path.is_file():
                issues.append(f"链接目标不存在: {source} -> {target}")
        if len(set(targets)) != len(targets):
            issues.append(f"受控链接重复: {source}")
        if source in targets:
            issues.append(f"受控链接包含自链接: {source}")
        if len(targets) > 3:
            issues.append(f"受控链接超过 3 条: {source}")
        if targets:
            links_by_source[source] = tuple(targets)
    for source, targets in links_by_source.items():
        for target in targets:
            if source not in links_by_source.get(target, ()):
                issues.append(f"自动链接不对称: {source} -> {target}")
    return links_by_source, issues


def validate_links(vault):
    vault, selected, _ = _validated_vault_roots(vault)
    links_by_source, issues = _read_managed_links(vault, selected)
    del links_by_source
    return tuple(sorted(set(issues)))


def _create_review_snapshot(plan):
    vault = plan.vault
    sources = plan.snapshot_sources
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    state_paths = VaultStatePaths.for_vault(vault)
    snapshot_dir = require_path_within_vault(
        state_paths.root / "snapshots",
        vault,
        "重分类快照目录",
        allowed_root=state_paths.root,
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    archive = require_path_within_vault(
        snapshot_dir / f"{stamp}-selected-materials-rescan-before.zip",
        vault,
        "重分类快照 ZIP",
        allowed_root=snapshot_dir,
    )
    manifest = require_path_within_vault(
        snapshot_dir / f"{stamp}-selected-materials-rescan-before.json",
        vault,
        "重分类快照清单",
        allowed_root=snapshot_dir,
    )
    files = []
    with zipfile.ZipFile(
        archive, "x", compression=zipfile.ZIP_DEFLATED
    ) as zipped:
        for source in sorted(sources, key=lambda path: str(path)):
            relative = source.relative_to(vault).as_posix()
            payload = source.read_bytes()
            zipped.writestr(relative, payload)
            files.append(
                {
                    "path": relative,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    manifest.write_text(
        json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return archive, manifest


def create_review_snapshot(vault, moves, trash, links):
    """预检全部操作后，只快照将被修改或删除的 Markdown 与既存索引。"""
    return _create_review_snapshot(
        _prepare_review_plan(vault, moves, trash, links)
    )


def audit_vault(vault):
    vault, selected, _ = _validated_vault_roots(vault)
    documents = []
    for note in _iter_managed_notes(vault, selected):
        current_domain = note.relative_to(selected).parts[0]
        markdown = note.read_text(encoding="utf-8")
        title_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
        title = title_match.group(1).strip() if title_match else note.stem
        body = re.sub(
            r"\A---\r?\n.*?\r?\n---\r?\n",
            "",
            markdown,
            flags=re.S,
        )
        body = AUTO_LINKS_SECTION.sub("", body)
        result = classify_document(title, body, current_domain)
        evidence_domain = result.target_domain or current_domain
        documents.append(
            {
                "path": note.relative_to(selected).as_posix(),
                "title": title,
                "current_domain": current_domain,
                "decision": result.decision,
                "target_domain": result.target_domain,
                "score": (
                    result.scores.get(result.target_domain, 0)
                    if result.target_domain
                    else max(result.scores.values(), default=0)
                ),
                "evidence": list(result.evidence.get(evidence_domain, ())),
                "scores": result.scores,
            }
        )
    decision_counts = dict(
        sorted(Counter(item["decision"] for item in documents).items())
    )
    return {
        "vault": str(vault),
        "document_count": len(documents),
        "decision_counts": decision_counts,
        "link_issues": list(validate_links(vault)),
        "documents": documents,
    }


def _decision_relative_path(value, field):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError(f"{field} 必须是非空路径")
    if isinstance(value, str) and "\\" in value:
        raise ValueError(f"{field} 必须使用正斜杠")
    path = Path(value)
    if (
        path.is_absolute()
        or len(path.parts) != 3
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0] not in MANAGED_DOMAINS
        or not _MONTH_DIRECTORY.fullmatch(path.parts[1])
        or path.suffix.casefold() != ".md"
        or path.name == INDEX_FILENAME
    ):
        raise ValueError(
            f"{field} 必须是 <已知领域>/YYYY年MM月/*.md 的规范资料路径"
        )
    return path


def _normalize_review_decisions(moves, trash, links):
    """把文件输入和直接 API 输入统一收敛到同一严格决策契约。"""
    if not isinstance(moves, dict):
        raise ValueError("moves 必须是对象")
    if not isinstance(trash, (list, tuple)):
        raise ValueError("trash 必须是列表")
    if not isinstance(links, dict):
        raise ValueError("links 必须是对象")

    normalized_moves = {}
    for raw_source, target_domain in moves.items():
        source = _decision_relative_path(raw_source, "moves 路径")
        if source in normalized_moves:
            raise ValueError(f"moves 不允许重复规范化路径: {source}")
        _validate_target_domain(target_domain)
        if target_domain == source.parts[0]:
            raise ValueError("move 目标领域不能与来源领域相同")
        normalized_moves[source] = target_domain

    normalized_trash = tuple(
        _decision_relative_path(raw_path, "trash 路径")
        for raw_path in trash
    )
    if len(set(normalized_trash)) != len(normalized_trash):
        raise ValueError("trash 不允许重复路径")
    trash_set = set(normalized_trash)
    if set(normalized_moves) & trash_set:
        raise ValueError("同一资料不能同时 move 和 trash")

    normalized_links = {}
    for raw_source, raw_targets in links.items():
        source = _decision_relative_path(raw_source, "links 路径")
        if source in normalized_links:
            raise ValueError(f"links 不允许重复规范化路径: {source}")
        if not isinstance(raw_targets, (list, tuple)):
            raise ValueError("links 目标必须是列表")
        targets = tuple(
            _decision_relative_path(raw_target, "links 目标")
            for raw_target in raw_targets
        )
        if source in targets:
            raise ValueError("links 不允许自链接")
        if len(set(targets)) != len(targets):
            raise ValueError("links 不允许重复链接")
        if len(targets) > 3:
            raise ValueError("每篇资料最多三个 links")
        normalized_links[source] = targets

    for source, targets in normalized_links.items():
        if source in trash_set:
            raise ValueError("trash 资料不能作为 links 端点")
        for target in targets:
            if target in trash_set:
                raise ValueError("trash 资料不能作为 links 端点")
            if source not in normalized_links.get(target, ()):
                raise ValueError("links 必须严格双向对称")

    return {
        "moves": normalized_moves,
        "trash": normalized_trash,
        "links": normalized_links,
    }


def _reject_duplicate_json_keys(pairs):
    payload = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"决策文件存在重复键: {key}")
        payload[key] = value
    return payload


def load_review_decisions(path: Path) -> dict[str, object]:
    """读取人工确认的精选资料重分类决定并校验其操作边界。"""
    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"决策文件不是有效 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("决策文件根节点必须是对象")
    expected_keys = {"moves", "trash", "links"}
    if set(payload) != expected_keys:
        raise ValueError("决策文件根节点必须且只能包含 moves、trash、links")

    raw_moves = payload["moves"]
    raw_trash = payload["trash"]
    raw_links = payload["links"]
    if not isinstance(raw_moves, dict):
        raise ValueError("moves 必须是对象")
    if not isinstance(raw_trash, list):
        raise ValueError("trash 必须是列表")
    if not isinstance(raw_links, dict):
        raise ValueError("links 必须是对象")
    return _normalize_review_decisions(raw_moves, raw_trash, raw_links)


def _review_move_destination(vault, relative, target_domain):
    return (
        Path(vault)
        / SELECTED_ROOT
        / target_domain
        / Path(relative).parent.name
        / Path(relative).name
    )


def _review_trash_destination(vault, relative):
    return Path(vault) / "99_废纸篓" / SELECTED_ROOT / Path(relative)


def _note_asset_issues(note, vault):
    vault, selected, trash_root = _validated_vault_roots(vault)
    note = Path(note).resolve()
    issues = []
    try:
        relative = note.relative_to(selected)
        domain_root = selected / relative.parts[0]
    except (ValueError, IndexError):
        try:
            relative = note.relative_to(trash_root)
            domain_root = trash_root / relative.parts[0]
        except (ValueError, IndexError):
            return [f"资料超出受管目录: {note}"]
    try:
        note = require_path_within_vault(
            note,
            vault,
            "待验证资料",
            allowed_root=domain_root,
        )
        attachment_root = require_path_within_vault(
            domain_root / "_attachments",
            vault,
            "待验证附件目录",
            allowed_root=domain_root,
        )
    except ValueError as exc:
        return [f"附件超出受管目录: {note} ({exc})"]
    markdown = note.read_text(encoding="utf-8")
    for raw_target in _ASSET_LINK.findall(markdown):
        target = unquote(
            raw_target.split("#", 1)[0].strip().strip("<>")
        )
        if not target or target.lower().endswith(".md"):
            continue
        if "://" in target or (
            _REMOTE_TARGET.match(target) and not Path(target).is_absolute()
        ):
            continue
        target_path = Path(target)
        if target_path.is_absolute():
            issues.append(
                "附件超出受管目录: "
                f"{note.relative_to(vault).as_posix()} -> {raw_target}"
            )
            continue
        try:
            asset = require_path_within_vault(
                note.parent / target_path,
                vault,
                "待验证附件",
                allowed_root=attachment_root,
            )
        except ValueError:
            issues.append(
                "附件超出受管目录: "
                f"{note.relative_to(vault).as_posix()} -> {raw_target}"
            )
            continue
        if not asset.is_file():
            issues.append(
                "附件不存在: "
                f"{note.relative_to(vault).as_posix()} -> "
                f"{asset.relative_to(vault).as_posix()}"
            )
    return issues


def _verify_indexes(vault):
    vault, selected, _ = _validated_vault_roots(vault)
    issues = []
    index_counts = {}
    for domain in MANAGED_DOMAINS:
        domain_dir = require_path_within_vault(
            selected / domain,
            vault,
            f"{domain} 索引目录",
            allowed_root=selected,
        )
        _validate_domain_tree(vault, selected, domain_dir)
        index = domain_dir / INDEX_FILENAME
        if not index.is_file():
            issues.append(f"目录索引不存在: {index.relative_to(vault).as_posix()}")
            index_counts[domain] = 0
            continue
        actual_notes = set()
        for note in iter_indexable_note_paths(domain_dir, domain):
            relative_note = (
                note.relative_to(domain_dir).with_suffix("").as_posix()
            )
            actual_notes.add(relative_note)
            try:
                extract_note_metadata_from_text(
                    note,
                    note.read_text(encoding="utf-8"),
                )
            except (OSError, UnicodeError, ValueError) as exc:
                issues.append(
                    "索引资料元数据无效: "
                    f"{note.relative_to(vault).as_posix()} ({exc})"
                )
        indexed_notes = set()
        for raw_target in re.findall(r"\[\[([^|\]]+)(?:\|[^\]]*)?\]\]", index.read_text(encoding="utf-8")):
            target = unquote(raw_target).strip()
            if not target:
                continue
            indexed_notes.add(PurePosixPath(target).with_suffix("").as_posix())
        index_counts[domain] = len(indexed_notes)
        for target in sorted(indexed_notes - actual_notes):
            issues.append(
                "目录索引目标不存在: "
                f"{index.relative_to(vault).as_posix()} -> "
                f"{domain_dir.relative_to(vault).as_posix()}/{target}.md"
            )
        for target in sorted(actual_notes - indexed_notes):
            issues.append(
                "目录索引缺少资料: "
                f"{domain_dir.relative_to(vault).as_posix()}/{target}.md"
            )
    return index_counts, issues


def _verify_snapshot(vault, snapshot):
    archive, manifest = (Path(path) for path in snapshot)
    issues = []
    if not archive.is_file():
        return 0, [f"快照 ZIP 不存在: {archive.as_posix()}"]
    if not manifest.is_file():
        return 0, [f"快照清单不存在: {manifest.as_posix()}"]
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        records = payload["files"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return 0, [f"快照清单无效: {manifest.as_posix()} ({exc})"]
    if not isinstance(records, list):
        return 0, [f"快照清单无效: {manifest.as_posix()} (files 必须是列表)"]
    expected = {}
    for record in records:
        if not isinstance(record, dict) or not all(
            field in record for field in ("path", "size", "sha256")
        ):
            issues.append(f"快照清单条目无效: {manifest.as_posix()}")
            continue
        path = record["path"]
        if not isinstance(path, str) or path in expected:
            issues.append(f"快照清单路径无效: {manifest.as_posix()} -> {path!r}")
            continue
        expected[path] = record
    try:
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
            if names != set(expected):
                issues.append(
                    "快照 ZIP 条目与清单不一致: "
                    f"{archive.as_posix()} / {manifest.as_posix()}"
                )
            for path, record in expected.items():
                if path not in names:
                    continue
                content = zipped.read(path)
                if (
                    record["size"] != len(content)
                    or record["sha256"] != hashlib.sha256(content).hexdigest()
                ):
                    issues.append(
                        "快照 SHA-256 不匹配: "
                        f"{manifest.as_posix()} -> {path}"
                    )
    except zipfile.BadZipFile:
        issues.append(f"快照 ZIP 无效: {archive.as_posix()}")
    return len(expected), issues


def _frontmatter_domain(note):
    lines = note.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    if not lines or lines[0] != "---":
        return None
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return None
    for line in lines[1:closing]:
        if line.startswith((" ", "\t")):
            continue
        field, separator, value = line.partition(":")
        if separator and field == "domain":
            value = value.strip()
            if value in {"|", ">"}:
                return None
            if value.startswith('"'):
                try:
                    return str(json.loads(value))
                except json.JSONDecodeError:
                    return value.strip('"')
            return value.strip("'")
    return None


def _expected_final_links(moves, links):
    final_relative_by_source = {
        source: Path(target_domain, source.parts[1], source.name)
        for source, target_domain in moves.items()
    }
    expected = {}
    for source, targets in links.items():
        final_source = final_relative_by_source.get(source, source)
        final_targets = tuple(
            final_relative_by_source.get(target, target)
            for target in targets
        )
        if final_targets:
            expected[final_source] = final_targets
    return expected


def _verify_exact_links(vault, selected, moves, links):
    actual, issues = _read_managed_links(vault, selected)
    expected = _expected_final_links(moves, links)
    all_sources = set(actual) | set(expected)
    for source in sorted(all_sources, key=lambda path: path.as_posix()):
        actual_targets = set(actual.get(source, ()))
        expected_targets = set(expected.get(source, ()))
        for target in sorted(
            expected_targets - actual_targets,
            key=lambda path: path.as_posix(),
        ):
            issues.append(f"受控链接缺少: {source} -> {target}")
        for target in sorted(
            actual_targets - expected_targets,
            key=lambda path: path.as_posix(),
        ):
            issues.append(f"受控链接额外: {source} -> {target}")
    return actual, issues


def verify_review_results(
    vault: Path,
    moves: dict[Path, str],
    trash: tuple[Path, ...],
    links: dict[Path, tuple[Path, ...]],
    snapshot: tuple[Path, Path] | None = None,
) -> dict[str, object]:
    """验证本次精选资料重分类已完成且没有破坏受控内容。"""
    decisions = _normalize_review_decisions(moves, trash, links)
    moves = decisions["moves"]
    trash = decisions["trash"]
    links = decisions["links"]
    vault, selected, trash_root = _validated_vault_roots(vault)
    issues = []
    checked_notes = []
    for relative, target_domain in moves.items():
        source = require_path_within_vault(
            selected / relative,
            vault,
            "验证移动来源",
            allowed_root=selected,
        )
        destination = require_path_within_vault(
            _review_move_destination(vault, relative, target_domain),
            vault,
            "验证移动目标",
            allowed_root=selected,
        )
        if source.exists():
            issues.append(f"移动来源仍存在: {source.relative_to(vault).as_posix()}")
        if not destination.is_file():
            issues.append(f"移动目标不存在: {destination.relative_to(vault).as_posix()}")
            continue
        actual_domain = _frontmatter_domain(destination)
        if actual_domain != target_domain:
            issues.append(
                "移动目标 domain 不匹配: "
                f"{destination.relative_to(vault).as_posix()} "
                f"(应为 {target_domain}，实际 {actual_domain})"
            )
        checked_notes.append(destination)
    for relative in trash:
        source = require_path_within_vault(
            selected / relative,
            vault,
            "验证废纸篓来源",
            allowed_root=selected,
        )
        destination = require_path_within_vault(
            _review_trash_destination(vault, relative),
            vault,
            "验证废纸篓目标",
            allowed_root=trash_root,
        )
        if source.exists():
            issues.append(f"废纸篓来源仍存在: {source.relative_to(vault).as_posix()}")
        if not destination.is_file():
            issues.append(f"废纸篓镜像不存在: {destination.relative_to(vault).as_posix()}")
            continue
        checked_notes.append(destination)

    missing_assets = []
    for note in checked_notes:
        for issue in _note_asset_issues(note, vault):
            missing_assets.append(issue)
            issues.append(issue)
    actual_links, link_issues = _verify_exact_links(
        vault,
        selected,
        moves,
        links,
    )
    issues.extend(link_issues)
    index_counts, index_issues = _verify_indexes(vault)
    issues.extend(index_issues)
    snapshot_files = 0
    if snapshot is not None:
        snapshot_files, snapshot_issues = _verify_snapshot(vault, snapshot)
        issues.extend(snapshot_issues)
    return {
        "ok": not issues,
        "moves": len(moves),
        "trash": len(trash),
        "managed_link_notes": len(actual_links),
        "missing_assets": missing_assets,
        "index_counts": index_counts,
        "snapshot_files": snapshot_files,
        "snapshot": (
            {
                "archive": str(snapshot[0]),
                "manifest": str(snapshot[1]),
            }
            if snapshot is not None
            else None
        ),
        "issues": sorted(issues),
    }


def default_report_path(vault: Path, phase: str) -> Path:
    """生成保存在 Vault 状态目录中的阶段报告路径。"""
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    paths = VaultStatePaths.for_vault(vault)
    return paths.reports / f"{phase}-{stamp}.json"


def _write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _pending_review_items(moves, trash, links):
    return [
        *(
            f"move:{source.as_posix()}->{target}"
            for source, target in moves.items()
        ),
        *(f"trash:{source.as_posix()}" for source in trash),
        *(
            f"links:{source.as_posix()}"
            for source in links
        ),
        "indexes:固定九领域全量重建",
    ]


def _apply_failure_report(
    exc,
    moves,
    trash,
    links,
    *,
    snapshot=None,
    execution_completed=False,
):
    snapshot = getattr(exc, "snapshot", None) or snapshot
    operations = _pending_review_items(moves, trash, links)
    return {
        "ok": False,
        "phase": "apply",
        "snapshot": (
            {
                "archive": str(snapshot[0]),
                "manifest": str(snapshot[1]),
            }
            if snapshot is not None
            else None
        ),
        "completed": operations if execution_completed else [],
        "pending": ["verify"] if execution_completed else operations,
        "issues": [str(exc)],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="精选资料重分类审阅工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "默认 Vault：--vault 省略时读取 OBSIDIAN_VAULT_PATH。\n"
            "默认报告：<vault>/.state/yinxiang-notes/reports/。\n"
            "decisions JSON 必须且只能包含 moves、trash、links；资料路径格式为\n"
            "<已知领域>/YYYY年MM月/*.md。\n\n"
            "示例：\n"
            "  python scripts/reclassify_selected_materials.py audit\n"
            "  python scripts/reclassify_selected_materials.py verify "
            "--decisions decisions.json"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command_help = {
        "audit": "业务资料只读扫描，并写审计报告",
        "apply": "修改业务资料、复制受管附件并全量重建九个领域索引",
        "verify": "业务资料只读；写验证报告",
    }
    for command in ("audit", "apply", "verify"):
        subparser = commands.add_parser(
            command,
            help=command_help[command],
            description=command_help[command],
        )
        subparser.add_argument(
            "--vault",
            type=Path,
            help="Obsidian Vault；省略时读取 OBSIDIAN_VAULT_PATH",
        )
        subparser.add_argument(
            "--output",
            type=Path,
            help=(
                "报告路径；默认写入 "
                "<vault>/.state/yinxiang-notes/reports/"
            ),
        )
        if command in {"apply", "verify"}:
            subparser.add_argument(
                "--decisions",
                type=Path,
                required=True,
                help=(
                    "严格 decisions JSON：moves、trash、links；"
                    "路径为 <已知领域>/YYYY年MM月/*.md"
                ),
            )
        if command == "apply":
            subparser.add_argument(
                "--confirm",
                help=(
                    "修改业务资料前的确认词，必须精确为 "
                    "RECLASSIFY_SELECTED_MATERIALS"
                ),
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        vault = load_vault_root(args.vault)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        output = args.output or default_report_path(vault, args.command)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.command == "audit":
        try:
            report = audit_vault(vault)
            _write_report(output, report)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"审阅失败: {exc}", file=sys.stderr)
            return 1
        print(f"审阅报告：{output}")
        return 0
    if args.command == "apply" and args.confirm != "RECLASSIFY_SELECTED_MATERIALS":
        print(
            "apply 必须同时提供 --confirm RECLASSIFY_SELECTED_MATERIALS",
            file=sys.stderr,
        )
        return 2
    try:
        decisions = load_review_decisions(args.decisions)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    moves = decisions["moves"]
    trash = decisions["trash"]
    links = decisions["links"]
    if args.command == "apply":
        try:
            state_paths = VaultStatePaths.for_vault(vault)
            with runtime_write_lock(
                state_paths,
                "reclassify-selected-materials",
            ):
                snapshot = None
                execution_completed = False
                try:
                    snapshot = execute_review(
                        vault,
                        moves,
                        trash,
                        links,
                    )
                    execution_completed = True
                    report = verify_review_results(
                        vault,
                        moves,
                        trash,
                        links,
                        snapshot,
                    )
                except Exception as exc:
                    report = _apply_failure_report(
                        exc,
                        moves,
                        trash,
                        links,
                        snapshot=snapshot,
                        execution_completed=execution_completed,
                    )
                _write_report(output, report)
        except (
            OSError,
            StateLockConflict,
            UnicodeError,
            ValueError,
        ) as exc:
            print(f"apply 未执行: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            report = verify_review_results(vault, moves, trash, links)
        except (OSError, UnicodeError, ValueError) as exc:
            report = {
                "ok": False,
                "phase": "verify",
                "issues": [str(exc)],
            }
        try:
            _write_report(output, report)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"verify 报告写入失败: {exc}", file=sys.stderr)
            return 1
    if not report["ok"]:
        for issue in report["issues"]:
            print(f"{args.command} 失败: {issue}", file=sys.stderr)
        return 1
    print(f"验证报告：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
