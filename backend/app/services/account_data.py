from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from sqlalchemy import Date, DateTime, String, Table, and_, delete, insert, or_, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.auth import User
from app.models.course import Course

_REDACTED_COLUMN_FRAGMENTS = ("password", "secret", "token")
_REDACTED_COLUMNS = {"auth", "p256dh", "storage_path"}
_MIGRATION_EXCLUDED_TABLES = {
    "users",
    "auth_sessions",
    "password_reset_codes",
    "email_verification_codes",
    "push_subscriptions",
    "push_deliveries",
    "calendar_subscriptions",
    "catalog_courses",
    "catalog_sources",
}
_MIGRATION_MAX_FILES = 5000
_MIGRATION_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_MIGRATION_MAX_JSON_BYTES = 50 * 1024 * 1024


class MigrationBundleError(ValueError):
    pass


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


def _collect_rows(
    db: Session,
    seeds: dict[tuple[str, str], set[Any]],
    *,
    direct_user_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
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
    for key, seed_values in seeds.items():
        values[key].update(seed_values)

    changed = True
    while changed:
        changed = False
        for table in tables:
            predicates = []
            for column in table.columns:
                seeded = seeds.get((table.name, column.name))
                if seeded:
                    predicates.append(column.in_(seeded))

            if direct_user_id is not None and "user_id" in table.c:
                predicates.append(table.c.user_id == direct_user_id)

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


def _collect_owned_rows(db: Session, user_id: str) -> dict[str, list[dict[str, Any]]]:
    return _collect_rows(
        db,
        {("users", "id"): {user_id}},
        direct_user_id=user_id,
    )


def export_user_data(db: Session, user: User) -> dict[str, Any]:
    owned = _collect_owned_rows(db, user.id)
    exported_tables: dict[str, list[dict[str, Any]]] = {}

    for table_name, rows in sorted(owned.items()):
        if table_name in {"users", "auth_sessions"}:
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


def export_migration_bundle(db: Session, user: User) -> bytes:
    owned = _collect_owned_rows(db, user.id)
    payload = export_user_data(db, user)
    manifest: list[dict[str, Any]] = []
    archive = BytesIO()

    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "account.json",
            json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
        )

        for row in owned.get("documents", []):
            storage_path = row.get("storage_path")
            if not storage_path:
                continue
            source = Path(str(storage_path))
            if not source.is_file():
                manifest.append(
                    {
                        "document_id": row["id"],
                        "original_filename": row.get("original_filename"),
                        "included": False,
                        "reason": "source file missing",
                    }
                )
                continue

            extension = str(row.get("extension") or source.suffix or "")
            archive_name = f"files/{row['id']}{extension}"
            bundle.write(source, archive_name)
            manifest.append(
                {
                    "document_id": row["id"],
                    "original_filename": row.get("original_filename"),
                    "content_type": row.get("content_type"),
                    "extension": extension,
                    "size_bytes": row.get("size_bytes"),
                    "sha256": row.get("sha256"),
                    "archive_path": archive_name,
                    "included": True,
                }
            )

        bundle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "studyos-cloud-migration-v1",
                    "created_at": datetime.now(UTC).isoformat(),
                    "source_files": manifest,
                },
                indent=2,
                ensure_ascii=False,
            ).encode("utf-8"),
        )

    return archive.getvalue()



def _migration_archive_path(name: str) -> PurePosixPath:
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MigrationBundleError("Migration bundle contains an unsafe archive path")
    return candidate


