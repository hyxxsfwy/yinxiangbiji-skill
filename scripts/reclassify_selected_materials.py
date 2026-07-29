"""重新审阅并整理 Obsidian 精选资料。"""

from dataclasses import dataclass
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from urllib.parse import unquote
import zipfile

from scripts.curate_selected_materials import (
    AUTO_LINKS_END,
    AUTO_LINKS_SECTION,
    AUTO_LINKS_START,
    extract_auto_link_targets,
)
from scripts.knowledge_base import write_knowledge_base_index


SELECTED_ROOT = "30_精选资料"
INDEX_FILENAME = "目录索引.md"
_ASSET_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_DOMAIN_LINE = re.compile(r'(?m)^domain:\s*(?:"[^"]*"|[^\r\n]*)$')

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
            "quant",
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
        ),
        "support": (
            "健康", "症状", "手术", "感染", "营养", "睡眠", "心脏",
            "大脑", "寿命",
        ),
    },
    "中医": {
        "core": (
            "中医", "中药", "经络", "针灸", "穴位", "方剂", "辨证论治",
            "阴阳", "气血", "脏腑",
        ),
        "support": ("调理", "体质", "养生", "脉象", "舌象"),
    },
    "两性情感": {
        "core": (
            "两性", "婚姻", "伴侣", "夫妻", "恋爱", "亲密关系", "情感关系",
            "婚恋", "离婚", "彩礼", "婚房", "婆媳", "择偶",
            "出轨", "老公", "老婆", "丈夫", "妻子", "男友", "女友",
            "小三",
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
        ),
        "support": (
            "复盘", "目标管理", "专注", "阅读", "学习", "职业", "沟通",
            "效率",
        ),
    },
}
SPECIFIC_DOMAINS = {"Quant", "中医", "两性情感", "知识管理"}
TITLE_FALLBACKS = (
    ("Quant", re.compile(
        r"量化|TDXQuant|Alpha|因子|回测|时间序列|缠论|交易策略|交易系统|"
        r"短线交易|技术交易|实盘",
        re.I,
    )),
    ("知识管理", re.compile(r"知识库|Obsidian|PKM|GTD|卡片笔记", re.I)),
    ("投资理财", re.compile(
        r"币安|币圈|港股|港卡|牛市|熊市|现金流|房贷|贷款|银行|万事达|"
        r"VISA|财富自由|OKE|V神|以太坊|比特币|交易商|股票|证券|基金|"
        r"美股|A股|黄金|白银|理财",
        re.I,
    )),
    ("中医", re.compile(r"中医|中药|倪海厦|徐文兵|针灸|穴位|气血|灸|药酒")),
    ("健康医学", re.compile(
        r"癌|肺|基因|细胞|免疫|病毒|医生|医学|医疗|医院|猝死|睡眠|"
        r"体重|减肥|脂肪|代谢|卵巢|盆底肌|心脏|健康|器官|犯困",
    )),
    ("两性情感", re.compile(
        r"婚|妻|夫|老公|老婆|伴侣|恋爱|女友|男友|小三|出轨|两性|"
        r"情感|亲密关系|相亲|女权|男权",
    )),
    ("个人成长", re.compile(
        r"个人成长|人生选择|自我|前额叶|拖延|生活方式|内卷|职业规划|"
        r"失业|裁员|跳槽|找工作|沟通",
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
        r"大模型|机器学习|开源模型|本体论|推理技术",
        re.I,
    )),
)


