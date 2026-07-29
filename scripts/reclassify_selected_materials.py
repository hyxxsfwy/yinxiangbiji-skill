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
from urllib.parse import unquote
import zipfile

from scripts.curate_selected_materials import (
    AUTO_LINKS_END,
    AUTO_LINKS_SECTION,
    AUTO_LINKS_START,
    extract_auto_link_targets,
)
from scripts.knowledge_base import write_knowledge_base_index
from scripts.runtime import configure_utf8_output, load_vault_root


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


def _preflight_review(vault, moves, trash, links):
    vault = Path(vault).resolve()
    selected = (vault / SELECTED_ROOT).resolve()
    trash_root = (vault / "99_废纸篓" / SELECTED_ROOT).resolve()
    move_destinations = {}
    move_sources_by_destination = {}
    final_relative_by_source = {}
    for raw_relative, raw_target_domain in moves.items():
        relative = Path(raw_relative)
        target_domain = _validate_target_domain(raw_target_domain)
        source = selected / relative
        if not _is_within(source, selected):
            raise ValueError(f"移动来源超出精选资料目录: {relative}")
        destination = _review_move_destination(
            vault, relative, target_domain
        )
        if not _is_within(destination, selected):
            raise ValueError(f"移动目标超出精选资料目录: {destination}")
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists():
            raise FileExistsError(destination)
        resolved_destination = destination.resolve()
        if resolved_destination in move_sources_by_destination:
            raise ValueError(
                "多个 move 不能规划到同一目标: "
                f"{relative} 与 {move_sources_by_destination[resolved_destination]}"
            )
        move_sources_by_destination[resolved_destination] = relative
        move_destinations[relative] = destination
        final_relative_by_source[relative] = destination.relative_to(selected)
        for asset in _referenced_assets(source):
            _collision_safe_asset_destination(
                asset,
                selected / target_domain / "_attachments",
            )

    trash_destinations = {}
    trash_paths = {Path(relative) for relative in trash}
    if set(move_destinations) & trash_paths:
        raise ValueError("同一资料不能同时 move 和 trash")
    for raw_relative in trash:
        relative = Path(raw_relative)
        source = selected / relative
        destination = _review_trash_destination(vault, relative)
        if not _is_within(source, selected):
            raise ValueError(f"废纸篓来源超出精选资料目录: {relative}")
        if not _is_within(destination, trash_root):
            raise ValueError(f"废纸篓目标超出废纸篓目录: {destination}")
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists():
            raise FileExistsError(destination)
        trash_destinations[relative] = destination
        for asset in _referenced_assets(source):
            target_dir = trash_root / relative.parts[0] / "_attachments"
            _collision_safe_asset_destination(asset, target_dir)

    for raw_source, raw_targets in links.items():
        source = Path(raw_source)
        targets = tuple(Path(target) for target in raw_targets)
        if source in trash_paths or any(target in trash_paths for target in targets):
            raise ValueError("trash 资料不能作为 links 端点")
        for endpoint in (source, *targets):
            original = selected / endpoint
            final = selected / final_relative_by_source.get(endpoint, endpoint)
            if not _is_within(original, selected) or not _is_within(final, selected):
                raise ValueError(f"links 端点超出精选资料目录: {endpoint}")
            if not original.is_file():
                raise FileNotFoundError(original)
    return move_destinations, trash_destinations, final_relative_by_source


