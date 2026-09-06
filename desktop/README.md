# StudyOS Desktop

StudyOS Desktop packages the existing StudyOS web client as a Windows desktop application.

## Architecture

The desktop app does not maintain a second UI. It bundles the production Next.js standalone
output, starts it on a private loopback port, and places a tiny local reverse proxy in front
of it.

- UI/static requests -> bundled Next.js server
- `/api/*` and `/calendar/*` -> configured StudyOS backend
- Browser renderer -> sandboxed Electron window with Node integration disabled

This preserves StudyOS' existing same-origin browser behavior while allowing the desktop
binary to connect to any deployed StudyOS backend.

## First launch

If `STUDYOS_BACKEND_URL` is not provided, the app displays a first-run connection screen.
The chosen backend origin is saved to Electron's per-user application data directory.

Packaged builds reject non-HTTPS remote servers. Plain HTTP remains available only for
`localhost` / `127.0.0.1` development.

## Local desktop build

Build the Next.js standalone bundle first:

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