def _coerce_import_value(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if (
        isinstance(column.type, Date)
        and not isinstance(column.type, DateTime)
        and isinstance(value, str)
    ):
        return date.fromisoformat(value)
    return value


def _migration_tables(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise MigrationBundleError("Migration bundle account data is missing tables")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for name, rows in tables.items():
        if name in _MIGRATION_EXCLUDED_TABLES:
            continue
        if not isinstance(name, str) or not isinstance(rows, list):
            raise MigrationBundleError("Migration bundle contains malformed table data")
        normalized[name] = rows
    return normalized


def _build_primary_key_maps(
    tables_payload: dict[str, list[dict[str, Any]]],
    user: User,
) -> dict[tuple[str, str], dict[Any, Any]]:
    mappings: dict[tuple[str, str], dict[Any, Any]] = defaultdict(dict)

    for table in Base.metadata.sorted_tables:
        rows = tables_payload.get(table.name)
        if not rows:
            continue
        for row in rows:
            if not isinstance(row, dict):
                raise MigrationBundleError(f"Malformed row in {table.name}")
            for column in table.primary_key.columns:
                if column.name not in row:
                    raise MigrationBundleError(
                        f"Migration row in {table.name} is missing primary key {column.name}"
                    )
                old_value = row[column.name]
                foreign_key = next(iter(column.foreign_keys), None)
                if foreign_key is not None:
                    parent_key = (
                        foreign_key.column.table.name,
                        foreign_key.column.name,
                    )
                    if parent_key == ("users", "id"):
                        new_value = user.id
                    else:
                        try:
                            new_value = mappings[parent_key][old_value]
                        except KeyError as exc:
                            raise MigrationBundleError(
                                f"Migration dependency for {table.name}.{column.name} is missing"
                            ) from exc
                elif isinstance(column.type, String):
                    new_value = str(uuid4())
                else:
                    new_value = old_value
                mappings[(table.name, column.name)][old_value] = new_value

    return dict(mappings)


def _remap_import_row(
    table: Table,
    row: dict[str, Any],
    mappings: dict[tuple[str, str], dict[Any, Any]],
    user: User,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in table.columns:
        if table.name == "documents" and column.name == "storage_path":
            continue
        if column.name not in row:
            if (
                column.nullable
                or column.default is not None
                or column.server_default is not None
                or column.autoincrement is True
            ):
                continue
            raise MigrationBundleError(
                f"Migration row in {table.name} is missing required field {column.name}"
            )

        value = row[column.name]
        own_mapping = mappings.get((table.name, column.name))
        if column.primary_key and own_mapping is not None:
            try:
                value = own_mapping[value]
            except KeyError as exc:
                raise MigrationBundleError(
                    f"Migration primary key mapping for {table.name}.{column.name} is missing"
                ) from exc
        elif column.foreign_keys and value is not None:
            foreign_key = next(iter(column.foreign_keys))
            parent_key = (
                foreign_key.column.table.name,
                foreign_key.column.name,
            )
            if parent_key == ("users", "id"):
                value = user.id
            else:
                parent_mapping = mappings.get(parent_key)
                if parent_mapping is None or value not in parent_mapping:
                    raise MigrationBundleError(
                        f"Migration foreign key for {table.name}.{column.name} is missing"
                    )
                value = parent_mapping[value]

        values[column.name] = _coerce_import_value(column, value)
    return values


def _validate_migration_zip(bundle: ZipFile) -> None:
    infos = bundle.infolist()
    if len(infos) > _MIGRATION_MAX_FILES:
        raise MigrationBundleError("Migration bundle contains too many files")

    total = 0
    for info in infos:
        _migration_archive_path(info.filename)
        total += info.file_size
        if total > _MIGRATION_MAX_UNCOMPRESSED_BYTES:
            raise MigrationBundleError("Migration bundle is too large")


def _read_migration_json(bundle: ZipFile, name: str) -> dict[str, Any]:
    try:
        info = bundle.getinfo(name)
    except KeyError as exc:
        raise MigrationBundleError(f"Migration bundle is missing {name}") from exc
    if info.file_size > _MIGRATION_MAX_JSON_BYTES:
        raise MigrationBundleError(f"{name} is too large")
    try:
        value = json.loads(bundle.read(info))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MigrationBundleError(f"Migration bundle has invalid {name}") from exc
    if not isinstance(value, dict):
        raise MigrationBundleError(f"Migration bundle has malformed {name}")
    return value


def import_migration_bundle(
    db: Session,
    user: User,
    source: BinaryIO,
    *,
    data_dir: Path,
) -> dict[str, int]:
    if db.scalar(select(Course.id).where(Course.user_id == user.id).limit(1)) is not None:
        raise MigrationBundleError(
            "Cloud migration can only be imported into an account with no courses"
        )

    created_files: list[Path] = []
    created_dirs: set[Path] = set()
    try:
        with ZipFile(source, "r") as bundle:
            _validate_migration_zip(bundle)
            account = _read_migration_json(bundle, "account.json")
            manifest = _read_migration_json(bundle, "manifest.json")
            if account.get("format") != "studyos-account-export-v1":
                raise MigrationBundleError("Unsupported StudyOS account export format")
            if manifest.get("format") != "studyos-cloud-migration-v1":
                raise MigrationBundleError("Unsupported StudyOS migration bundle format")

            tables_payload = _migration_tables(account)
            mappings = _build_primary_key_maps(tables_payload, user)

            files_by_document: dict[str, dict[str, Any]] = {}
            source_files = manifest.get("source_files")
            if not isinstance(source_files, list):
                raise MigrationBundleError("Migration bundle source-file manifest is malformed")
            for item in source_files:
                if not isinstance(item, dict) or "document_id" not in item:
                    raise MigrationBundleError("Migration bundle source-file entry is malformed")
                files_by_document[str(item["document_id"])] = item

            imported_rows = 0
            imported_files = 0
            for table in Base.metadata.sorted_tables:
                if table.name in _MIGRATION_EXCLUDED_TABLES:
                    continue
                rows = tables_payload.get(table.name)
                if not rows:
                    continue

                for row in rows:
                    values = _remap_import_row(table, row, mappings, user)
                    if table.name == "documents":
                        old_document_id = str(row["id"])
                        file_info = files_by_document.get(old_document_id)
                        if not file_info or file_info.get("included") is not True:
                            raise MigrationBundleError(
                                f"Source file for document {old_document_id} is missing"
                            )
                        archive_path = file_info.get("archive_path")
                        if not isinstance(archive_path, str):
                            raise MigrationBundleError("Migration source file path is missing")
                        _migration_archive_path(archive_path)

                        new_document_id = str(values["id"])
                        new_course_id = str(values["course_id"])
                        extension = str(row.get("extension") or file_info.get("extension") or "")
                        if not extension.startswith(".") or "/" in extension or "\\" in extension:
                            raise MigrationBundleError("Migration document extension is invalid")

                        destination_dir = Path(data_dir) / new_course_id
                        destination_dir.mkdir(parents=True, exist_ok=True)
                        created_dirs.add(destination_dir)
                        destination = destination_dir / f"{new_document_id}{extension}"

                        digest = hashlib.sha256()
                        size = 0
                        try:
                            source_info = bundle.getinfo(archive_path)
                        except KeyError as exc:
                            raise MigrationBundleError(
                                f"Migration source file {archive_path} is missing"
                            ) from exc
                        with (
                            bundle.open(source_info) as input_file,
                            destination.open("wb") as output,
                        ):
                            while chunk := input_file.read(1024 * 1024):
                                size += len(chunk)
                                if size > _MIGRATION_MAX_UNCOMPRESSED_BYTES:
                                    raise MigrationBundleError("Migration source file is too large")
                                digest.update(chunk)
                                output.write(chunk)
                        created_files.append(destination)

                        expected_size = row.get("size_bytes")
                        expected_hash = row.get("sha256")
                        if expected_size is not None and size != int(expected_size):
                            raise MigrationBundleError(
                                f"Migration source file size mismatch for {old_document_id}"
                            )
                        if expected_hash and digest.hexdigest() != str(expected_hash):
                            raise MigrationBundleError(
                                f"Migration source file hash mismatch for {old_document_id}"
                            )

                        values["storage_path"] = str(destination)
                        imported_files += 1

                    db.execute(insert(table).values(**values))
                    imported_rows += 1

            db.commit()
            return {
                "rows": imported_rows,
                "files": imported_files,
                "courses": len(tables_payload.get("courses", [])),
            }
    except (BadZipFile, OSError) as exc:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        for directory in sorted(created_dirs, reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        if isinstance(exc, BadZipFile):
            raise MigrationBundleError("Invalid StudyOS migration ZIP") from exc
        raise MigrationBundleError("Could not import StudyOS migration bundle") from exc
    except Exception:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        for directory in sorted(created_dirs, reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def delete_user_data(db: Session, user: User) -> list[Path]:
    owned = _collect_owned_rows(db, user.id)
    storage_paths = _storage_paths(owned)
    _delete_collected_rows(db, owned, include_users=True)
    db.commit()
    _unlink_storage(storage_paths)
    return storage_paths


def delete_course_data(db: Session, course: Course) -> list[Path]:
    owned = _collect_rows(db, {("courses", "id"): {course.id}})
    storage_paths = _storage_paths(owned)
    _delete_collected_rows(db, owned, include_users=False)
    db.commit()
    _unlink_storage(storage_paths)
    return storage_paths


def _storage_paths(rows: dict[str, list[dict[str, Any]]]) -> list[Path]:
    return [
        Path(str(row["storage_path"]))
        for row in rows.get("documents", [])
        if row.get("storage_path")
    ]


def _delete_collected_rows(
    db: Session,
    owned: dict[str, list[dict[str, Any]]],
    *,
    include_users: bool,
) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "users" and not include_users:
            continue
        rows = owned.get(table.name)
        if not rows:
            continue
        _delete_rows(db, table, rows)


def _unlink_storage(storage_paths: list[Path]) -> None:
    parents: set[Path] = set()
    for path in storage_paths:
        path.unlink(missing_ok=True)
        parents.add(path.parent)
    for parent in parents:
        try:
            parent.rmdir()
        except OSError:
            pass


def _delete_rows(db: Session, table: Table, rows: list[dict[str, Any]]) -> None:
    primary_keys = list(table.primary_key.columns)
    if not primary_keys:
        return

    row_predicates = [
        and_(*(column == row[column.name] for column in primary_keys))
        for row in rows
    ]
    db.execute(delete(table).where(or_(*row_predicates)))
