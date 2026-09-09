const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const desktopDir = __dirname;
const distDir = path.join(desktopDir, 'dist');
const stagingDir = path.join(distDir, 'appx-manual');
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopDir, 'package.json'), 'utf8'));
const version = packageJson.version;
const outputPath = path.join(distDir, `StudyOS-${version}-Microsoft-Store-x64.appx`);

function fail(message) {
  console.error(message);
  process.exit(1);
}

function findFile(root, targetName) {
  if (!root || !fs.existsSync(root)) return null;
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    let entries;
    try { entries = fs.readdirSync(current, { withFileTypes: true }); } catch { continue; }
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) stack.push(full);
      else if (entry.isFile() && entry.name.toLowerCase() === targetName.toLowerCase()) return full;
    }
  }
  return null;
}

function runBuilder() {
  const electronBuilderCli = path.join(desktopDir, 'node_modules', 'electron-builder', 'out', 'cli', 'cli.js');
  if (!fs.existsSync(electronBuilderCli)) fail(`Missing local electron-builder CLI: ${electronBuilderCli}`);

  const args = [electronBuilderCli, '--win', 'appx', '--publish', 'never'];
  if (process.env.STORE_IDENTITY_NAME) {
    args.push(`--config.appx.identityName=${process.env.STORE_IDENTITY_NAME}`);
    args.push(`--config.appx.publisher=${process.env.STORE_PUBLISHER || packageJson.build.appx.publisher}`);
    args.push(`--config.appx.publisherDisplayName=${process.env.STORE_PUBLISHER_DISPLAY_NAME || packageJson.build.appx.publisherDisplayName}`);
  }

  console.log(`Generating AppX manifest and mapping with electron-builder CLI: ${electronBuilderCli}`);
  const result = spawnSync(process.execPath, args, {
    cwd: desktopDir,
    stdio: 'inherit',
    env: { ...process.env, CSC_IDENTITY_AUTO_DISCOVERY: 'false' },
    windowsHide: false,
  });
  if (result.error) console.warn(`electron-builder invocation warning: ${result.error.message}`);
  console.log(`electron-builder exited with code ${result.status ?? 'unknown'}; continuing with manual AppX packaging.`);
}

runBuilder();

const generatedRoot = path.join(distDir, '__appx-x64');
const mappingPath = path.join(generatedRoot, 'mapping.txt');
const manifestPath = path.join(generatedRoot, 'AppxManifest.xml');

if (!fs.existsSync(mappingPath)) fail(`Missing generated AppX mapping: ${mappingPath}`);
if (!fs.existsSync(manifestPath)) fail(`Missing generated AppX manifest: ${manifestPath}`);

if (fs.existsSync(stagingDir)) fs.rmSync(stagingDir, { recursive: true, force: true });
fs.mkdirSync(stagingDir, { recursive: true });

const lines = fs.readFileSync(mappingPath, 'utf8').split(/\r?\n/);
const filteredMapping = [];
let copied = 0;
let skippedReserved = 0;
let skippedPythonDocxContentTypes = 0;

const reservedPayloadNames = new Set([
  'appxblockmap.xml',
  'appxstreammap.xml',
  'appxsignature.p7x',
  '[content_types].xml',
]);

