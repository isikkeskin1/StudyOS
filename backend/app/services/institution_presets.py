from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx

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


def discover_polito_official_seeds(
    catalog: CatalogCourse,
    *,
    timeout_seconds: float = 12.0,
) -> tuple[list[str], list[str]]:
    """Resolve useful official POLITO seeds from only the catalog course metadata.

    The exam endpoint is deterministic from the teaching code. Its returned HTML often
    links or names the relevant teaching/curriculum surfaces, which the normal bounded
    catalog crawler can then follow. This intentionally does not use a search engine or
    scrape third-party indexes.
    """
    urls, notes = suggest_catalog_seed_urls(catalog)
    exam_url = urls[0]

    try:
        response = httpx.get(
            exam_url,
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "StudyOS/0.51 institutional-course-discovery"},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return urls, notes

    official_links = re.findall(
        r"""href=["']([^"'#]+)["']""",
        response.text,
        flags=re.IGNORECASE,
    )
    for link in official_links:
        if link.startswith("/"):
            link = "https://didattica.polito.it" + link
        if not link.startswith("https://didattica.polito.it/"):
            continue
        lowered = link.lower()
        if not any(
            token in lowered
            for token in (
                "offerta_formativa",
                "insegnamento",
                "teaching",
                "programma",
                "scheda",
            )
        ):
            continue
        if link not in urls:
            urls.append(link)
            notes.append(
                "Official Politecnico di Torino teaching/curriculum link discovered "
                "from the course exam surface."
            )
        if len(urls) >= 6:
            break

    return urls, notes
