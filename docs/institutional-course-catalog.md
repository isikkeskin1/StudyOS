# Institutional Course Catalog

StudyOS admins can build curated institutional master courses from public and authorized
teaching material, publish them to the catalog, and assign personal copies to users.

## Admin bootstrap

Set one or more comma-separated emails:

```env
STUDYOS_ADMIN_EMAILS=admin@example.com
```

On registration/login, matching accounts receive the admin role.

## Recommended workflow

1. Open **Admin catalog** from the StudyOS dashboard.
2. Create an institutional master course, for example:
   - Institution: `Politecnico di Torino`
   - Institution code: `POLITO`
   - Course: `Physics I`
   - Course code / academic year / language as applicable.
3. Add official public course/teaching portal URLs as discovery seeds.
4. Run discovery with a bounded depth/source count.
5. Review the source queue:
   - `candidate`: needs review
   - `approved`: ready for import
   - `rejected`: intentionally excluded
   - `unsupported`: discovered, but StudyOS cannot ingest that format yet
   - `duplicate`: same content already exists
   - `failed`: unavailable or blocked by discovery safety rules
   - `imported`: ingested into the master course
6. Approve useful sources and import them.
7. StudyOS processes imported material and rebuilds course/exam intelligence.
8. Add any private teaching material only when the admin is authorized to use it.
9. Publish the master course once its processed source set and analysis are ready.
10. Students can enroll from the catalog, or an admin can assign the published course by email.

## Discovery safety

Institution discovery is intentionally bounded:

- only HTTP(S) URLs are accepted;
- seeded hostnames define the crawl boundary;
- followed links must remain on those hosts/subdomains;
- DNS must resolve to public network addresses;
- localhost, private, link-local, multicast, reserved, and unspecified addresses are blocked;
- redirects are revalidated;
- no cookies or authenticated browser session are used;
- downloads are size-capped;
- crawl depth and total discovered source count are capped.

The discovery engine is for public sources. It must not be used to bypass authentication,
paywalls, access controls, or institutional permissions.

## Supported imports

StudyOS currently imports:

- PDF
- DOCX
- PPTX
- TXT
- Markdown
- public HTML pages (converted to text before ingestion)

Other discovered formats remain visible in the review queue as unsupported rather than being
silently discarded.

## Student isolation

A catalog course is a master source owned by an admin. When a student enrolls or an admin
assigns it, StudyOS creates a separate user-owned course and rebuilds the student's course
state from the curated source documents. User mastery, diagnostics, forecasts, plans, and
study history remain tenant-isolated.
