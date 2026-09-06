const { app, BrowserWindow, ipcMain, session, shell } = require("electron");
const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const net = require("net");
const { spawn } = require("child_process");

app.setAppUserModelId("com.studyos.desktop");

let backendProcess = null;
let nextProcess = null;
let proxyServer = null;
let appWindow = null;
let setupWindow = null;

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const window = appWindow || setupWindow;
    if (!window) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  });
}

function configPath() {
  return path.join(app.getPath("userData"), "desktop.json");
}

function readConfig() {
  const envUrl = process.env.STUDYOS_BACKEND_URL?.trim();
  if (envUrl) return { backendUrl: envUrl };
  try {
    const parsed = JSON.parse(fs.readFileSync(configPath(), "utf8"));
    return { backendUrl: String(parsed.backendUrl || "").trim() };
  } catch {
    return { backendUrl: "" };
  }
}

function normalizeBackendUrl(value) {
  const candidate = String(value || "").trim();
  const parsed = new URL(candidate);
  if (!["https:", "http:"].includes(parsed.protocol)) {
    throw new Error("StudyOS server must use HTTPS or HTTP.");
  }
  if (
    app.isPackaged &&
    parsed.protocol !== "https:" &&
    !["localhost", "127.0.0.1"].includes(parsed.hostname)
  ) {
    throw new Error("Packaged StudyOS requires HTTPS for remote servers.");
  }
  return parsed.origin;
}

function saveConfig(backendUrl) {
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  fs.writeFileSync(
    configPath(),
    JSON.stringify({ backendUrl: normalizeBackendUrl(backendUrl) }, null, 2),
    "utf8",
  );
}

function getOpenPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close(() => {
        if (!port) reject(new Error("Could not allocate a local port."));
        else resolve(port);
      });
    });
  });
}

function waitForHttp(url, timeoutMs = 30000, label = "StudyOS service") {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get(url, (response) => {
        response.resume();
        if (response.statusCode && response.statusCode < 500) {
          resolve();
          return;
        }
        retry();
      });
      request.setTimeout(1500, () => request.destroy());
      request.on("error", retry);
    };
    const retry = () => {
      if (Date.now() - started >= timeoutMs) {
        reject(new Error(`${label} did not start.`));
        return;
      }
      setTimeout(attempt, 250);
    };
    attempt();
  });
}

function bundledBackendPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend", "StudyOSBackend.exe");
  }
  return path.resolve(__dirname, "build/backend/StudyOSBackend.exe");
}

async function startLocalBackend() {
  const executable = bundledBackendPath();
  if (!fs.existsSync(executable)) {
    throw new Error("Bundled StudyOS backend is missing.");
  }

  const port = await getOpenPort();
  const dataRoot = path.join(app.getPath("userData"), "data");
  const uploads = path.join(dataRoot, "uploads");
  const databasePath = path.join(dataRoot, "studyos.db").replace(/\\/g, "/");
  fs.mkdirSync(uploads, { recursive: true });

  backendProcess = spawn(executable, [], {
    cwd: path.dirname(executable),
    windowsHide: true,
    stdio: "ignore",
    env: {
      ...process.env,
      STUDYOS_ENV: "desktop",
      STUDYOS_DESKTOP_HOST: "127.0.0.1",
      STUDYOS_DESKTOP_PORT: String(port),
      STUDYOS_DATABASE_URL: `sqlite:///${databasePath}`,
      STUDYOS_DATA_DIR: uploads,
      STUDYOS_TUTOR_PROVIDER: "local",
      STUDYOS_TUTOR_EMBEDDING_PROVIDER: "none",
      STUDYOS_LOG_LEVEL: "WARNING",
      STUDYOS_RELEASE: app.getVersion(),
    },
  });

  backendProcess.once("exit", (code) => {
    if (!app.isQuitting && code !== 0) {
      console.error(`StudyOS backend exited with code ${code}`);
    }
  });

  const origin = `http://127.0.0.1:${port}`;
  await waitForHttp(
    `${origin}/api/v1/health/ready`,
    45000,
    "StudyOS local backend",
  );
  return origin;
}

function webRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "web")
    : path.resolve(__dirname, "../web/.next/standalone");
}

