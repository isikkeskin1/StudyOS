from __future__ import annotations

from sqlalchemy import text

from app.core.database import create_database_engine


def test_database_engine_accepts_postgresql_urls_without_sqlite_connect_args(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.core.database.create_engine", fake_create_engine)

    engine = create_database_engine(
        "postgresql+psycopg://studyos:studyos@localhost:5432/studyos"
    )

    assert engine is not None
    assert captured["url"] == (
        "postgresql+psycopg://studyos:studyos@localhost:5432/studyos"
    )
    assert captured["kwargs"] == {"connect_args": {}}


def test_sqlite_engine_still_works(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'database.db'}")
    with engine.connect() as connection:
        assert connection.execute(text("select 1")).scalar_one() == 1
    engine.dispose()
