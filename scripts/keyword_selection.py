from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata

from scripts.export_search_results import full_body_text


KEYWORD_SELECTION_POLICY_VERSION = 1
_ASCII_TERM_RE = re.compile(r"[a-z0-9]+(?:[ ._-][a-z0-9]+)*")


@dataclass(frozen=True)
class KeywordAssessment:
    matched: bool
    primary_domain: str | None
    matched_keywords: tuple[str, ...]
    matched_terms: tuple[str, ...]
    reason: str


def _normalized(value):
    return unicodedata.normalize("NFKC", value or "").casefold()


def _contains_term(text, term):
    normalized_text = _normalized(text)
    normalized_term = _normalized(term)
    if not normalized_term:
        return False
    if _ASCII_TERM_RE.fullmatch(normalized_term):
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(normalized_term)
            + r"(?![a-z0-9])"
        )
        return re.search(pattern, normalized_text) is not None
    return normalized_term in normalized_text


def _canonical_terms(canonical_keyword, aliases):
    return (canonical_keyword, *aliases.get(canonical_keyword, ()))


def expanded_query_terms(domains, aliases):
    expanded = []
    seen = set()
    for domain, keywords in domains.items():
        for canonical_keyword in keywords:
            for query_term in _canonical_terms(canonical_keyword, aliases):
                identity = (
                    domain,
                    canonical_keyword,
                    _normalized(query_term),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                expanded.append((domain, canonical_keyword, query_term))
    return tuple(expanded)


def _match_details(title, content, domains, aliases):
    body = full_body_text(content)
    matches = {}
    terms_by_keyword = {}
    for domain, keywords in domains.items():
        domain_matches = []
        for canonical_keyword in keywords:
            matched_terms = tuple(
                term
                for term in _canonical_terms(canonical_keyword, aliases)
                if _contains_term(title, term) or _contains_term(body, term)
            )
            if not matched_terms:
                continue
            domain_matches.append(canonical_keyword)
            terms_by_keyword.setdefault(canonical_keyword, matched_terms)
        if domain_matches:
            matches[domain] = tuple(domain_matches)
    return matches, terms_by_keyword


def match_keyword_terms(title, content, domains, aliases):
    matches, _terms_by_keyword = _match_details(
        title,
        content,
        domains,
        aliases,
    )
    return matches


def assess_keyword_union(title, content, domains, aliases):
    matches, terms_by_keyword = _match_details(
        title,
        content,
        domains,
        aliases,
    )
    if not matches:
        return KeywordAssessment(
            matched=False,
            primary_domain=None,
            matched_keywords=(),
            matched_terms=(),
            reason="标题和完整正文均未命中规范关键词或别名",
        )

    primary_domain = max(
        matches,
        key=lambda domain: len(matches[domain]),
    )
    matched_keywords = tuple(
        keyword
        for domain in domains
        for keyword in matches.get(domain, ())
    )
    matched_terms = tuple(
        dict.fromkeys(
            term
            for keyword in matched_keywords
            for term in terms_by_keyword[keyword]
        )
    )
    return KeywordAssessment(
        matched=True,
        primary_domain=primary_domain,
        matched_keywords=matched_keywords,
        matched_terms=matched_terms,
        reason=(
            f"命中 {len(matched_keywords)} 个规范关键词，"
            f"主目录为 {primary_domain}"
        ),
    )


def keyword_selection_hash(domains, aliases):
    payload = {
        "version": KEYWORD_SELECTION_POLICY_VERSION,
        "domains": [
            {
                "domain": domain,
                "keywords": list(keywords),
            }
            for domain, keywords in domains.items()
        ],
        "aliases": {
            canonical_keyword: list(aliases[canonical_keyword])
            for canonical_keyword in sorted(aliases)
        },
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
