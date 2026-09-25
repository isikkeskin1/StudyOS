from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import CatalogCourse, CatalogSource
from app.models.course import Course
from app.models.document import Document
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.intelligence import NoProcessedDocumentsError, analyze_course
from app.services.processing import DocumentProcessingError, process_document

_USER_AGENT = "StudyOS-SourceDiscovery/0.1"
_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md"}
_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_EXT_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
_KIND_RULES = [
    ("past_exam_solution", ("solution", "solutions", "soluzione", "risposta")),
    ("past_exam", ("past exam", "written exam", "exam paper", "esame", "appello")),
    ("exercise", ("exercise", "exercises", "problem set", "tutorial", "esercizi")),
    ("formula_sheet", ("formula", "formulas", "cheat sheet", "reference sheet")),
    ("lecture", ("lecture", "slides", "lesson", "lezione", "dispense")),
    ("syllabus", ("syllabus", "programme", "program", "programma", "course description")),
    ("exam_info", ("exam schedule", "exam rules", "assessment", "grading", "modalita")),
]
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class DiscoveryError(RuntimeError):
    pass


class SourceImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedSource:
    url: str
    content: bytes
    content_type: str | None


class _HtmlCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if lowered == "title":
            self._in_title = True
        if lowered == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif lowered == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.text_parts.append(cleaned)
        if self._in_title:
            self.title_parts.append(cleaned)

    @property
    def title(self) -> str | None:
        value = " ".join(self.title_parts).strip()
        return value[:500] or None

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts)


def _normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise DiscoveryError("Only absolute HTTP(S) source URLs are supported")
    return parsed._replace(scheme=parsed.scheme.lower()).geturl()


def _host_allowed(host: str, allowed_hosts: set[str]) -> bool:
    lowered = host.lower().rstrip(".")
    return any(
        lowered == allowed or lowered.endswith(f".{allowed}")
        for allowed in allowed_hosts
    )


def _validate_public_url(url: str, allowed_hosts: set[str] | None = None) -> str:
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower().rstrip(".")
    if allowed_hosts is not None and not _host_allowed(host, allowed_hosts):
        raise DiscoveryError("Source left the explicitly seeded institution hosts")

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise DiscoveryError(f"Could not resolve source host: {host}") from exc

    if not addresses:
        raise DiscoveryError(f"Could not resolve source host: {host}")

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise DiscoveryError("Source host resolved to a non-public network address")

    return normalized


def _fetch_public(
    client: httpx.Client,
    url: str,
    *,
    allowed_hosts: set[str],
    max_bytes: int = _MAX_DOWNLOAD_BYTES,
) -> FetchedSource:
    current = _validate_public_url(url, allowed_hosts)
    for _redirect in range(4):
        with client.stream("GET", current) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise DiscoveryError("Source returned a redirect without a location")
                current = _validate_public_url(
                    urljoin(current, location),
                    allowed_hosts,
                )
                continue

            if response.status_code >= 400:
                raise DiscoveryError(
                    f"Source returned HTTP {response.status_code}: {current}"
                )

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise DiscoveryError("Source exceeds the discovery download limit")
                chunks.append(chunk)

            content_type = response.headers.get("content-type", "").split(";", 1)[0]
            return FetchedSource(
                url=current,
                content=b"".join(chunks),
                content_type=content_type.lower() or None,
            )

    raise DiscoveryError("Source exceeded the redirect limit")


def _extension(url: str, content_type: str | None) -> str | None:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in _SUPPORTED_EXTENSIONS:
        return suffix
    if content_type in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[content_type]
    return None


def _classify(url: str, title: str | None, text: str = "") -> str:
    haystack = " ".join((url, title or "", text[:3000])).lower()
    for kind, terms in _KIND_RULES:
        if any(term in haystack for term in terms):
            return kind
    if (urlparse(url).path.lower().endswith(tuple(_SUPPORTED_EXTENSIONS))):
        return "course_file"
    return "web_page"


