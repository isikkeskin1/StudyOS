from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.semester_queue import SemesterStudyQueue, SemesterStudyQueueRevision
from app.schemas.emergency_planning import EmergencyPlanRequest
from app.schemas.semester_dashboard import (
    SemesterCourseStatus,
    SemesterDashboardRead,
    SemesterQueueStatus,
)
from app.services.calibration import get_course_calibration
from app.services.emergency_planning import _load_topics
from app.services.planning import _plan_confidence, _weighted_mastery
from app.services.retention import build_review_queue
from app.services.semester_queue import (
    SemesterQueueNotFoundError,
    _block_read,
    _completed_minutes,
    _current_blocks,
    _parse_datetime,
    _source_fingerprint,
)


def _course_status(db: Session, course: Course, now: datetime) -> SemesterCourseStatus:
    days = (course.exam_date - now.date()).days if course.exam_date else None
    pressure = (
        "unknown"
        if days is None
        else "past"
        if days < 0
        else "today"
        if days == 0
        else "soon"
        if days <= 3
        else "upcoming"
        if days <= 7
        else "later"
    )
    topic_ids = set(
        db.scalars(select(CourseTopic.id).where(CourseTopic.course_id == course.id)).all()
    )
    grade = None
    confidence = "low"
    measured_count = 0
    if topic_ids:
        topics, stored, as_of = _load_topics(db, course, EmergencyPlanRequest(available_hours=0.5))
        measured_count = len(topic_ids.intersection(stored))
        confidence = _plan_confidence(topics, stored, as_of)
        if measured_count:
            grade = _weighted_mastery(topics, {t.id: t.mastery for t in topics}) * course.max_grade
    gap = (
        max(0.0, course.target_grade - grade)
        if (grade is not None and course.target_grade is not None)
        else None
    )
    target_status = (
        "unconfigured"
        if course.target_grade is None
        else "unmeasured"
        if grade is None
        else "below_target"
        if gap > 1e-9
        else "at_target"
    )
    calibration = get_course_calibration(db, course.id)
    reviews = build_review_queue(
        db,
        course,
        retention_half_lives={
            t.topic_id: t.retention_half_life_days
            for t in calibration.topics
            if t.retention_half_life_days is not None
        },
        retention_confidences={t.topic_id: t.retention_confidence for t in calibration.topics},
    )
    return SemesterCourseStatus(
        course_id=course.id,
        course_name=course.name,
        exam_date=course.exam_date,
        days_until_exam=days,
        deadline_pressure=pressure,
        target_grade=course.target_grade,
        max_grade=course.max_grade,
        current_estimated_grade=round(grade, 2) if grade is not None else None,
        target_gap=round(gap, 2) if gap is not None else None,
        normalized_target_gap=round(gap / course.max_grade, 5) if gap is not None else None,
        target_status=target_status,
        confidence=confidence,
        topic_count=len(topic_ids),
        measured_topic_count=measured_count,
        due_review_count=reviews.due_topic_count,
    )


def build_semester_dashboard(db: Session, queue_id: str | None = None) -> SemesterDashboardRead:
    now = datetime.now(UTC)
    courses = list(db.scalars(select(Course).order_by(Course.name, Course.id)).all())
    course_rows = [_course_status(db, course, now) for course in courses]
    queues = list(
        db.scalars(
            select(SemesterStudyQueue).order_by(
                SemesterStudyQueue.created_at.desc(), SemesterStudyQueue.id
            )
        ).all()
    )
    if queue_id is not None and not any(q.id == queue_id for q in queues):
        raise SemesterQueueNotFoundError("Semester study queue not found")
    selected = (
        next((q for q in queues if q.id == queue_id), None)
        if queue_id
        else next((q for q in queues if q.status == "active"), None)
    )
    summaries = []
    next_action = None
    existing_topics = set(db.scalars(select(CourseTopic.id)).all())
    existing_courses = {c.id for c in courses}
    for queue in queues:
        blocks = _current_blocks(db, queue)
        unfinished = [b for b in blocks if b.status in {"planned", "in_progress"}]
        revision = db.scalar(
            select(SemesterStudyQueueRevision).where(
                SemesterStudyQueueRevision.queue_id == queue.id,
                SemesterStudyQueueRevision.revision == queue.current_revision,
            )
        )
        reasons = []
        if queue.status == "active":
            if revision is None or revision.source_fingerprint != _source_fingerprint(
                db, queue, now
            ):
                reasons.append("source_change")
            if revision and revision.created_at.date() != now.date():
                reasons.append("daily_refresh")
            if any(
                b.course_id not in existing_courses or b.topic_id not in existing_topics
                for b in unfinished
            ):
                reasons.append("missing_course_or_topic")
            elapsed_minutes = 0
            configs = {c["course_id"]: c for c in queue.course_configs}
            for block in unfinished:
                elapsed_minutes += block.planned_minutes
                deadline = _parse_datetime(configs.get(block.course_id, {}).get("deadline_at"))
                if deadline and (deadline - now).total_seconds() < elapsed_minutes * 60:
                    reasons.append("deadline_no_longer_fits")
                    break
        summaries.append(
            SemesterQueueStatus(
                queue_id=queue.id,
                status=queue.status,
                revision=queue.current_revision,
                remaining_available_minutes=queue.remaining_available_minutes,
                completed_study_minutes=_completed_minutes(db, queue.id),
                needs_refresh=bool(reasons),
                refresh_reasons=reasons,
                planned_minutes=sum(b.planned_minutes for b in unfinished),
            )
        )
        if selected is not None and selected.id == queue.id and queue.status == "active":
            active = next((b for b in unfinished if b.status == "in_progress"), None)
            candidate = active or (unfinished[0] if unfinished and not reasons else None)
            next_action = _block_read(candidate) if candidate else None
    return SemesterDashboardRead(
        generated_at=now,
        course_count=len(course_rows),
        upcoming_exam_count=sum(
            c.days_until_exam is not None and c.days_until_exam >= 0 for c in course_rows
        ),
        below_target_count=sum(c.target_status == "below_target" for c in course_rows),
        unmeasured_course_count=sum(c.measured_topic_count == 0 for c in course_rows),
        due_review_count=sum(c.due_review_count for c in course_rows),
        courses=course_rows,
        queues=summaries,
        selected_queue_id=selected.id if selected else None,
        next_action=next_action,
        assumptions=[
            "Current grades use the existing retention-aware model; unmeasured topics use its "
            "baseline. Courses without measured topics have no grade estimate.",
            "Below-target status describes an estimated gap, not a probability of failing.",
            "Course exam dates provide calendar-day urgency only, not an assumed exam time.",
            "The newest active queue is selected unless queue_id is supplied. Queue budgets "
            "are alternatives and are not added together.",
            "This endpoint is read-only. Refresh stale queues before starting planned work; "
            "in-progress work remains visible. Queue projections are available in queue revisions.",
        ],
    )
