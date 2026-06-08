from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.schemas.tutor import TutorCitationRead

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?")
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
_PREDICATE_PATTERN = re.compile(
    r"\b(?:is|are|was|were|equals?|states?|means?|causes?|produces?|points?|"
    r"remains?|increases?|decreases?|gives?|has|have|must|can|will|should|"
    r"occurs?|depends?|varies?|changes?|becomes?|moves?|acts?|relates?|"
    r"corresponds?|conserves?|conserved)\b",
    re.IGNORECASE,
)
_NEGATION_PATTERN = re.compile(
    r"\b(?:not|never|no|cannot|can't|doesn't|isn't|aren't|wasn't|weren't|without)\b",
    re.IGNORECASE,
)
_DISCOURSE_PREFIX = re.compile(
    r"^(?:from your course material|exam-focused explanation)\s*:\s*",
    re.IGNORECASE,
)

VALIDATION_MODEL = "atomic-entailment-v1"
CLAIM_DECOMPOSITION_MODEL = "atomic-claims-v1"
MINIMUM_SUPPORT_SCORE = 0.35

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "by",
    "can",
    "course",
    "do",
    "does",
    "exam",
    "explanation",
    "for",
    "focused",
    "from",
    "in",
    "into",
    "is",
    "it",
    "material",
    "of",
    "on",
    "or",
    "that",
    "the",
    "then",
    "therefore",
    "this",
    "thus",
    "to",
    "was",
    "were",
    "will",
    "with",
    "your",
}

_TERM_ALIASES = {
    "accelerations": "acceleration",
    "decreased": "decrease",
    "decreases": "decrease",
    "decreasing": "decrease",
    "directed": "point",
    "directions": "direction",
    "equaled": "equal",
    "equals": "equal",
    "equivalent": "equal",
    "falls": "decrease",
    "falling": "decrease",
    "fixed": "constant",
    "forces": "force",
    "greater": "greater",
    "higher": "greater",
    "increased": "increase",
    "increases": "increase",
    "increasing": "increase",
    "larger": "greater",
    "less": "less",
    "lower": "less",
    "masses": "mass",
    "multiplied": "multiply",
    "multiplies": "multiply",
    "opposes": "oppose",
    "pointing": "point",
    "points": "point",
    "remained": "remain",
    "remains": "remain",
    "resultant": "net",
    "rises": "increase",
    "rising": "increase",
    "smaller": "less",
    "stays": "remain",
    "times": "multiply",
    "unchanged": "constant",
}

_SAFE_NOVEL_TERMS = {
    "according",
    "equation",
    "law",
    "principle",
    "relation",
    "relationship",
    "quantity",
    "value",
}

_POLARITY_PAIRS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("same direction", "same sense"), ("opposite direction", "opposite sense")),
    (("positive",), ("negative",)),
    (
        ("greater than", "larger than", "higher than"),
        ("less than", "smaller than", "lower than"),
    ),
    (("increase", "increases", "rises"), ("decrease", "decreases", "falls")),
    (
        ("directly proportional", "direct proportion"),
        ("inversely proportional", "inverse proportion"),
    ),
    (("clockwise",), ("counterclockwise", "anticlockwise")),
    (("upward", "upwards"), ("downward", "downwards")),
)


@dataclass(frozen=True)
class AtomicClaim:
    text: str
    citation_ranks: tuple[int, ...]


@dataclass(frozen=True)
class ClaimVerdict:
    claim: AtomicClaim
    status: str
    support_score: float
    reason: str


@dataclass(frozen=True)
class TutorEntailmentValidation:
    status: str
    model: str
    claim_decomposition_model: str
    atomic_claim_count: int
    validated_claim_count: int
    unsupported_claim_count: int
    contradicted_claim_count: int
    unsupported_addition_count: int
    numeric_mismatch_claim_count: int
    invalid_citation_claim_count: int
    citation_coverage: float
    grounding_score: float
    minimum_support_score: float


def _canonical_term(token: str) -> str:
    normalized = token.lower().replace("’", "'")
    return _TERM_ALIASES.get(normalized, normalized)


