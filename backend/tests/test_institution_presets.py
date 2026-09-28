from __future__ import annotations

from app.models.catalog import CatalogCourse
from app.services.institution_presets import (
    InstitutionPresetError,
    suggest_catalog_seed_urls,
)


def _catalog(
    *,
    institution_code: str = "POLITO",
    course_code: str = "17AXOXZ",
    academic_year: str | None = "2026/27",
) -> CatalogCourse:
    return CatalogCourse(
        source_course_id="course-id",
        institution_name="Politecnico di Torino",
        institution_code=institution_code,
        course_code=course_code,
        academic_year=academic_year,
        language="English",
        description=None,
        published=False,
        created_by_user_id="admin-id",
    )


def test_polito_seed_preset_generates_exam_and_curriculum_urls() -> None:
    urls, notes = suggest_catalog_seed_urls(
        _catalog(),
        program_code="555",
    )

    assert len(urls) == 2
    assert urls[0].endswith("esami.visu.app?c_cod_ins=17AXOXZ")
    assert "p_cds=555" in urls[1]
    assert "p_coorte=2026" in urls[1]
    assert "p_sdu=37" in urls[1]
    assert len(notes) == 2


def test_polito_seed_preset_works_with_course_code_only() -> None:
    urls, notes = suggest_catalog_seed_urls(
        _catalog(academic_year=None),
    )

    assert urls == [
        "https://didattica.polito.it/pls/portal30/esami.visu.app?c_cod_ins=17AXOXZ"
    ]
    assert len(notes) == 1


def test_seed_preset_rejects_unsupported_institution() -> None:
    try:
        suggest_catalog_seed_urls(
            _catalog(institution_code="OTHER"),
        )
    except InstitutionPresetError as exc:
        assert "POLITO only" in str(exc)
    else:
        raise AssertionError("Unsupported institution was accepted")
