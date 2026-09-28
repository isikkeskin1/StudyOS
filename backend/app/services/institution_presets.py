from __future__ import annotations

import re
from urllib.parse import urlencode

from app.models.catalog import CatalogCourse

_POLITO_CODE_RE = re.compile(r"^[0-9A-Z]{5,12}$")


class InstitutionPresetError(ValueError):
    pass


def _academic_year_start(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})", value)
    return int(match.group(1)) if match else None


def suggest_catalog_seed_urls(
    catalog: CatalogCourse,
    *,
    program_code: str | None = None,
    cohort_year: int | None = None,
) -> tuple[list[str], list[str]]:
    institution_code = (catalog.institution_code or "").strip().upper()
    if institution_code != "POLITO":
        raise InstitutionPresetError(
            "Automatic official seed suggestions are currently available for POLITO only"
        )

    course_code = (catalog.course_code or "").strip().upper()
    if not course_code:
        raise InstitutionPresetError("Add a Politecnico di Torino course code first")
    if not _POLITO_CODE_RE.fullmatch(course_code):
        raise InstitutionPresetError("The POLITO course code format is not valid")

    urls = [
        (
            "https://didattica.polito.it/pls/portal30/esami.visu.app?"
            + urlencode({"c_cod_ins": course_code})
        )
    ]
    notes = [
        "Official Politecnico di Torino exam schedule and assessment-type page."
    ]

    resolved_cohort = cohort_year or _academic_year_start(catalog.academic_year)
    normalized_program = (program_code or "").strip()
    if normalized_program and resolved_cohort:
        if not normalized_program.isdigit():
            raise InstitutionPresetError("POLITO degree-program code must be numeric")
        urls.append(
            "https://didattica.polito.it/pls/portal30/"
            "sviluppo.offerta_formativa_2019.vis?"
            + urlencode(
                {
                    "p_cds": normalized_program,
                    "p_coorte": resolved_cohort,
                    "p_sdu": 37,
                }
            )
        )
        notes.append(
            "Official Politecnico di Torino curriculum/teaching-plan page for the "
            "selected degree program and cohort."
        )

    return urls, notes