def _support_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(text):
        term = _canonical_term(match.group(0))
        if term in _STOPWORDS or len(term) <= 1:
            continue
        terms.add(term)
    return terms


def _looks_like_clause(text: str) -> bool:
    return len(_support_terms(text)) >= 2 and bool(_PREDICATE_PATTERN.search(text))


def _split_independent_and_clauses(text: str) -> list[str]:
    items = [text]
    changed = True
    while changed:
        changed = False
        next_items: list[str] = []
        for item in items:
            split = False
            for match in re.finditer(r"\s+and\s+", item, re.IGNORECASE):
                left = item[: match.start()].strip(" ,")
                right = item[match.end() :].strip(" ,")
                if _looks_like_clause(left) and _looks_like_clause(right):
                    next_items.extend([left, right])
                    changed = True
                    split = True
                    break
            if not split:
                next_items.append(item)
        items = next_items
    return items


def _split_atomic_text(text: str) -> list[str]:
    coarse = re.split(
        r"\s*;\s*|\s+(?:but|whereas|however)\s+",
        text,
        flags=re.IGNORECASE,
    )
    claims: list[str] = []
    for part in coarse:
        clean = part.strip(" ,")
        if not clean:
            continue
        claims.extend(_split_independent_and_clauses(clean))
    return claims


def decompose_atomic_claims(answer: str) -> list[AtomicClaim]:
    claims: list[AtomicClaim] = []
    for sentence in _SENTENCE_SPLIT.split(answer):
        clean_sentence = sentence.strip()
        if not clean_sentence:
            continue
        ranks = tuple(
            sorted({int(value) for value in _CITATION_PATTERN.findall(clean_sentence)})
        )
        plain = _CITATION_PATTERN.sub("", clean_sentence)
        plain = _DISCOURSE_PREFIX.sub("", plain).strip(" .")
        if len(_support_terms(plain)) < 2:
            continue
        for text in _split_atomic_text(plain):
            clean = text.strip(" .")
            if len(_support_terms(clean)) >= 2:
                claims.append(AtomicClaim(text=clean, citation_ranks=ranks))
    return claims