@dataclass(frozen=True)
class Classification:
    decision: str
    target_domain: str | None
    scores: dict[str, int]
    evidence: dict[str, tuple[str, ...]]


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
    if current_domain in SPECIFIC_DOMAINS and current_title_score >= 8:
        return Classification("keep", current_domain, scores, evidence)
    if (
        current_title_score >= 8
        and current_title_score == max(title_scores.values(), default=0)
    ):
        return Classification("keep", current_domain, scores, evidence)
    target_domain, target_score = max(
        scores.items(),
        key=lambda item: (
            title_scores[item[0]],
            item[1],
            item[0],
        ),
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
    current_score = scores.get(current_domain, 0)
    title_evidence = title_scored[target_domain][1]
    title_has_core = any(
        term in title_evidence
        for term in DOMAIN_PROFILES[target_domain]["core"]
    )
    body_core_hits = sum(
        term in evidence[target_domain]
        for term in DOMAIN_PROFILES[target_domain]["core"]
    )
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
    replacement = f'domain: "{domain}"'
    if not _DOMAIN_LINE.search(markdown):
        raise ValueError("文档缺少 domain frontmatter")
    return _DOMAIN_LINE.sub(replacement, markdown, count=1)


def _referenced_assets(note):
    text = note.read_text(encoding="utf-8")
    for raw_target in _ASSET_LINK.findall(text):
        target = unquote(
            raw_target.split("#", 1)[0].strip().strip("<>")
        )
        if not target or "://" in target or target.lower().endswith(".md"):
            continue
        path = (note.parent / target).resolve()
        if path.is_file():
            yield path


def _collision_safe_asset_destination(asset, target_dir):
    destination = target_dir / asset.name
    payload = asset.read_bytes()
    if not destination.exists() or destination.read_bytes() == payload:
        return destination
    digest = hashlib.sha256(payload).hexdigest()[:12]
    destination = target_dir / f"{asset.stem}_{digest}{asset.suffix}"
    if destination.exists() and destination.read_bytes() != payload:
        raise FileExistsError(destination)
    return destination


def _rewrite_asset_references(markdown, renames):
    for source_name, destination_name in renames.items():
        if source_name == destination_name:
            continue
        markdown = markdown.replace(
            f"../_attachments/{source_name}",
            f"../_attachments/{destination_name}",
        )
    return markdown


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


def execute_review(vault, moves, trash, links):
    vault = Path(vault).resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault: {vault}")
    selected = vault / SELECTED_ROOT
    move_destinations = {}
    for relative, target_domain in moves.items():
        relative = Path(relative)
        source = selected / relative
        destination = selected / target_domain / relative.parent.name / relative.name
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists():
            raise FileExistsError(destination)
        move_destinations[relative] = destination
        for asset in _referenced_assets(source):
            _collision_safe_asset_destination(
                asset,
                selected / target_domain / "_attachments",
            )
    trash_destinations = {}
    for relative in trash:
        relative = Path(relative)
        source = selected / relative
        destination = vault / "99_废纸篓" / SELECTED_ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists():
            raise FileExistsError(destination)
        trash_destinations[relative] = destination
        for asset in _referenced_assets(source):
            target_dir = (
                vault
                / "99_废纸篓"
                / SELECTED_ROOT
                / relative.parts[0]
                / "_attachments"
            )
            _collision_safe_asset_destination(asset, target_dir)

    create_review_snapshot(vault, moves, trash, links)

    final_path_by_source = {}
    for relative, target_domain in moves.items():
        relative = Path(relative)
        source = selected / relative
        destination = move_destinations[relative]
        destination.parent.mkdir(parents=True, exist_ok=True)
        asset_renames = {}
        for asset in _referenced_assets(source):
            asset_destination = _collision_safe_asset_destination(
                asset,
                selected / target_domain / "_attachments",
            )
            asset_destination.parent.mkdir(parents=True, exist_ok=True)
            if not asset_destination.exists():
                shutil.copy2(asset, asset_destination)
            asset_renames[asset.name] = asset_destination.name
        markdown = _update_domain(
            source.read_text(encoding="utf-8"), target_domain
        )
        markdown = _rewrite_asset_references(markdown, asset_renames)
        destination.write_text(markdown, encoding="utf-8")
        source.unlink()
        final_path_by_source[Path(relative)] = destination

    for relative in trash:
        relative = Path(relative)
        source = selected / relative
        destination = trash_destinations[relative]
        destination.parent.mkdir(parents=True, exist_ok=True)
        asset_renames = {}
        for asset in _referenced_assets(source):
            target_dir = (
                vault
                / "99_废纸篓"
                / SELECTED_ROOT
                / relative.parts[0]
                / "_attachments"
            )
            asset_destination = _collision_safe_asset_destination(
                asset, target_dir
            )
            asset_destination.parent.mkdir(parents=True, exist_ok=True)
            if not asset_destination.exists():
                shutil.copy2(asset, asset_destination)
            asset_renames[asset.name] = asset_destination.name
        markdown = _rewrite_asset_references(
            source.read_text(encoding="utf-8"),
            asset_renames,
        )
        destination.write_text(markdown, encoding="utf-8")
        source.unlink()

    for relative, targets in links.items():
        note = final_path_by_source.get(Path(relative), selected / relative)
        rendered = _render_links(
            note.read_text(encoding="utf-8"),
            tuple(Path(target) for target in targets),
        )
        note.write_text(rendered, encoding="utf-8")

    for domain_dir in sorted(
        (path for path in selected.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        write_knowledge_base_index(domain_dir, domain_dir.name)


def validate_links(vault):
    vault = Path(vault).resolve()
    selected = vault / SELECTED_ROOT
    links_by_source = {}
    issues = []
    for note in selected.rglob("*.md"):
        if note.name == INDEX_FILENAME:
            continue
        targets = tuple(
            PurePosixPath(target).with_suffix("").as_posix()
            if PurePosixPath(target).suffix.casefold() == ".md"
            else PurePosixPath(target).as_posix()
            for target in extract_auto_link_targets(
                note.read_text(encoding="utf-8")
            )
        )
        if not targets:
            continue
        source = note.relative_to(vault).with_suffix("").as_posix()
        links_by_source[source] = set(targets)
        for target in targets:
            if not (vault / Path(*PurePosixPath(f"{target}.md").parts)).is_file():
                issues.append(f"链接目标不存在: {source} -> {target}")
    for source, targets in links_by_source.items():
        for target in targets:
            if source not in links_by_source.get(target, set()):
                issues.append(f"自动链接不对称: {source} -> {target}")
    return tuple(sorted(issues))


def create_review_snapshot(vault, moves, trash, links):
    vault = Path(vault).resolve()
    selected = vault / SELECTED_ROOT
    sources = set()
    for relative in (*moves.keys(), *trash, *links.keys()):
        path = selected / Path(relative)
        if path.is_file():
            sources.add(path)
    sources.update(
        path
        for path in selected.glob(f"*/{INDEX_FILENAME}")
        if path.is_file()
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snapshot_dir = (
        vault / ".state" / "yinxiang-notes" / "snapshots"
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    archive = snapshot_dir / f"{stamp}-selected-materials-rescan-before.zip"
    manifest = snapshot_dir / f"{stamp}-selected-materials-rescan-before.json"
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


def audit_vault(vault):
    vault = Path(vault).resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault: {vault}")
    selected = vault / SELECTED_ROOT
    documents = []
    for domain_dir in sorted(
        (path for path in selected.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        for note in sorted(domain_dir.rglob("*.md")):
            if note.name == INDEX_FILENAME:
                continue
            markdown = note.read_text(encoding="utf-8")
            title_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
            title = title_match.group(1).strip() if title_match else note.stem
            body = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", markdown, flags=re.S)
            body = AUTO_LINKS_SECTION.sub("", body)
            result = classify_document(title, body, domain_dir.name)
            evidence_domain = result.target_domain or domain_dir.name
            documents.append(
                {
                    "path": note.relative_to(selected).as_posix(),
                    "title": title,
                    "current_domain": domain_dir.name,
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
