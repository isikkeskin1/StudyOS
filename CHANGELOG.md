# Changelog

All notable StudyOS beta changes are documented here.

## [0.53.0] - 2026-09-06

### Changed

- Desktop startup now upgrades legacy local SQLite databases through bundled Alembic migrations before serving the app.
- Windows packaging now includes the migration scripts required by the bundled backend.
- Next.js is updated from 15.5.0 to the patched 15.5.24 Maintenance-LTS release.
- Release validation now tests an actual legacy desktop database and verifies it reaches the current schema.

### Fixed

- Existing desktop databases created before the institutional catalog schema no longer fail when newer StudyOS builds start.
- Bundled migration resources are resolved correctly from the packaged PyInstaller runtime.
- Windows legacy-database smoke testing no longer fails on nested PowerShell here-string syntax.

### Release safety

- Backend CI, desktop packaged-app smoke, migration smoke, updater metadata verification and authenticated desktop API traffic remain required release gates.
- v0.53.0 is intended as an upgrade-safety release rather than a feature expansion.

## [0.52.0] - 2026-09-06

### Added

- Institutional course catalog with administrator-owned master courses.
- Admin role bootstrap through `STUDYOS_ADMIN_EMAILS`.
- Public institutional source discovery with bounded same-host crawling.
- Source review queue with candidate, approved, rejected, duplicate, unsupported, failed and imported states.
- Import pipeline for public HTML, PDF, DOCX, PPTX, TXT and Markdown sources.
- Politecnico di Torino official-source presets and one-click source discovery from course metadata.
- Direct catalog-course assignment to users by email.
- GitHub Releases-based automatic updates for installed Windows builds.
- StudyOS-branded updater window with version, progress, percentage and download speed.
- StudyOS startup splash with live startup state.
- Optional Authenticode signing hooks for Windows releases.

### Changed

- Desktop backend and web shell now start in parallel to reduce cold-start time.
- Windows release workflow now generates and verifies `latest.yml` and NSIS blockmaps for updates.
- GitHub publishing is isolated to release events; normal CI never attempts to publish.
- Windows release builds can inherit the version from the GitHub release tag.
- README, Docker, backend, web, desktop, service-worker cache and health metadata aligned to v0.52.0.

### Fixed

- Numbered exam rules and administrative instructions can no longer become fake diagnostic questions.
- Desktop runtime recovery now exposes real startup errors instead of treating every failure as a missing server.
- Hosted backend URLs are validated before being saved.
- Partial desktop child processes are cleaned before recovery.
- Packaged Next.js runtime dependencies are explicitly included and verified.
- Institutional source classification now distinguishes index pages from actual past-exam files.
- Discovery URL handling blocks private/local network targets and validates redirects.
- Desktop updater packaging no longer requires a GitHub token during ordinary push/PR builds.

### Notes

- Existing pre-v0.52 StudyOS installs cannot auto-update retroactively. Install v0.52.0 manually once; subsequent installed releases can update through StudyOS.
- Portable Windows builds remain non-updating by design.
- Unsigned Windows binaries may still trigger Microsoft SmartScreen. The supported mitigation is trusted code signing or Store/MSIX distribution.

## [0.51.2] - 2026-09-06

Desktop runtime reliability hotfix.

## [0.51.1] - 2026-09-06

Desktop startup and recovery hotfix.

## [0.51.0] - 2026-09-06

Initial downloadable Windows desktop beta.

## [0.50.0] - 2026-09-06

Beta hardening: account/data controls, security headers, throttling, production configuration and release audit.
