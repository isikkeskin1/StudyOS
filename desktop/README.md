# StudyOS Desktop

StudyOS Desktop packages the existing StudyOS web client and a local FastAPI backend as a Windows desktop application.

## Architecture

The desktop app does not maintain a second UI. It bundles the production Next.js standalone
output, starts it on a private loopback port, and places a tiny local reverse proxy in front
of it.

- UI/static requests -> bundled Next.js server
- `/api/*` and `/calendar/*` -> bundled local FastAPI backend by default
- local academic state -> SQLite + uploads under Electron's per-user AppData
- optional cloud mode -> configured hosted StudyOS backend
- Browser renderer -> sandboxed Electron window with Node integration disabled

This preserves StudyOS' existing same-origin browser behavior and gives normal users a
double-click local desktop experience without requiring Python, Node, Docker, or a server URL.

## First launch

The packaged app starts its bundled FastAPI sidecar on a private loopback port and creates a
local SQLite database plus upload storage under the user's AppData directory.

A hosted backend can still be selected via `STUDYOS_BACKEND_URL` or the fallback connection
screen if the local sidecar cannot start. Packaged builds reject non-HTTPS remote servers;
plain HTTP remains available only for `localhost` / `127.0.0.1`.

## Local desktop build

For local Electron development, build the Next.js standalone bundle first. Packaged Windows
builds also require `desktop/build/backend/StudyOSBackend.exe`, which CI creates with PyInstaller.


```powershell
cd web
npm install
$env:STUDYOS_ENV="production"
$env:STUDYOS_BACKEND_URL="http://127.0.0.1:8000"
npm run build

cd ../desktop
npm install
npm run start
```

Build Windows installers:

```powershell
npm run dist:win
```

The output is written to `desktop/dist/`.

## Distribution

`.github/workflows/desktop-windows.yml` builds both:

- NSIS installer
- portable Windows executable

Every published GitHub Release triggers a Windows build and uploads the generated EXEs to
that release automatically.

## Signing

Current beta builds are unsigned unless a Windows code-signing certificate is configured in
CI. Unsigned Windows downloads can trigger Microsoft SmartScreen warnings. Production
distribution should add Authenticode signing before broad public launch.
