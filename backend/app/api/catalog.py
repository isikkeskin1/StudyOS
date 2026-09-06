from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.auth import User
from app.models.catalog import CatalogCourse
from app.models.course import Course
from app.models.course_intelligence import CourseAnalysis
from app.models.document import Document
from app.schemas.catalog import CatalogCourseCreate, CatalogCourseRead
from app.schemas.course import CourseRead
from app.services.account_data import delete_course_data
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.intelligence import NoProcessedDocumentsError, analyze_course
from app.services.processing import DocumentProcessingError, process_document

router = APIRouter(tags=["course catalog"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_id


def _require_admin(request: Request, db: Session) -> User:
    user_id = _current_user_id(request)
    user = db.get(User, user_id)
    if user is None or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


def _unscoped(db: Session) -> None:
    db.info.pop("user_id", None)


def _catalog_read(db: Session, item: CatalogCourse) -> CatalogCourseRead:
    source = db.get(Course, item.source_course_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog source course is missing",
        )
    document_count = db.scalar(
        select(func.count(Document.id)).where(Document.course_id == source.id)
    ) or 0
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
        document_count=int(document_count),
    )


@router.post(
    "/admin/catalog/courses",
    response_model=CatalogCourseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_catalog_course(
    payload: CatalogCourseCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CatalogCourseRead:
    admin = _require_admin(request, db)
    course = Course(
        user_id=admin.id,
        name=payload.name,
        max_grade=payload.max_grade,
    )
    db.add(course)
    db.flush()

    catalog = CatalogCourse(
        source_course_id=course.id,
        institution_name=payload.institution_name,
        institution_code=payload.institution_code,
        course_code=payload.course_code,
        academic_year=payload.academic_year,
        language=payload.language,
        description=payload.description,
        published=False,
        created_by_user_id=admin.id,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    return _catalog_read(db, catalog)


@router.get("/admin/catalog/courses", response_model=list[CatalogCourseRead])
def list_admin_catalog_courses(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[CatalogCourseRead]:
    _require_admin(request, db)
    items = list(
        db.scalars(
            select(CatalogCourse).order_by(
                CatalogCourse.institution_name,
                CatalogCourse.course_code,
                CatalogCourse.created_at.desc(),
            )
        ).all()
    )
    return [_catalog_read(db, item) for item in items]


@router.post(
    "/admin/catalog/courses/{catalog_id}/publish",
    response_model=CatalogCourseRead,
)
def publish_catalog_course(
    catalog_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CatalogCourseRead:
    _require_admin(request, db)
    item = db.get(CatalogCourse, catalog_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalog course not found")

    source = db.get(Course, item.source_course_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Catalog source course is missing")

    documents = list(
        db.scalars(select(Document).where(Document.course_id == source.id)).all()
    )
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add course documents before publishing",
        )
    if any(document.status != "processed" for document in documents):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Process every catalog document before publishing",
        )
    if db.get(CourseAnalysis, source.id) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analyze the catalog source course before publishing",
        )

    item.published = True
    db.commit()
    db.refresh(item)
    return _catalog_read(db, item)


@router.post(
    "/admin/catalog/courses/{catalog_id}/unpublish",
    response_model=CatalogCourseRead,
)
def unpublish_catalog_course(
    catalog_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CatalogCourseRead:
    _require_admin(request, db)
    item = db.get(CatalogCourse, catalog_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalog course not found")
    item.published = False
    db.commit()
    db.refresh(item)
    return _catalog_read(db, item)


@router.get("/catalog/courses", response_model=list[CatalogCourseRead])
def list_catalog_courses(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[CatalogCourseRead]:
    _current_user_id(request)
    _unscoped(db)
    items = list(
        db.scalars(
            select(CatalogCourse)
            .where(CatalogCourse.published.is_(True))
            .order_by(
                CatalogCourse.institution_name,
                CatalogCourse.course_code,
                CatalogCourse.created_at.desc(),
            )
        ).all()
    )
    return [_catalog_read(db, item) for item in items]


def _instantiate_catalog_course(
    db: Session,
    *,
    item: CatalogCourse,
    user_id: str,
    data_dir: Path,
) -> Course:
    source = db.get(Course, item.source_course_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Catalog source course is missing")

    source_documents = list(
        db.scalars(
            select(Document)
            .where(
                Document.course_id == source.id,
                Document.status == "processed",
            )
            .order_by(Document.created_at)
        ).all()
    )
    if not source_documents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog course has no processed documents",
        )

    target = Course(
        user_id=user_id,
        name=source.name,
        max_grade=source.max_grade,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    target_dir = data_dir / target.id
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        for source_document in source_documents:
            document_id = str(uuid4())
            suffix = Path(source_document.original_filename).suffix or source_document.extension
            target_path = target_dir / f"{document_id}{suffix}"
            shutil.copy2(Path(source_document.storage_path), target_path)

            document = Document(
                id=document_id,
                course_id=target.id,
                original_filename=source_document.original_filename,
                content_type=source_document.content_type,
                extension=source_document.extension,
                size_bytes=source_document.size_bytes,
                sha256=source_document.sha256,
                storage_path=str(target_path),
                status="uploaded",
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            process_document(db, document)

        analyze_course(db, target.id)
        try:
            analyze_exams(db, target.id)
        except (NoExamDocumentsError, CourseTopicsRequiredError):
            pass
    except (OSError, DocumentProcessingError, NoProcessedDocumentsError) as exc:
        db.rollback()
        delete_course_data(db, target)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not instantiate the catalog course",
        ) from exc

    db.refresh(target)
    return target


@router.post(
    "/catalog/courses/{catalog_id}/enroll",
    response_model=CourseRead,
    status_code=status.HTTP_201_CREATED,
)
def enroll_catalog_course(
    catalog_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Course:
    user_id = _current_user_id(request)
    _unscoped(db)
    item = db.get(CatalogCourse, catalog_id)
    if item is None or not item.published:
        raise HTTPException(status_code=404, detail="Catalog course not found")

    return _instantiate_catalog_course(
        db,
        item=item,
        user_id=user_id,
        data_dir=Path(request.app.state.settings.data_dir),
    )


@router.post(
    "/admin/catalog/courses/{catalog_id}/assign/{user_id}",
    response_model=CourseRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_catalog_course(
    catalog_id: str,
    user_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Course:
    _require_admin(request, db)
    _unscoped(db)

    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    item = db.get(CatalogCourse, catalog_id)
    if item is None or not item.published:
        raise HTTPException(status_code=404, detail="Catalog course not found")

    return _instantiate_catalog_course(
        db,
        item=item,
        user_id=target_user.id,
        data_dir=Path(request.app.state.settings.data_dir),
    )