async function startNextServer() {
  const port = await getOpenPort();
  const root = webRoot();
  const serverPath = path.join(root, "server.js");
  if (!fs.existsSync(serverPath)) {
    throw new Error(
      "StudyOS web bundle is missing. Run the Next.js production build before starting desktop.",
    );
  }

  nextProcess = spawn(process.execPath, [serverPath], {
    cwd: root,
    windowsHide: true,
    stdio: "ignore",
    env: {
      ...process.env,
      NODE_ENV: "production",
      HOSTNAME: "127.0.0.1",
      PORT: String(port),
      STUDYOS_ENV: "production",
      ELECTRON_RUN_AS_NODE: "1",
    },
  });

  nextProcess.once("exit", (code) => {
    if (!app.isQuitting && code !== 0) {
      console.error(`StudyOS web shell exited with code ${code}`);
    }
  });

  await waitForHttp(
    `http://127.0.0.1:${port}/`,
    30000,
    "StudyOS web shell",
  );
  return port;
}

function forwardRequest(req, res, targetOrigin) {
  let target;
  try {
    target = new URL(req.url || "/", targetOrigin);
  } catch {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "Invalid upstream URL" }));
    return;
  }

  const client = target.protocol === "https:" ? https : http;
  const headers = { ...req.headers, host: target.host };

  const upstream = client.request(
    target,
    {
      method: req.method,
      headers,
    },
    (upstreamResponse) => {
      const responseHeaders = { ...upstreamResponse.headers };
      delete responseHeaders["content-security-policy-report-only"];
      res.writeHead(upstreamResponse.statusCode || 502, responseHeaders);
      upstreamResponse.pipe(res);
    },
  );

  upstream.on("error", () => {
    if (!res.headersSent) {
      res.writeHead(502, { "Content-Type": "application/json" });
    }
    res.end(JSON.stringify({ detail: "StudyOS server is unavailable" }));
  });

  req.pipe(upstream);
}

async function startProxy(backendUrl, nextPort) {
  const port = await getOpenPort();
  proxyServer = http.createServer((req, res) => {
    const requestPath = req.url || "/";
    const isBackendRoute =
      requestPath.startsWith("/api/") || requestPath.startsWith("/calendar/");
    const target = isBackendRoute
      ? backendUrl
      : `http://127.0.0.1:${nextPort}`;
    forwardRequest(req, res, target);
  });

  await new Promise((resolve, reject) => {
    proxyServer.once("error", reject);
    proxyServer.listen(port, "127.0.0.1", resolve);
  });
  return port;
}

function configureSessionSecurity(appOrigin) {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const url = webContents.getURL();
    callback(permission === "notifications" && url.startsWith(appOrigin));
  });
}

function createAppWindow(appOrigin) {
  configureSessionSecurity(appOrigin);
  appWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: "#070b11",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });

  appWindow.once("ready-to-show", () => appWindow.show());
  appWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  appWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(appOrigin)) {
      event.preventDefault();
      if (url.startsWith("https://")) void shell.openExternal(url);
    }
  });
  void appWindow.loadURL(appOrigin);
}

function createSetupWindow() {
  if (setupWindow) return;
  setupWindow = new BrowserWindow({
    width: 620,
    height: 620,
    resizable: false,
    backgroundColor: "#080c12",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });
  void setupWindow.loadFile(path.join(__dirname, "setup.html"));
}

ipcMain.handle("studyos:save-backend", async (event, backendUrl) => {
  const senderUrl = event.senderFrame?.url || "";
  if (!senderUrl.startsWith("file:") || !senderUrl.endsWith("/setup.html")) {
    throw new Error("Invalid configuration request.");
  }
  saveConfig(backendUrl);
  setupWindow?.close();
  setupWindow = null;
  await launchStudyOS();
  return true;
});

async function launchStudyOS() {
  const config = readConfig();
  const backendUrl = config.backendUrl
    ? normalizeBackendUrl(config.backendUrl)
    : await startLocalBackend();

  const nextPort = await startNextServer();
  const proxyPort = await startProxy(backendUrl, nextPort);
  createAppWindow(`http://127.0.0.1:${proxyPort}`);
}

if (hasSingleInstanceLock) {
  app.whenReady().then(async () => {
    try {
      await launchStudyOS();
    } catch (error) {
      console.error(error);
      createSetupWindow();
    }
  });
}

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void launchStudyOS();
  }
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (proxyServer) proxyServer.close();
  if (nextProcess) nextProcess.kill();
  if (backendProcess) backendProcess.kill();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