def _normalized_text(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _polarity_contradiction(claim: str, excerpts: list[str]) -> bool:
    normalized_claim = _normalized_text(claim)
    for excerpt in excerpts:
        normalized_excerpt = _normalized_text(excerpt)
        for positive, negative in _POLARITY_PAIRS:
            claim_positive = _contains_any(normalized_claim, positive)
            claim_negative = _contains_any(normalized_claim, negative)
            evidence_positive = _contains_any(normalized_excerpt, positive)
            evidence_negative = _contains_any(normalized_excerpt, negative)
            if claim_positive and evidence_negative and not evidence_positive:
                return True
            if claim_negative and evidence_positive and not evidence_negative:
                return True
    return False


def _has_negation(text: str) -> bool:
    without_not_only = re.sub(r"\bnot only\b", "", text, flags=re.IGNORECASE)
    return bool(_NEGATION_PATTERN.search(without_not_only))


def _negation_contradiction(claim: str, excerpts: list[str]) -> bool:
    claim_terms = _support_terms(claim)
    comparable: list[bool] = []
    for excerpt in excerpts:
        evidence_terms = _support_terms(excerpt)
        overlap = len(claim_terms & evidence_terms)
        ratio = overlap / max(1, len(claim_terms))
        if overlap >= 2 and ratio >= 0.55:
            comparable.append(_has_negation(excerpt))
    if not comparable:
        return False
    claim_negated = _has_negation(claim)
    if any(evidence_negated == claim_negated for evidence_negated in comparable):
        return False
    return any(evidence_negated != claim_negated for evidence_negated in comparable)


def _numbers(text: str) -> set[float]:
    values: set[float] = set()
    for token in _NUMBER_PATTERN.findall(text):
        try:
            value = float(token)
        except ValueError:
            continue
        if math.isfinite(value):
            values.add(value)
    return values


def _numbers_supported(claim: str, excerpts: list[str]) -> bool:
    claim_numbers = _numbers(claim)
    if not claim_numbers:
        return True
    evidence_numbers = _numbers(" ".join(excerpts))
    if not evidence_numbers:
        return False
    for claim_value in claim_numbers:
        matched = False
        for evidence_value in evidence_numbers:
            tolerance = max(1e-9, abs(evidence_value) * 0.005)
            if abs(claim_value - evidence_value) <= tolerance:
                matched = True
                break
        if not matched:
            return False
    return True


def _claim_support(
    claim: str,
    excerpts: list[str],
    minimum_support_score: float,
) -> tuple[str, float, str]:
    if _polarity_contradiction(claim, excerpts):
        return "contradicted", 0.0, "The claim reverses a directional or comparative relation."
    if _negation_contradiction(claim, excerpts):
        return "contradicted", 0.0, "The claim reverses the evidence's negation polarity."
    if not _numbers_supported(claim, excerpts):
        return "numeric_mismatch", 0.0, "A numerical value is not supported by the cited evidence."

    claim_terms = _support_terms(claim)
    evidence_terms: set[str] = set()
    for excerpt in excerpts:
        evidence_terms.update(_support_terms(excerpt))
    if not claim_terms:
        return "supported", 1.0, "No substantive terms required validation."

    overlap_terms = claim_terms & evidence_terms
    support_score = len(overlap_terms) / len(claim_terms)
    minimum_overlap = 1 if len(claim_terms) <= 2 else 2
    if len(overlap_terms) < minimum_overlap or support_score < minimum_support_score:
        return (
            "unsupported",
            support_score,
            "The cited evidence does not cover enough of the claim.",
        )

    novel_terms = claim_terms - evidence_terms - _SAFE_NOVEL_TERMS
    if novel_terms:
        return (
            "unsupported_addition",
            support_score,
            "The claim adds substantive content absent from the cited evidence.",
        )
    return "supported", support_score, "The cited evidence covers the atomic claim."


def validate_atomic_grounding(
    answer: str,
    citations: list[TutorCitationRead],
    minimum_support_score: float = MINIMUM_SUPPORT_SCORE,
) -> TutorEntailmentValidation:
    citation_by_rank = {citation.rank: citation for citation in citations}
    claims = decompose_atomic_claims(answer)
    verdicts: list[ClaimVerdict] = []

    for claim in claims:
        if not claim.citation_ranks or not set(claim.citation_ranks).issubset(citation_by_rank):
            verdicts.append(
                ClaimVerdict(
                    claim=claim,
                    status="invalid_citation",
                    support_score=0.0,
                    reason="The claim has no valid citation.",
                )
            )
            continue
        excerpts = [citation_by_rank[rank].excerpt for rank in claim.citation_ranks]
        status, score, reason = _claim_support(
            claim.text,
            excerpts,
            minimum_support_score,
        )
        verdicts.append(
            ClaimVerdict(
                claim=claim,
                status=status,
                support_score=score,
                reason=reason,
            )
        )

    supported = sum(verdict.status == "supported" for verdict in verdicts)
    contradicted = sum(verdict.status == "contradicted" for verdict in verdicts)
    additions = sum(verdict.status == "unsupported_addition" for verdict in verdicts)
    numeric_mismatches = sum(verdict.status == "numeric_mismatch" for verdict in verdicts)
    invalid_citations = sum(verdict.status == "invalid_citation" for verdict in verdicts)
    unsupported = len(verdicts) - supported
    coverage = supported / len(verdicts) if verdicts else 0.0
    grounding_score = (
        sum(verdict.support_score for verdict in verdicts) / len(verdicts)
        if verdicts
        else 0.0
    )
    status = "passed" if verdicts and unsupported == 0 else "rejected"

    return TutorEntailmentValidation(
        status=status,
        model=VALIDATION_MODEL,
        claim_decomposition_model=CLAIM_DECOMPOSITION_MODEL,
        atomic_claim_count=len(verdicts),
        validated_claim_count=supported,
        unsupported_claim_count=unsupported,
        contradicted_claim_count=contradicted,
        unsupported_addition_count=additions,
        numeric_mismatch_claim_count=numeric_mismatches,
        invalid_citation_claim_count=invalid_citations,
        citation_coverage=round(coverage, 4),
        grounding_score=round(grounding_score, 4),
        minimum_support_score=minimum_support_score,
    )
