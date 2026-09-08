const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = __dirname;
const mainPath = path.join(root, "main.cjs");
const preloadPath = path.join(root, "preload.cjs");
const packagePath = path.join(root, "package.json");

function fail(message) {
  console.error(`Desktop verification failed: ${message}`);
  process.exit(1);
}

function assertIncludes(source, needle, label) {
  if (!source.includes(needle)) fail(`missing ${label}`);
}

for (const file of [mainPath, preloadPath]) {
  const result = spawnSync(process.execPath, ["--check", file], {
    stdio: "inherit",
  });
  if (result.status !== 0) fail(`${path.basename(file)} has invalid JavaScript syntax`);
}

const main = fs.readFileSync(mainPath, "utf8");
const preload = fs.readFileSync(preloadPath, "utf8");
const pkg = JSON.parse(fs.readFileSync(packagePath, "utf8"));

assertIncludes(main, 'const CLOUD_BACKEND_URL = "https://', "HTTPS cloud backend");
assertIncludes(main, "nodeIntegration: false", "disabled Node integration");
assertIncludes(main, "contextIsolation: true", "context isolation");
assertIncludes(main, "sandbox: true", "renderer sandbox");
assertIncludes(main, "webSecurity: true", "Electron web security");
assertIncludes(main, 'requestPath.startsWith("/api/")', "API proxy routing");
assertIncludes(main, 'requestPath.startsWith("/calendar/")', "calendar proxy routing");
assertIncludes(preload, "contextBridge", "contextBridge preload boundary");

if (pkg.main !== "main.cjs") fail("package main must point to main.cjs");
if (pkg.build?.appId !== "com.studyos.desktop") fail("unexpected Electron appId");
if (!Array.isArray(pkg.build?.extraResources)) fail("desktop package is missing extraResources");

const resources = JSON.stringify(pkg.build.extraResources);
if (!resources.includes("build/web/server.js")) fail("bundled Next.js server is missing");
if (!resources.includes("build/backend")) fail("bundled backend is missing");

console.log("StudyOS desktop source verification passed.");