def _parse_html(content: bytes) -> _HtmlCollector:
    parser = _HtmlCollector()
    parser.feed(content.decode("utf-8", errors="replace"))
    return parser


def _source_note(
    *,
    extension: str | None,
    content_type: str | None,
    sha256: str,
    known_hashes: set[str],
) -> tuple[str, str | None]:
    if sha256 in known_hashes:
        return "duplicate", "Same content was already discovered at another URL."
    if content_type in _HTML_TYPES:
        return "candidate", None
    if extension not in _SUPPORTED_EXTENSIONS:
        return "unsupported", "StudyOS cannot import this file type yet."
    return "candidate", None


def discover_catalog_sources(
    db: Session,
    *,
    catalog: CatalogCourse,
    seed_urls: list[str],
    max_depth: int,
    max_sources: int,
) -> list[CatalogSource]:
    normalized_seeds = [_normalize_url(url) for url in seed_urls]
    allowed_hosts = {
        (urlparse(url).hostname or "").lower().rstrip(".")
        for url in normalized_seeds
    }
    for seed in normalized_seeds:
        _validate_public_url(seed, allowed_hosts)

    queue: deque[tuple[str, str | None, int]] = deque(
        (url, None, 0) for url in normalized_seeds
    )
    visited: set[str] = set()
    discovered: list[CatalogSource] = []
    known_hashes = set(
        db.scalars(
            select(CatalogSource.sha256).where(
                CatalogSource.catalog_course_id == catalog.id,
                CatalogSource.sha256.is_not(None),
            )
        ).all()
    )

    with httpx.Client(
        timeout=httpx.Timeout(15.0, connect=7.0),
        headers={"User-Agent": _USER_AGENT, "Accept": "*/*"},
        follow_redirects=False,
    ) as client:
        while queue and len(discovered) < max_sources:
            url, parent_url, depth = queue.popleft()
            try:
                normalized = _normalize_url(url)
            except DiscoveryError:
                continue
            if normalized in visited:
                continue
            visited.add(normalized)

            existing = db.scalar(
                select(CatalogSource).where(
                    CatalogSource.catalog_course_id == catalog.id,
                    CatalogSource.url == normalized,
                )
            )
            if existing is not None:
                continue

            try:
                fetched = _fetch_public(
                    client,
                    normalized,
                    allowed_hosts=allowed_hosts,
                )
            except DiscoveryError as exc:
                source = CatalogSource(
                    catalog_course_id=catalog.id,
                    url=normalized,
                    discovered_from_url=parent_url,
                    source_kind="unreachable",
                    status="failed",
                    depth=depth,
                    discovery_note=str(exc),
                )
                db.add(source)
                db.commit()
                db.refresh(source)
                discovered.append(source)
                continue

            html = fetched.content_type in _HTML_TYPES
            parser = _parse_html(fetched.content) if html else None
            title = parser.title if parser is not None else Path(urlparse(fetched.url).path).name
            text = parser.text if parser is not None else ""
            extension = ".txt" if html else _extension(fetched.url, fetched.content_type)
            sha256 = hashlib.sha256(
                text.encode("utf-8") if html else fetched.content
            ).hexdigest()
            status, note = _source_note(
                extension=extension,
                content_type=fetched.content_type,
                sha256=sha256,
                known_hashes=known_hashes,
            )
            source = CatalogSource(
                catalog_course_id=catalog.id,
                url=fetched.url,
                discovered_from_url=parent_url,
                title=title,
                source_kind=_classify(fetched.url, title, text),
                content_type=fetched.content_type,
                extension=extension,
                status=status,
                depth=depth,
                sha256=sha256,
                discovery_note=note,
            )
            db.add(source)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                continue
            db.refresh(source)
            discovered.append(source)
            known_hashes.add(sha256)

            if parser is None or depth >= max_depth:
                continue
            for href in parser.links:
                absolute = urljoin(fetched.url, href)
                try:
                    normalized_link = _normalize_url(absolute)
                except DiscoveryError:
                    continue
                host = (urlparse(normalized_link).hostname or "").lower().rstrip(".")
                if _host_allowed(host, allowed_hosts):
                    queue.append((normalized_link, fetched.url, depth + 1))

    return discovered


