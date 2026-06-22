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
from app.models.course_intelligence import (
    CourseAnalysis,
    CourseTopic,
    TopicEvidence,
    TopicRelationship,
)
from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentChunk, DocumentUnit
from app.schemas.course import CourseCreate, CourseRead
from app.schemas.course_setup import CourseSetupRead
from app.schemas.document import (
    DocumentAnalysisRead,
    DocumentChunkRead,
    DocumentContentRead,
    DocumentRead,
    DocumentUnitRead,
)
from app.schemas.intelligence import (
    CourseAnalysisRead,
    CourseIntelligenceRead,
    CourseTopicRead,
    TopicEvidenceRead,
    TopicRelationshipRead,
)
from app.services.course_setup import course_setup_status
from app.services.intelligence import NoProcessedDocumentsError, analyze_course
from app.services.processing import DocumentProcessingError, process_document
from app.services.storage import (
    UnsupportedFileTypeError,
    UploadTooLargeError,
    store_upload,
)

router = APIRouter(prefix="/courses", tags=["courses"])


def _get_course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _get_course_document(db: Session, course_id: str, document_id: str) -> Document:
    _get_course(db, course_id)
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


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


@router.get("/{course_id}/setup", response_model=CourseSetupRead)
def get_course_setup(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CourseSetupRead:
    course = _get_course(db, course_id)
    return CourseSetupRead.model_validate(course_setup_status(db, course), from_attributes=True)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, db: Annotated[Session, Depends(get_db)]) -> Course:
    return _get_course(db, course_id)


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
    _get_course(db, course_id)

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
    _get_course(db, course_id)
    return list(
        db.scalars(
            select(Document)
            .where(Document.course_id == course_id)
            .order_by(Document.created_at.desc())
        ).all()
    )


@router.get("/{course_id}/documents/{document_id}", response_model=DocumentRead)
def get_document(
    course_id: str,
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return _get_course_document(db, course_id, document_id)


@router.post(
    "/{course_id}/documents/{document_id}/process",
    response_model=DocumentAnalysisRead,
)
def process_uploaded_document(
    course_id: str,
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentAnalysis:
    document = _get_course_document(db, course_id, document_id)
    try:
        return process_document(db, document)
    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{course_id}/documents/{document_id}/content",
    response_model=DocumentContentRead,
)
def get_document_content(
    course_id: str,
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentContentRead:
    document = _get_course_document(db, course_id, document_id)
    analysis = db.get(DocumentAnalysis, document_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has not been processed",
        )

    units = list(
        db.scalars(
            select(DocumentUnit)
            .where(DocumentUnit.document_id == document_id)
            .order_by(DocumentUnit.unit_index)
        ).all()
    )
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()
    )

    return DocumentContentRead(
        document=DocumentRead.model_validate(document),
        analysis=DocumentAnalysisRead.model_validate(analysis),
        units=[DocumentUnitRead.model_validate(unit) for unit in units],
        chunks=[DocumentChunkRead.model_validate(chunk) for chunk in chunks],
    )


def _read_course_intelligence(db: Session, course_id: str) -> CourseIntelligenceRead:
    analysis = db.get(CourseAnalysis, course_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Course has not been analyzed",
        )

    topics = list(
        db.scalars(
            select(CourseTopic)
            .where(CourseTopic.course_id == course_id)
            .order_by(CourseTopic.importance_score.desc(), CourseTopic.name)
        ).all()
    )
    topic_ids = [topic.id for topic in topics]

    evidence_by_topic: dict[str, list[TopicEvidence]] = {topic_id: [] for topic_id in topic_ids}
    if topic_ids:
        for evidence in db.scalars(
            select(TopicEvidence)
            .where(TopicEvidence.topic_id.in_(topic_ids))
            .order_by(TopicEvidence.evidence_score.desc())
        ).all():
            evidence_by_topic[evidence.topic_id].append(evidence)

    topic_name_by_id = {topic.id: topic.name for topic in topics}
    relationships = list(
        db.scalars(
            select(TopicRelationship)
            .where(TopicRelationship.course_id == course_id)
            .order_by(
                TopicRelationship.cooccurrence_count.desc(),
                TopicRelationship.weight.desc(),
            )
        ).all()
    )

    return CourseIntelligenceRead(
        analysis=CourseAnalysisRead.model_validate(analysis),
        topics=[
            CourseTopicRead(
                id=topic.id,
                name=topic.name,
                normalized_name=topic.normalized_name,
                importance_score=topic.importance_score,
                mention_count=topic.mention_count,
                document_count=topic.document_count,
                exam_mention_count=topic.exam_mention_count,
                lecture_mention_count=topic.lecture_mention_count,
                evidence=[
                    TopicEvidenceRead.model_validate(evidence)
                    for evidence in evidence_by_topic[topic.id]
                ],
            )
            for topic in topics
        ],
        relationships=[
            TopicRelationshipRead(
                source_topic_id=relationship.source_topic_id,
                source_topic_name=topic_name_by_id[relationship.source_topic_id],
                target_topic_id=relationship.target_topic_id,
                target_topic_name=topic_name_by_id[relationship.target_topic_id],
                cooccurrence_count=relationship.cooccurrence_count,
                weight=relationship.weight,
            )
            for relationship in relationships
        ],
    )


@router.post("/{course_id}/analyze", response_model=CourseIntelligenceRead)
def analyze_course_documents(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CourseIntelligenceRead:
    _get_course(db, course_id)
    try:
        analyze_course(db, course_id)
    except NoProcessedDocumentsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _read_course_intelligence(db, course_id)


@router.get("/{course_id}/intelligence", response_model=CourseIntelligenceRead)
def get_course_intelligence(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CourseIntelligenceRead:
    _get_course(db, course_id)
    return _read_course_intelligence(db, course_id)
