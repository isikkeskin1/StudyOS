from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Table, and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.auth import User

_REDACTED_COLUMN_FRAGMENTS = ("password", "secret", "token")
_REDACTED_COLUMNS = {"auth", "p256dh", "storage_path"}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def _is_exportable_column(name: str) -> bool:
    lowered = name.lower()
    if lowered in _REDACTED_COLUMNS:
        return False
    return not any(fragment in lowered for fragment in _REDACTED_COLUMN_FRAGMENTS)


def _collect_owned_rows(db: Session, user_id: str) -> dict[str, list[dict[str, Any]]]:
    tables = list(Base.metadata.sorted_tables)
    owned: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: dict[str, set[tuple[Any, ...]]] = defaultdict(set)

    referenced_columns = {
        (foreign_key.column.table.name, foreign_key.column.name)
        for table in tables
        for column in table.columns
        for foreign_key in column.foreign_keys
    }
    values: dict[tuple[str, str], set[Any]] = defaultdict(set)
    values[("users", "id")].add(user_id)

    changed = True
    while changed:
        changed = False
        for table in tables:
            if table.name == "users":
                continue

            predicates = []
            if "user_id" in table.c:
                predicates.append(table.c.user_id == user_id)

            for column in table.columns:
                for foreign_key in column.foreign_keys:
                    parent_key = (
                        foreign_key.column.table.name,
                        foreign_key.column.name,
                    )
                    parent_values = values.get(parent_key)
                    if parent_values:
                        predicates.append(column.in_(parent_values))

            if not predicates:
                continue

            rows = db.execute(select(table).where(or_(*predicates))).mappings().all()
            primary_keys = list(table.primary_key.columns)
            for row in rows:
                identity = tuple(row[column.name] for column in primary_keys)
                if identity in seen[table.name]:
                    continue
                seen[table.name].add(identity)
                materialized = dict(row)
                owned[table.name].append(materialized)
                changed = True

                for column in table.columns:
                    key = (table.name, column.name)
                    if key not in referenced_columns:
                        continue
                    value = materialized.get(column.name)
                    if value is not None:
                        values[key].add(value)

    return dict(owned)


def export_user_data(db: Session, user: User) -> dict[str, Any]:
    owned = _collect_owned_rows(db, user.id)
    exported_tables: dict[str, list[dict[str, Any]]] = {}

    for table_name, rows in sorted(owned.items()):
        if table_name == "auth_sessions":
            continue
        exported_rows = []
        for row in rows:
            exported_rows.append(
                {
                    key: _json_value(value)
                    for key, value in row.items()
                    if _is_exportable_column(key)
                }
            )
        exported_tables[table_name] = exported_rows

    return {
        "format": "studyos-account-export-v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat(),
        },
        "source_files_included": False,
        "tables": exported_tables,
    }


def delete_user_data(db: Session, user: User) -> list[Path]:
    owned = _collect_owned_rows(db, user.id)
    storage_paths = [
        Path(str(row["storage_path"]))
        for row in owned.get("documents", [])
        if row.get("storage_path")
    ]

    tables_by_name = {table.name: table for table in Base.metadata.sorted_tables}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "users":
            continue
        rows = owned.get(table.name)
        if not rows:
            continue
        _delete_rows(db, table, rows)

    db.execute(delete(User.__table__).where(User.__table__.c.id == user.id))
    db.commit()

    for path in storage_paths:
        path.unlink(missing_ok=True)
        parent = path.parent
        try:
            parent.rmdir()
        except OSError:
            pass

    return storage_paths


def _delete_rows(db: Session, table: Table, rows: list[dict[str, Any]]) -> None:
    primary_keys = list(table.primary_key.columns)
    if not primary_keys:
        return

    row_predicates = [
        and_(*(column == row[column.name] for column in primary_keys))
        for row in rows
    ]
    db.execute(delete(table).where(or_(*row_predicates)))
