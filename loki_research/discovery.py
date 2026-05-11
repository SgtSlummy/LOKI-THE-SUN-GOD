from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

BLOCKED_TERMS = {
    "malware",
    "phishing",
    "password dump",
    "token grabber",
    "dox",
    "doxxing",
    "exploit kit",
}


@dataclass(frozen=True)
class DiscoveryCandidate:
    title: str
    source_url: str
    summary: str
    reason_for_fit: str
    confidence: float
    safety_status: str


def score_candidate(*, title: str, summary: str, community_terms: list[str]) -> float:
    haystack = f"{title} {summary}".lower()
    if not community_terms:
        return 0.0
    normalized_terms = {_normalize_term(term) for term in community_terms if term.strip()}
    matches = sum(1 for term in normalized_terms if term in haystack or _singularize(term) in haystack)
    return min(1.0, matches / max(1, len(normalized_terms)))


def safety_status(title: str, summary: str, source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "blocked"
    haystack = f"{title} {summary} {source_url}".lower()
    if any(term in haystack for term in BLOCKED_TERMS):
        return "blocked"
    return "pending_review"


def build_candidate(*, title: str, source_url: str, summary: str, community_terms: list[str]) -> DiscoveryCandidate:
    confidence = score_candidate(title=title, summary=summary, community_terms=community_terms)
    haystack = f"{title} {summary}".lower()
    reason = "Matched community interests: " + ", ".join(
        term
        for term in community_terms
        if _normalize_term(term) in haystack or _singularize(_normalize_term(term)) in haystack
    )
    if reason.endswith(": "):
        reason = "No strong community-interest match found."
    return DiscoveryCandidate(
        title=title.strip(),
        source_url=source_url.strip(),
        summary=summary.strip(),
        reason_for_fit=reason,
        confidence=confidence,
        safety_status=safety_status(title, summary, source_url),
    )


def _normalize_term(term: str) -> str:
    return " ".join(term.lower().split())


def _singularize(term: str) -> str:
    return " ".join(word[:-1] if word.endswith("s") and len(word) > 3 else word for word in term.split())
