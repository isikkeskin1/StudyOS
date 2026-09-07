# StudyOS Cloud — Backup & Restore Runbook

StudyOS Cloud treats PostgreSQL and uploaded course files as canonical user data. A backup is only considered useful if it can be restored and verified.

## What must be protected

### PostgreSQL

PostgreSQL contains:

- accounts and verification state;
- courses and catalog assignments;
- diagnostics, mastery and mistakes;
- plans, queues and schedules;
- forecasts and calibration history;
- tutor/practice state;
- references to uploaded source files.

### Uploaded source files

The backend upload volume contains the original files users uploaded to StudyOS. Database rows alone are not a complete recovery if those files are missing.

## Production baseline

For the current Railway beta:

1. Keep Railway's database volume protected with provider-level backups or PITR when enabled on the account.
2. Take periodic logical PostgreSQL dumps before risky migrations or infrastructure changes.
3. Treat the upload volume as a separate backup domain.
4. Never store database dumps or user course files in the public GitHub repository.
5. Run restore drills into an isolated/scratch database. Never test a restore by overwriting production.

## PostgreSQL logical backup

Use Railway's public database URL only from a trusted machine or CI environment and do not print it to logs.

```bash
pg_dump "$DATABASE_PUBLIC_URL" \
  --format=custom \
  --no-owner \
  --file="studyos-postgres-$(date +%Y%m%d-%H%M%S).dump"
```

The resulting dump is sensitive user data. Store it only in an encrypted/private backup destination.

## Restore drill

Create or provision an isolated PostgreSQL target and restore the dump:

```bash
pg_restore \
  --dbname="$RESTORE_DATABASE_URL" \
  --no-owner \
  --exit-on-error \
  studyos-postgres-YYYYMMDD-HHMMSS.dump
```

Then verify:

```sql
SELECT count(*) FROM users;
SELECT count(*) FROM courses;
SELECT count(*) FROM documents;
SELECT version_num FROM alembic_version;
```

A restore drill is successful only when:

- Alembic is at the expected revision;
- account/course/document counts are plausible;
- foreign-key relationships are intact;
- the API can boot against the restored database;
- `/api/v1/health/ready` succeeds when paired with writable test storage.

## Railway point-in-time recovery

Railway supports PostgreSQL point-in-time recovery (PITR) using archived WAL plus rolling base backups when the feature is enabled for the service/account.

Before enabling it:

- verify the plan/cost impact in Railway;
- define the intended retention window;
- document who is allowed to initiate a restore;
- perform a restore into a fork/scratch service before relying on it.

PITR is preferred for recovery from accidental writes or deletions because it can recover to a point immediately before the incident. Logical dumps remain useful for portability and migration safety.

## Uploaded-file backups

The current beta uses a Railway persistent volume. Until StudyOS moves uploads to object storage:

- do not assume a PostgreSQL backup includes course source files;
- export/copy the upload volume before destructive infrastructure changes;
- preserve paths and SHA-256 values from the `documents` table;
- verify restored files against their recorded `size_bytes` and `sha256`.

The local-to-cloud migration bundle already performs size and SHA-256 verification and is a useful integrity model for future automated upload backups.

## Before every production schema migration

1. Confirm the previous production deployment is healthy.
2. Confirm a recent recoverable database backup exists.
3. Record the current Alembic revision.
4. Deploy the migration.
5. Confirm `/api/v1/health/ready`.
6. Confirm signup/login and one representative authenticated read.
7. Keep the previous deployment available for application rollback.

## Recovery order

For a serious production incident:

1. Stop writes if continuing writes could worsen data loss.
2. Identify the incident timestamp.
3. Restore PostgreSQL into an isolated target.
4. Validate schema and row integrity.
5. Restore/verify uploaded files.
6. Start a StudyOS backend against the recovered copy.
7. Run readiness and authenticated smoke checks.
8. Only then cut production traffic to the recovered data plane.

## Current beta gaps

- Automated off-provider copies of uploaded files are not yet configured.
- PITR/provider backup status must be confirmed in Railway before wider beta traffic.
- A recurring restore drill should be added before StudyOS is treated as production-grade.
- Object storage should replace the single 500 MB filesystem volume as usage grows.
