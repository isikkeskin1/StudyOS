from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria


class Base(DeclarativeBase):
    pass


class StudyOSSession(Session):
    pass


@event.listens_for(StudyOSSession, "do_orm_execute")
def _scope_tenant_reads(execute_state) -> None:
    if not execute_state.is_select:
        return
    user_id = execute_state.session.info.get("user_id")
    if not user_id:
        return

    from app.models.course import Course
    from app.models.semester_queue import SemesterStudyQueue

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            Course,
            lambda cls: cls.user_id == user_id,
            include_aliases=True,
        ),
        with_loader_criteria(
            SemesterStudyQueue,
            lambda cls: cls.user_id == user_id,
            include_aliases=True,
        ),
    )


def create_database_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=StudyOSSession,
    )


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        session.info["user_id"] = user_id
    try:
        yield session
    finally:
        session.close()
