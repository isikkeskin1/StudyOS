from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    document_type: str
    confidence: float


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def classify_document(filename: str, text_sample: str) -> Classification:
    filename_text = filename.lower().replace("_", " ").replace("-", " ")
    body = text_sample[:12000].lower()
    combined = f"{filename_text}\n{body}"

    exam_terms = ("exam", "midterm", "final", "written test", "past paper")
    solution_terms = ("solution", "solutions", "answer key", "worked answers")

    if _contains_any(combined, exam_terms) and _contains_any(combined, solution_terms):
        return Classification("past_exam_solution", 0.95)

    rules: tuple[tuple[str, tuple[str, ...], float], ...] = (
        ("syllabus", ("syllabus", "course outline", "learning outcomes"), 0.92),
        ("past_exam", exam_terms, 0.90),
        ("lecture", ("lecture", "slides", "week ", "lesson "), 0.86),
        ("exercise_sheet", ("exercise sheet", "problem set", "worksheet", "tutorial sheet"), 0.88),
        ("notes", ("notes", "revision notes", "study notes"), 0.82),
        ("textbook", ("textbook", "chapter ", "isbn"), 0.78),
        ("solution", solution_terms, 0.84),
    )

    for document_type, terms, confidence in rules:
        if _contains_any(filename_text, terms):
            return Classification(document_type, confidence)

    for document_type, terms, confidence in rules:
        if _contains_any(body, terms):
            return Classification(document_type, round(confidence - 0.12, 2))

    return Classification("unknown", 0.2)
