from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.auth import User
from app.models.catalog import CatalogCourse, CatalogSource
from app.models.course import Course
from app.models.document import Document
from app.services.account_data import delete_course_data
from app.services.intelligence import NoProcessedDocumentsError, analyze_course

router = APIRouter(tags=["catalog administration"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_id


def _require_admin(request: Request, db: Session) -> User:
    user = db.get(User, _current_user_id(request))
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


def _unscoped(db: Session) -> None:
    db.info.pop("user_id", None)


def _catalog(db: Session, catalog_id: str) -> CatalogCourse:
    item = db.get(CatalogCourse, catalog_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalog course not found",
        )
    return item


@router.delete(
    "/admin/catalog/courses/{catalog_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_catalog_course(
    catalog_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Permanently remove an institutional master course and its owned data.

    Student courses already instantiated from the catalog are independent copies and are
    deliberately not removed.
    """
    _require_admin(request, db)
    _unscoped(db)
    item = _catalog(db, catalog_id)
    source = db.get(Course, item.source_course_id)
    if source is None:
        db.delete(item)
        db.commit()
        return
    delete_course_data(db, source)


@router.delete(
    "/admin/catalog/courses/{catalog_id}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_catalog_source(
    catalog_id: str,
    source_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Remove one discovered source without deleting an imported course document."""
    _require_admin(request, db)
    _unscoped(db)
    _catalog(db, catalog_id)
    source = db.get(CatalogSource, source_id)
    if source is None or source.catalog_course_id != catalog_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalog source not found",
        )
    db.delete(source)
    db.commit()


@router.delete(
    "/admin/catalog/courses/{catalog_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_catalog_document(
    catalog_id: str,
    document_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Remove one institutional document while preserving the master course itself."""
    _require_admin(request, db)
    _unscoped(db)
    item = _catalog(db, catalog_id)
    document = db.get(Document, document_id)
    if document is None or document.course_id != item.source_course_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Library document not found",
        )

    storage_path = Path(document.storage_path)
    linked_sources = list(
        db.scalars(
            select(CatalogSource).where(
                CatalogSource.catalog_course_id == item.id,
                CatalogSource.imported_document_id == document.id,
            )
        ).all()
    )
    for source in linked_sources:
        source.imported_document_id = None
        if source.status == "imported":
            source.status = "approved"

    db.delete(document)
    db.commit()
    storage_path.unlink(missing_ok=True)

    remaining_processed = db.scalar(
        select(func.count(Document.id)).where(
            Document.course_id == item.source_course_id,
            Document.status == "processed",
        )
    ) or 0

    if remaining_processed == 0:
        if item.published:
            item.published = False
            db.commit()
        return

    try:
        analyze_course(db, item.source_course_id)
    except NoProcessedDocumentsError:
        if item.published:
            item.published = False
            db.commit()