def execute_review(vault, moves, trash, links):
    vault = Path(vault).resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError(f"目标不是 Obsidian vault: {vault}")
    selected = vault / SELECTED_ROOT
    (
        move_destinations,
        trash_destinations,
        final_relative_by_source,
    ) = _preflight_review(vault, moves, trash, links)

    snapshot = create_review_snapshot(vault, moves, trash, links)

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
        final_relative = final_relative_by_source.get(
            Path(relative), Path(relative)
        )
        note = selected / final_relative
        rendered = _render_links(
            note.read_text(encoding="utf-8"),
            tuple(
                final_relative_by_source.get(Path(target), Path(target))
                for target in targets
            ),
        )
        note.write_text(rendered, encoding="utf-8")

    for domain_dir in sorted(
        (path for path in selected.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        write_knowledge_base_index(domain_dir, domain_dir.name)
    return snapshot


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


def _decision_relative_path(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} 必须是非空路径")
    path = Path(value)
    if path.is_absolute() or len(path.parts) < 2 or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ValueError(f"{field} 必须相对于 {SELECTED_ROOT}")
    return path


def load_review_decisions(path: Path) -> dict[str, object]:
    """读取人工确认的精选资料重分类决定并校验其操作边界。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"决策文件不是有效 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("决策文件根节点必须是对象")

    raw_moves = payload.get("moves", {})
    raw_trash = payload.get("trash", [])
    raw_links = payload.get("links", {})
    if not isinstance(raw_moves, dict):
        raise ValueError("moves 必须是对象")
    if not isinstance(raw_trash, list):
        raise ValueError("trash 必须是列表")
    if not isinstance(raw_links, dict):
        raise ValueError("links 必须是对象")

    moves = {}
    for raw_source, target_domain in raw_moves.items():
        source = _decision_relative_path(raw_source, "moves 路径")
        if not isinstance(target_domain, str) or not target_domain.strip():
            raise ValueError("move 目标领域不能为空")
        target_domain = target_domain.strip()
        _validate_target_domain(target_domain)
        if target_domain == source.parts[0]:
            raise ValueError("move 目标领域不能与来源领域相同")
        moves[source] = target_domain

    trash = tuple(
        _decision_relative_path(raw_path, "trash 路径")
        for raw_path in raw_trash
    )
    trash_set = set(trash)
    if set(moves) & trash_set:
        raise ValueError("同一资料不能同时 move 和 trash")

    links = {}
    for raw_source, raw_targets in raw_links.items():
        source = _decision_relative_path(raw_source, "links 路径")
        if not isinstance(raw_targets, list):
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
        links[source] = targets

    for source, targets in links.items():
        if source in trash_set:
            raise ValueError("trash 资料不能作为 links 端点")
        for target in targets:
            if target in trash_set:
                raise ValueError("trash 资料不能作为 links 端点")
            if source not in links.get(target, ()):
                raise ValueError("links 必须严格双向对称")

    return {"moves": moves, "trash": trash, "links": links}


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
    issues = []
    markdown = note.read_text(encoding="utf-8")
    for raw_target in _ASSET_LINK.findall(markdown):
        target = unquote(raw_target.split("#", 1)[0].strip().strip("<>"))
        if not target or "://" in target or target.lower().endswith(".md"):
            continue
        asset = (note.parent / target).resolve()
        if not asset.is_file():
            issues.append(
                "附件不存在: "
                f"{note.relative_to(vault).as_posix()} -> "
                f"{asset.relative_to(vault).as_posix()}"
            )
    return issues


def _verify_indexes(vault):
    selected = Path(vault) / SELECTED_ROOT
    issues = []
    index_counts = {}
    for domain_dir in sorted(
        (path for path in selected.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        if domain_dir.name == "_attachments":
            continue
        index = domain_dir / INDEX_FILENAME
        if not index.is_file():
            issues.append(f"目录索引不存在: {index.relative_to(vault).as_posix()}")
            continue
        actual_notes = {
            note.relative_to(domain_dir).with_suffix("").as_posix()
            for note in domain_dir.rglob("*.md")
            if note.name != INDEX_FILENAME
        }
        indexed_notes = set()
        for raw_target in re.findall(r"\[\[([^|\]]+)(?:\|[^\]]*)?\]\]", index.read_text(encoding="utf-8")):
            target = unquote(raw_target).strip()
            if not target:
                continue
            indexed_notes.add(PurePosixPath(target).with_suffix("").as_posix())
        index_counts[domain_dir.name] = len(indexed_notes)
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


def verify_review_results(
    vault: Path,
    moves: dict[Path, str],
    trash: tuple[Path, ...],
    links: dict[Path, tuple[Path, ...]],
    snapshot: tuple[Path, Path] | None = None,
) -> dict[str, object]:
    """验证本次精选资料重分类已完成且没有破坏受控内容。"""
    vault = Path(vault).resolve()
    selected = vault / SELECTED_ROOT
    issues = []
    checked_notes = []
    for relative, target_domain in moves.items():
        relative = Path(relative)
        source = selected / relative
        destination = _review_move_destination(vault, relative, target_domain)
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
        relative = Path(relative)
        source = selected / relative
        destination = _review_trash_destination(vault, relative)
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
    for issue in validate_links(vault):
        issues.append(issue)
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
        "managed_link_notes": len(links),
        "missing_assets": missing_assets,
        "index_counts": index_counts,
        "snapshot_files": snapshot_files,
        "issues": sorted(issues),
    }


def default_report_path(vault: Path, phase: str) -> Path:
    """生成保存在 Vault 状态目录中的阶段报告路径。"""
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return (
        Path(vault)
        / ".state"
        / "yinxiang-notes"
        / "reports"
        / f"{phase}-{stamp}.json"
    )


def _write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="精选资料重分类审阅工具")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "apply", "verify"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--vault", type=Path)
        subparser.add_argument("--output", type=Path)
        if command in {"apply", "verify"}:
            subparser.add_argument("--decisions", type=Path, required=True)
        if command == "apply":
            subparser.add_argument("--confirm")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        vault = load_vault_root(args.vault)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = args.output or default_report_path(vault, args.command)
    if args.command == "audit":
        report = audit_vault(vault)
        _write_report(output, report)
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
        snapshot = execute_review(vault, moves, trash, links)
        report = verify_review_results(vault, moves, trash, links, snapshot)
    else:
        report = verify_review_results(vault, moves, trash, links)
    _write_report(output, report)
    if not report["ok"]:
        for issue in report["issues"]:
            print(f"验证失败: {issue}", file=sys.stderr)
        return 1
    print(f"验证报告：{output}")
    return 0
