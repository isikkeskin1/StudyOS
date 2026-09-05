from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.cheat_sheet import CheatSheet
from app.models.course import Course
from app.schemas.cheat_sheet import CheatSheetGenerateRequest, CheatSheetRead
from app.services.cheat_sheet import (
    CheatSheetUnavailable,
    generate_cheat_sheet,
    read_cheat_sheet,
)

router = APIRouter(prefix="/courses/{course_id}/cheat-sheets", tags=["cheat sheets"])


def _course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _sheet(db: Session, course_id: str, sheet_id: str) -> CheatSheet:
    row = db.get(CheatSheet, sheet_id)
    if row is None or row.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cheat sheet not found")
    return row


@router.post("", response_model=CheatSheetRead, status_code=status.HTTP_201_CREATED)
def create_cheat_sheet(
    course_id: str,
    payload: CheatSheetGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CheatSheetRead:
    course = _course(db, course_id)
    try:
        return read_cheat_sheet(generate_cheat_sheet(db, course, payload))
    except CheatSheetUnavailable as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=list[CheatSheetRead])
def list_cheat_sheets(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[CheatSheetRead]:
    _course(db, course_id)
    rows = db.scalars(
        select(CheatSheet)
        .where(CheatSheet.course_id == course_id)
        .order_by(CheatSheet.generated_at.desc())
    ).all()
    return [read_cheat_sheet(row) for row in rows]


@router.get("/{sheet_id}", response_model=CheatSheetRead)
def get_cheat_sheet(
    course_id: str,
    sheet_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CheatSheetRead:
    _course(db, course_id)
    return read_cheat_sheet(_sheet(db, course_id, sheet_id))
