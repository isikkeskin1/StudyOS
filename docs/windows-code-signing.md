# Windows code signing

StudyOS Desktop supports optional Authenticode signing during GitHub Actions releases.

Configure these repository secrets:

- `WINDOWS_CSC_LINK` — base64-encoded PFX/P12 certificate payload or a supported certificate reference for electron-builder.
- `WINDOWS_CSC_KEY_PASSWORD` — password for that certificate.

When those secrets are present, electron-builder signs the Windows binaries during the normal
release build. The release workflow then verifies the resulting Setup EXE with
`Get-AuthenticodeSignature` before upload.

Unsigned builds remain supported for development and beta testing, but Windows SmartScreen may
show **Unknown publisher** or reputation warnings. StudyOS intentionally does not attempt to
bypass SmartScreen. The supported ways to improve that experience are trusted code signing,
publisher reputation, or Store/MSIX distribution.
