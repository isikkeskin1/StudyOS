from __future__ import annotations

from app.schemas.tutor import TutorCitationRead
from app.services.tutor_entailment import decompose_atomic_claims
from app.services.tutor_provider import TutorDraft, validate_grounded_draft


def _citation(excerpt: str, rank: int = 1) -> TutorCitationRead:
    return TutorCitationRead(
        rank=rank,
        document_id=f"doc-{rank}",
        document_name="physics.txt",
        document_type="lecture",
        chunk_id=f"chunk-{rank}",
        source_label="document",
        locator_type="document",
        locator_index=None,
        source_reference="physics.txt — document",
        excerpt=excerpt,
        relevance_score=0.95,
        lexical_score=0.9,
        topic_affinity=0.0,
        term_coverage=1.0,
        matched_terms=[],
    )


def test_atomic_claim_decomposition_inherits_sentence_citation() -> None:
    claims = decompose_atomic_claims(
        "Net force equals mass times acceleration and acceleration points in the same "
        "direction as the net force [1]."
    )

    assert [claim.text for claim in claims] == [
        "Net force equals mass times acceleration",
        "acceleration points in the same direction as the net force",
    ]
    assert all(claim.citation_ranks == (1,) for claim in claims)


def test_atomic_entailment_accepts_supported_compound_claims() -> None:
    draft = TutorDraft(
        answer=(
            "Net force is equal to mass multiplied by acceleration and acceleration points "
            "in the same direction as the net force [1]."
        ),
        provider="test",
    )
    citation = _citation(
        "Net force equals mass times acceleration. Acceleration points in the same direction "
        "as the net force."
    )

    result = validate_grounded_draft(draft, [citation])

    assert result.status == "passed"
    assert result.model == "atomic-entailment-v1"
    assert result.claim_decomposition_model == "atomic-claims-v1"
    assert result.atomic_claim_count == 2
    assert result.validated_claim_count == 2
    assert result.unsupported_claim_count == 0


def test_atomic_entailment_rejects_direction_and_negation_contradictions() -> None:
    direction = validate_grounded_draft(
        TutorDraft(
            answer="Acceleration points in the opposite direction as the net force [1].",
            provider="test",
        ),
        [_citation("Acceleration points in the same direction as the net force.")],
    )
    negation = validate_grounded_draft(
        TutorDraft(
            answer="Momentum is not conserved in an isolated system [1].",
            provider="test",
        ),
        [_citation("Momentum is conserved in an isolated system.")],
    )

    assert direction.status == "rejected"
    assert direction.contradicted_claim_count == 1
    assert negation.status == "rejected"
    assert negation.contradicted_claim_count == 1


def test_atomic_entailment_rejects_high_overlap_unsupported_addition() -> None:
    result = validate_grounded_draft(
        TutorDraft(
            answer="Net force equals mass times quantum acceleration [1].",
            provider="test",
        ),
        [_citation("Net force equals mass times acceleration.")],
    )

    assert result.status == "rejected"
    assert result.unsupported_addition_count == 1
    assert result.grounding_score > result.minimum_support_score


def test_atomic_entailment_rejects_wrong_number_but_allows_rounding() -> None:
    citation = _citation("Near Earth's surface the gravitational acceleration is 9.81 m/s2.")
    rounded = validate_grounded_draft(
        TutorDraft(
            answer="Near Earth's surface the gravitational acceleration is 9.8 m/s2 [1].",
            provider="test",
        ),
        [citation],
    )
    wrong = validate_grounded_draft(
        TutorDraft(
            answer="Near Earth's surface the gravitational acceleration is 10 m/s2 [1].",
            provider="test",
        ),
        [citation],
    )

    assert rounded.status == "passed"
    assert wrong.status == "rejected"
    assert wrong.numeric_mismatch_claim_count == 1
