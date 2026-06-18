import { readFile, stat } from "node:fs/promises";

const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const serviceWorker = await readFile(new URL("../public/sw.js", import.meta.url), "utf8");
const manifest = await readFile(new URL("../app/manifest.ts", import.meta.url), "utf8");
const controller = await readFile(new URL("../components/pwa-controller.tsx", import.meta.url), "utf8");

const expectedCache = `studyos-shell-v${packageJson.version}`;
if (!serviceWorker.includes(expectedCache)) {
  throw new Error(`Service worker cache version must match package version: ${expectedCache}`);
}

for (const icon of ["icon-192.png", "icon-512.png", "apple-touch-icon.png"]) {
  const info = await stat(new URL(`../public/icons/${icon}`, import.meta.url));
  if (info.size < 512) throw new Error(`${icon} looks invalid or empty`);
}

for (const required of ["/icons/icon-192.png", "/icons/icon-512.png"]) {
  if (!manifest.includes(required)) throw new Error(`Manifest is missing ${required}`);
}

if (!controller.includes('serviceWorker.register("/sw.js"')) {
  throw new Error("PWA controller is not registering /sw.js");
}

if (!controller.includes("Notification.requestPermission")) {
  throw new Error("PWA controller is missing notification permission handling");
}

console.log(`PWA contract OK for StudyOS ${packageJson.version}`);
