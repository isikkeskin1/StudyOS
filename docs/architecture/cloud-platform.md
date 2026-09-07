# StudyOS Cloud Platform

StudyOS is moving from isolated desktop accounts to one centralized account and data plane shared by the web app and Windows desktop app.

## Target topology

```text
                         studyos.courses
                               │
                  ┌────────────┴────────────┐
                  │                         │
             Web browser              Windows app
                  │                         │
                  └────────────┬────────────┘
                               │ HTTPS
                               ▼
                      StudyOS web gateway
                               │
                     same-origin /api
                               ▼
                         FastAPI backend
                  auth · courses · planning
                    tutor · catalog · sync
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
           PostgreSQL                  persistent files
        accounts + state              course documents
                 │
                 ▼
         transactional services
          Brevo SMTP · Web Push
```

## Identity

- One StudyOS account works on both web and desktop.
- PostgreSQL is the canonical account store.
- Session cookies remain HTTP-only and secure in production.
- Password reset codes are generated and verified by the hosted backend.
- SMTP credentials never ship in the Windows binary.
- Password resets revoke all existing account sessions.
- Email verification should use the same transactional email infrastructure.

## Desktop

The existing Electron client already supports a hosted StudyOS backend over HTTPS.

During migration:

1. Existing local mode remains available as a compatibility path.
2. Cloud mode becomes the supported account-backed mode.
3. Once the production service is stable, new builds should default to the StudyOS cloud endpoint.
4. The bundled local backend can later become an offline/cache engine rather than the source of truth.

The desktop renderer continues to use the same Next.js UI as the web product.

## Web

The hosted web app uses the same Next.js application and FastAPI API as desktop. Browser and desktop users therefore share:

- accounts;
- courses;
- catalog assignments;
- mastery and diagnostics;
- semester queues;
- forecasts;
- tutor history;
- uploaded course material;
- account export/deletion.

## Production secrets

The hosted backend owns all provider secrets.

Required for password recovery:

```text
STUDYOS_SMTP_HOST=smtp-relay.brevo.com
STUDYOS_SMTP_PORT=587
STUDYOS_SMTP_USERNAME=<Brevo SMTP login>
STUDYOS_SMTP_PASSWORD=<secret>
STUDYOS_SMTP_FROM_EMAIL=support@studyos.courses
STUDYOS_SMTP_USE_TLS=true
```

The SMTP password must only exist in the hosting provider's secret store or server environment. It must never be committed to GitHub or bundled into desktop releases.

## Rollout

### Phase A — cloud foundation
- production PostgreSQL;
- persistent upload storage;
- HTTPS endpoint;
- SMTP-backed password recovery;
- deployment migration gate;
- production backups.

### Phase B — centralized accounts
- web signup/login;
- email verification;
- password recovery;
- desktop login against hosted accounts;
- session management and revoke-all.

### Phase C — shared academic data
- move course state and uploads to canonical cloud storage;
- migrate catalog assignments to cloud-only identity;
- preserve local data export/import during transition.

### Phase D — public web product
- serve StudyOS at `studyos.courses`;
- desktop and web use the same account;
- production monitoring, backups, abuse protection and support workflow.

### Phase E — offline support
- local cache;
- resumable uploads;
- conflict-aware sync;
- offline study sessions where practical.

## Release rule

Do not remove legacy local mode until centralized accounts, hosted storage, migrations, password recovery and real desktop-to-cloud smoke tests all pass in CI and production.
