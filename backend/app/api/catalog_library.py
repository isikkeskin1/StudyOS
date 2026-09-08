from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.models.auth import User
from app.models.catalog import CatalogCourse, CatalogFolder
from app.models.course import Course
from app.models.document import Document
from app.schemas.catalog import (
    CatalogCourseRead,
    CatalogFolderCreate,
    CatalogFolderRead,
    CatalogFolderUpdate,
    CatalogLibraryDocumentRead,
    CatalogLibraryRead,
    CatalogPackRequest,
)
from app.services.intelligence import NoProcessedDocumentsError, analyze_course
from app.services.processing import DocumentProcessingError, process_document
from app.services.storage import UnsupportedFileTypeError, UploadTooLargeError, store_upload

router = APIRouter(tags=["institutional library"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user_id


def _require_admin(request: Request, db: Session) -> User:
    user_id = _current_user_id(request)
    user = db.get(User, user_id)
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def _unscoped(db: Session) -> None:
    db.info.pop("user_id", None)


def _catalog(db: Session, catalog_id: str, *, published_only: bool = False) -> CatalogCourse:
    item = db.get(CatalogCourse, catalog_id)
    if item is None or (published_only and not item.published):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog course not found")
    return item


def _catalog_read(db: Session, item: CatalogCourse) -> CatalogCourseRead:
    source = db.get(Course, item.source_course_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Catalog source course is missing")
    count = db.scalar(select(func.count(Document.id)).where(Document.course_id == source.id)) or 0
    return CatalogCourseRead(
        id=item.id,
        source_course_id=item.source_course_id,
        institution_name=item.institution_name,
        institution_code=item.institution_code,
        course_code=item.course_code,
        academic_year=item.academic_year,
        language=item.language,
        description=item.description,
        published=item.published,
        created_at=item.created_at,
        updated_at=item.updated_at,
        name=source.name,
        document_count=int(count),
    )


def _folder(db: Session, item: CatalogCourse, folder_id: str) -> CatalogFolder:
    folder = db.get(CatalogFolder, folder_id)
    if folder is None or folder.catalog_course_id != item.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library folder not found")
    return folder


def _breadcrumbs(db: Session, item: CatalogCourse, current: CatalogFolder | None) -> list[CatalogFolder]:
    chain: list[CatalogFolder] = []
    cursor = current
    seen: set[str] = set()
    while cursor is not None:
        if cursor.id in seen or len(chain) >= 64:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid library folder hierarchy")
        seen.add(cursor.id)
        chain.append(cursor)
        cursor = _folder(db, item, cursor.parent_id) if cursor.parent_id else None
    chain.reverse()
    return chain


def _document_read(document: Document) -> CatalogLibraryDocumentRead:
    return CatalogLibraryDocumentRead(
        id=document.id,
        folder_id=document.catalog_folder_id,
        original_filename=document.original_filename,
        content_type=document.content_type,
        extension=document.extension,
        size_bytes=document.size_bytes,
        status=document.status,
        created_at=document.created_at,
        previewable=document.extension.lower() == ".pdf" or document.content_type == "application/pdf",
    )


def _library(db: Session, item: CatalogCourse, folder_id: str | None) -> CatalogLibraryRead:
    source = db.get(Course, item.source_course_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Catalog source course is missing")
    current = _folder(db, item, folder_id) if folder_id else None
    folders = list(
        db.scalars(
            select(CatalogFolder)
            .where(
                CatalogFolder.catalog_course_id == item.id,
                CatalogFolder.parent_id == (current.id if current else None),
            )
            .order_by(CatalogFolder.name)
        ).all()
    )
    documents = list(
        db.scalars(
            select(Document)
            .where(
                Document.course_id == source.id,
                Document.catalog_folder_id == (current.id if current else None),
                Document.status == "processed",
            )
            .order_by(Document.original_filename)
        ).all()
    )
    return CatalogLibraryRead(
        catalog=_catalog_read(db, item),
        current_folder=current,
        breadcrumbs=_breadcrumbs(db, item, current),
        folders=folders,
        documents=[_document_read(document) for document in documents],
    )


def _catalog_document(db: Session, item: CatalogCourse, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.course_id != item.source_course_id or document.status != "processed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library document not found")
    return document


def _folder_zip_path(db: Session, item: CatalogCourse, document: Document) -> str:
    parts = [Path(document.original_filename).name]
    if document.catalog_folder_id:
        folder = _folder(db, item, document.catalog_folder_id)
        parts = [entry.name for entry in _breadcrumbs(db, item, folder)] + parts
    return "/".join(parts)


@router.get("/catalog/courses/{catalog_id}/library", response_model=CatalogLibraryRead)
def browse_library(
    catalog_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    folder_id: str | None = Query(default=None),
) -> CatalogLibraryRead:
    _current_user_id(request)
    _unscoped(db)
    item = _catalog(db, catalog_id, published_only=True)
    return _library(db, item, folder_id)


@router.get("/admin/catalog/courses/{catalog_id}/library", response_model=CatalogLibraryRead)
def browse_admin_library(
    catalog_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    folder_id: str | None = Query(default=None),
) -> CatalogLibraryRead:
    _require_admin(request, db)
    _unscoped(db)
    return _library(db, _catalog(db, catalog_id), folder_id)


@router.post(
    "/admin/catalog/courses/{catalog_id}/folders",
    response_model=CatalogFolderRead,
    status_code=status.HTTP_201_CREATED,
)
def create_folder(
    catalog_id: str,
    payload: CatalogFolderCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CatalogFolder:
    _require_admin(request, db)
    _unscoped(db)
    item = _catalog(db, catalog_id)
    parent = _folder(db, item, payload.parent_id) if payload.parent_id else None
    name = payload.name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Enter a valid folder name")
    folder = CatalogFolder(catalog_course_id=item.id, parent_id=parent.id if parent else None, name=name)
    db.add(folder)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder with that name already exists here") from exc
    db.refresh(folder)
    return folder


@router.patch(
    "/admin/catalog/courses/{catalog_id}/folders/{folder_id}",
    response_model=CatalogFolderRead,
)
def rename_folder(
    catalog_id: str,
    folder_id: str,
    payload: CatalogFolderUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CatalogFolder:
    _require_admin(request, db)
    _unscoped(db)
    item = _catalog(db, catalog_id)
    folder = _folder(db, item, folder_id)
    name = payload.name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Enter a valid folder name")
    folder.name = name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder with that name already exists here") from exc
    db.refresh(folder)
    return folder


@router.post(
    "/admin/catalog/courses/{catalog_id}/documents",
    response_model=CatalogLibraryDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_library_document(
    catalog_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    folder_id: str | None = Query(default=None),
) -> CatalogLibraryDocumentRead:
    _require_admin(request, db)
    _unscoped(db)
    item = _catalog(db, catalog_id)
    source = db.get(Course, item.source_course_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Catalog source course is missing")
    folder = _folder(db, item, folder_id) if folder_id else None

    settings = request.app.state.settings
    document_id = str(uuid4())
    destination = Path(settings.data_dir) / source.id
    try:
        stored = await store_upload(
            file,
            destination_dir=destination,
            document_id=document_id,
            allowed_extensions=settings.allowed_extensions,
            max_bytes=settings.max_upload_bytes,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_mb} MB upload limit",
        ) from exc

    duplicate = db.scalar(
        select(Document).where(Document.course_id == source.id, Document.sha256 == stored.sha256)
    )
    if duplicate is not None:
        stored.path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This document is already in the institutional course")

    document = Document(
        id=document_id,
        course_id=source.id,
        catalog_folder_id=folder.id if folder else None,
        original_filename=file.filename or f"document{stored.extension}",
        content_type=file.content_type,
        extension=stored.extension,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        storage_path=str(stored.path),
        status="uploaded",
    )
    db.add(document)
    try:
        db.commit()
        db.refresh(document)
        process_document(db, document)
        try:
            analyze_course(db, source.id)
        except NoProcessedDocumentsError:
            pass
    except (IntegrityError, DocumentProcessingError) as exc:
        db.rollback()
        stored.path.unlink(missing_ok=True)
        if isinstance(exc, IntegrityError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This document is already in the institutional course") from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    db.refresh(document)
    return _document_read(document)


@router.get("/catalog/courses/{catalog_id}/documents/{document_id}/file")
def read_library_document(
    catalog_id: str,
    document_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    download: bool = Query(default=False),
):
    _current_user_id(request)
    _unscoped(db)
    item = _catalog(db, catalog_id, published_only=True)
    document = _catalog_document(db, item, document_id)
    path = Path(document.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored library file is missing")
    media_type = document.content_type or "application/octet-stream"
    disposition = "attachment" if download else "inline"
    return FileResponse(path, media_type=media_type, filename=document.original_filename, content_disposition_type=disposition)


@router.get("/admin/catalog/courses/{catalog_id}/documents/{document_id}/file")
def read_admin_library_document(
    catalog_id: str,
    document_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    download: bool = Query(default=False),
):
    _require_admin(request, db)
    _unscoped(db)
    item = _catalog(db, catalog_id)
    document = _catalog_document(db, item, document_id)
    path = Path(document.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored library file is missing")
    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document.original_filename,
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/catalog/courses/{catalog_id}/download-pack")
def download_library_pack(
    catalog_id: str,
    payload: CatalogPackRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    _current_user_id(request)
    _unscoped(db)
    item = _catalog(db, catalog_id, published_only=True)
    selected: list[Document] = []
    seen: set[str] = set()
    for document_id in payload.document_ids:
        if document_id in seen:
            continue
        seen.add(document_id)
        selected.append(_catalog_document(db, item, document_id))

    archive = SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode="w+b")
    used_paths: set[str] = set()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for document in selected:
            path = Path(document.storage_path)
            if not path.is_file():
                continue
            archive_path = _folder_zip_path(db, item, document)
            if archive_path in used_paths:
                base = Path(archive_path)
                archive_path = str(base.with_name(f"{base.stem}-{document.id[:8]}{base.suffix}")).replace("\\", "/")
            used_paths.add(archive_path)
            bundle.write(path, archive_path)
    archive.seek(0)
    safe_name = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in _catalog_read(db, item).name).strip("-") or "studyos-library"
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-pack.zip"'},
        background=BackgroundTask(archive.close),
    )
