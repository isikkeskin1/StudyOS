from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.document import Document
from app.schemas.course import CourseCreate, CourseRead
from app.schemas.document import DocumentRead
from app.services.storage import (
    UnsupportedFileTypeError,
    UploadTooLargeError,
    store_upload,
)

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: Annotated[Session, Depends(get_db)]) -> Course:
    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("", response_model=list[CourseRead])
def list_courses(db: Annotated[Session, Depends(get_db)]) -> list[Course]:
    return list(db.scalars(select(Course).order_by(Course.created_at.desc())).all())


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, db: Annotated[Session, Depends(get_db)]) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.post(
    "/{course_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    course_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    settings = request.app.state.settings
    document_id = str(uuid4())
    course_dir = Path(settings.data_dir) / course_id

    try:
        stored = await store_upload(
            file,
            destination_dir=course_dir,
            document_id=document_id,
            allowed_extensions=settings.allowed_extensions,
            max_bytes=settings.max_upload_bytes,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_mb} MB upload limit",
        ) from exc

    duplicate = db.scalar(
        select(Document).where(
            Document.course_id == course_id,
            Document.sha256 == stored.sha256,
        )
    )
    if duplicate is not None:
        stored.path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been uploaded to the course",
        )

    document = Document(
        id=document_id,
        course_id=course_id,
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
    except IntegrityError as exc:
        db.rollback()
        stored.path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been uploaded to the course",
        ) from exc

    db.refresh(document)
    return document


@router.get("/{course_id}/documents", response_model=list[DocumentRead])
def list_documents(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    return list(
        db.scalars(
            select(Document)
            .where(Document.course_id == course_id)
            .order_by(Document.created_at.desc())
        ).all()
    )