function escapeMappingValue(value) {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function validateDestination(destination) {
  if (path.isAbsolute(destination)) fail(`Unsafe AppX destination in mapping: ${destination}`);
  const components = destination.split('\\');
  if (components.some((component) => component === '..' || component === '')) {
    fail(`Unsafe AppX destination component in mapping: ${destination}`);
  }

  for (const component of components) {
    if (/[<>:"|?*\x00-\x1f]/.test(component)) {
      fail(`Invalid Windows AppX destination component: ${destination}`);
    }
    if (/[ .]$/.test(component)) {
      fail(`Trailing dot/space in AppX destination component: ${destination}`);
    }
    const base = component.split('.')[0].toUpperCase();
    if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/.test(base)) {
      fail(`Reserved Windows device name in AppX destination: ${destination}`);
    }
  }
}

// MakeAppx's mapping-file mode treats an exact AppxManifest.xml destination as the
// package manifest. Keep it out of the payload set, then add it explicitly below.
filteredMapping.push(`"${escapeMappingValue(manifestPath)}" "AppxManifest.xml"`);

for (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('[')) continue;
  const match = trimmed.match(/^"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"$/);
  if (!match) continue;

  const source = match[1].replace(/\\"/g, '"');
  const destination = match[2].replace(/\\"/g, '"');
  const normalizedDestination = destination.replace(/\\/g, '/').toLowerCase();
  const destinationLeaf = path.basename(destination).toLowerCase();

  if (destinationLeaf === 'appxmanifest.xml') {
    // We add the generated manifest once, above, so it is never duplicated.
    continue;
  }

  // [Content_Types].xml is an OPC/DOCX footprint file. It is not a valid AppX
  // payload name and MakeAppx creates its own package footprint files.
  if (destinationLeaf === '[content_types].xml') {
    skippedPythonDocxContentTypes += 1;
    console.log(`Skipping OPC footprint payload: ${destination}`);
    continue;
  }

  if (reservedPayloadNames.has(destinationLeaf)) {
    skippedReserved += 1;
    console.log(`Skipping reserved AppX payload name: ${destination}`);
    continue;
  }

  validateDestination(destination);
  if (!fs.existsSync(source)) fail(`Mapped AppX source does not exist: ${source}`);

  const destinationPath = path.resolve(stagingDir, ...destination.split('\\'));
  const stagingRoot = path.resolve(stagingDir) + path.sep;
  if (!destinationPath.startsWith(stagingRoot)) fail(`AppX destination escapes staging directory: ${destination}`);

  fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
  fs.copyFileSync(source, destinationPath);
  filteredMapping.push(`"${escapeMappingValue(destinationPath)}" "${escapeMappingValue(destination)}"`);
  copied += 1;
}

const filteredMappingPath = path.join(stagingDir, 'filtered-mapping.txt');
fs.writeFileSync(filteredMappingPath, `[Files]\n${filteredMapping.join('\n')}\n`, 'utf8');

const cacheRoot = process.env.LOCALAPPDATA
  ? path.join(process.env.LOCALAPPDATA, 'electron-builder', 'Cache')
  : null;
const makeAppx = findFile(cacheRoot, 'makeappx.exe');
if (!makeAppx) fail(`Could not find makeappx.exe under ${cacheRoot || '<missing LOCALAPPDATA>'}`);

if (fs.existsSync(outputPath)) fs.rmSync(outputPath, { force: true });
console.log(`Manual AppX staging ready: ${copied} payload files copied, ${skippedPythonDocxContentTypes} OPC footprint payload(s) skipped, ${skippedReserved} reserved payload(s) skipped.`);
console.log(`Filtered MakeAppx mapping: ${filteredMappingPath}`);
console.log(`Using MakeAppx: ${makeAppx}`);
console.log(`Creating: ${outputPath}`);

const result = spawnSync(makeAppx, [
  'pack',
  '/f', filteredMappingPath,
  '/p', outputPath,
  '/o',
  '/v',
], {
  cwd: desktopDir,
  stdio: 'inherit',
  windowsHide: true,
});

if (result.error) fail(`Failed to launch makeappx.exe: ${result.error.message}`);
if (result.status !== 0) fail(`makeappx.exe failed with exit code ${result.status}`);
if (!fs.existsSync(outputPath)) fail(`MakeAppx reported success but package is missing: ${outputPath}`);

console.log(`Created Microsoft Store AppX: ${outputPath}`);
console.log(`Size: ${(fs.statSync(outputPath).size / 1024 / 1024).toFixed(2)} MB`);