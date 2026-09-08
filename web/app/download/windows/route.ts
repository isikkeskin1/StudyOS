import { NextResponse } from "next/server";

const LATEST_RELEASE_API =
  "https://api.github.com/repos/isikkeskin1/StudyOS/releases/latest";
const RELEASES_FALLBACK =
  "https://github.com/isikkeskin1/StudyOS/releases/latest";

type ReleaseAsset = {
  name?: string;
  browser_download_url?: string;
};

type LatestRelease = {
  assets?: ReleaseAsset[];
};

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await fetch(LATEST_RELEASE_API, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "StudyOS-download-resolver",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.redirect(RELEASES_FALLBACK, 307);
    }

    const release = (await response.json()) as LatestRelease;
    const installer = release.assets?.find((asset) => {
      const name = asset.name?.toLowerCase() || "";
      return name.endsWith(".exe") && name.includes("windows-x64-setup");
    });

    if (!installer?.browser_download_url) {
      return NextResponse.redirect(RELEASES_FALLBACK, 307);
    }

    return NextResponse.redirect(installer.browser_download_url, 307);
  } catch {
    return NextResponse.redirect(RELEASES_FALLBACK, 307);
  }
}
