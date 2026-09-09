# Microsoft Store backend

Packaged StudyOS builds use the production Railway backend by default so Microsoft Store users share the same accounts, authentication state, and password-reset email flow as the web app.

The Electron runtime keeps the bundled SQLite backend available for explicit local/offline development via `STUDYOS_FORCE_LOCAL_BACKEND=1`.

The production backend is HTTPS, which is required for remote backends in packaged builds.