def _safe_filename(source: CatalogSource, extension: str) -> str:
    candidate = source.title or Path(urlparse(source.url).path).name or source.source_kind
    if candidate.lower().endswith(extension):
        candidate = candidate[: -len(extension)]
    cleaned = _SAFE_FILENAME_RE.sub("-", candidate).strip("-._")[:120] or "course-source"
    return f"{cleaned}{extension}"


def import_catalog_source(
    db: Session,
    *,
    catalog: CatalogCourse,
    source: CatalogSource,
    data_dir: Path,
) -> Document:
    course = db.get(Course, catalog.source_course_id)
    if course is None:
        raise SourceImportError("Catalog source course is missing")
    if source.status not in {"approved", "candidate"}:
        raise SourceImportError("Only approved or candidate sources can be imported")

    allowed_hosts = {(urlparse(source.url).hostname or "").lower().rstrip(".")}
    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=7.0),
        headers={"User-Agent": _USER_AGENT, "Accept": "*/*"},
        follow_redirects=False,
    ) as client:
        fetched = _fetch_public(client, source.url, allowed_hosts=allowed_hosts)

    html = fetched.content_type in _HTML_TYPES
    if html:
        parser = _parse_html(fetched.content)
        payload = parser.text.encode("utf-8")
        extension = ".txt"
        content_type = "text/plain"
    else:
        payload = fetched.content
        extension = _extension(fetched.url, fetched.content_type)
        content_type = fetched.content_type

    if extension not in _SUPPORTED_EXTENSIONS:
        raise SourceImportError("This source type is not supported for ingestion")

    digest = hashlib.sha256(payload).hexdigest()
    duplicate = db.scalar(
        select(Document).where(
            Document.course_id == course.id,
            Document.sha256 == digest,
        )
    )
    if duplicate is not None:
        source.status = "duplicate"
        source.sha256 = digest
        source.imported_document_id = duplicate.id
        source.discovery_note = "Matched an already imported course document."
        db.commit()
        return duplicate

    document_id = hashlib.sha256(f"{source.id}:{digest}".encode()).hexdigest()[:36]
    course_dir = data_dir / course.id
    course_dir.mkdir(parents=True, exist_ok=True)
    target_path = course_dir / f"{document_id}{extension}"
    target_path.write_bytes(payload)

    document = Document(
        id=document_id,
        course_id=course.id,
        original_filename=_safe_filename(source, extension),
        content_type=content_type,
        extension=extension,
        size_bytes=len(payload),
        sha256=digest,
        storage_path=str(target_path),
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        process_document(db, document)
    except DocumentProcessingError as exc:
        target_path.unlink(missing_ok=True)
        db.delete(document)
        db.commit()
        raise SourceImportError(str(exc)) from exc

    source.status = "imported"
    source.sha256 = digest
    source.imported_document_id = document.id
    source.discovery_note = None
    db.commit()
    db.refresh(document)
    return document


def import_approved_catalog_sources(
    db: Session,
    *,
    catalog: CatalogCourse,
    data_dir: Path,
) -> list[Document]:
    sources = list(
        db.scalars(
            select(CatalogSource)
            .where(
                CatalogSource.catalog_course_id == catalog.id,
                CatalogSource.status == "approved",
            )
            .order_by(CatalogSource.created_at)
        ).all()
    )
    imported: list[Document] = []
    for source in sources:
        imported.append(
            import_catalog_source(
                db,
                catalog=catalog,
                source=source,
                data_dir=data_dir,
            )
        )

    if imported:
        try:
            analyze_course(db, catalog.source_course_id)
        except NoProcessedDocumentsError:
            return imported
        try:
            analyze_exams(db, catalog.source_course_id)
        except (NoExamDocumentsError, CourseTopicsRequiredError):
            pass

    return imported
