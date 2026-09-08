# Microsoft Store distribution

StudyOS keeps two Windows distribution channels:

- **Direct download** — NSIS installer attached to GitHub Releases and linked from `/download`.
- **Microsoft Store** — MSIX package produced by the `Desktop Windows` workflow.

## Partner Center setup

1. Create or use a Microsoft Partner Center developer account.
2. Reserve the product name **StudyOS** as an MSIX app.
3. In Partner Center, copy the package identity values shown for the reserved product.
4. Configure these GitHub repository variables:
   - `STUDYOS_STORE_IDENTITY_NAME`
   - `STUDYOS_STORE_PUBLISHER`
   - `STUDYOS_STORE_PUBLISHER_DISPLAY_NAME`
5. Configure the hosted web environment variable:
   - `NEXT_PUBLIC_STUDYOS_STORE_URL` — the public Microsoft Store listing URL once assigned.

The desktop workflow requires all three Store identity variables together. With none configured,
CI still builds a generic MSIX as a packaging smoke test. With all three configured, the MSIX
manifest is built with the Partner Center identity and is ready to upload for Store certification.

## Release flow

Publishing a GitHub Release builds:

- `StudyOS-Windows-x64-Setup.exe` for the website/direct-install channel.
- `StudyOS-<version>-Windows-x64-Portable.exe`.
- `StudyOS-<version>-Microsoft-Store-x64.msix` as a GitHub Actions artifact for Partner Center.

The Store package is intentionally **not** attached to the public GitHub Release because Store-bound
MSIX packages are re-signed by Microsoft during Store publication and should be acquired from the
Store once approved.

## Website behavior

The `/download` page links its Windows button to `/download/windows`. That route resolves the
latest published GitHub Release and redirects to whichever x64 setup asset is present, so it works
with both historic versioned installer names and the new stable installer filename.

Once `NEXT_PUBLIC_STUDYOS_STORE_URL` is set, the Microsoft Store button becomes active.
