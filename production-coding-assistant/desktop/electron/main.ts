import { app, BrowserWindow, ipcMain, shell } from "electron";
import path from "node:path";
import fs from "node:fs";
import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";

declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;

const isDev = !app.isPackaged;

// ── Path helpers ────────────────────────────────────────────────────
function projectRoot(): string {
  return isDev
    ? process.cwd()
    : path.resolve(process.resourcesPath, "..", "..", "..");
}

function bundledBackendRoot(): string {
  return path.join(process.resourcesPath, "backend");
}

function resolveBackendLaunch() {
  const bundledPython     = path.join(bundledBackendRoot(), "python.exe");
  const bundledEntrypoint = path.join(bundledBackendRoot(), "server.py");
  if (fs.existsSync(bundledPython) && fs.existsSync(bundledEntrypoint)) {
    return { python: bundledPython, entrypoint: bundledEntrypoint, cwd: bundledBackendRoot(), mode: "bundled" };
  }
  const sourcePython     = path.join(projectRoot(), "..", ".venv", "Scripts", "python.exe");
  const sourceEntrypoint = path.join(projectRoot(), "backend", "server.py");
  return { python: sourcePython, entrypoint: sourceEntrypoint, cwd: projectRoot(), mode: "source" };
}

function resolveRendererEntrypoint(): string {
  const candidates = [
    path.join(projectRoot(), "frontend", "dist", "index.html"),
    path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    path.join(__dirname, "../frontend/dist/index.html"),
  ];
  const match = candidates.find(fs.existsSync);
  if (!match) throw new Error(`Renderer not found. Checked:\n  ${candidates.join("\n  ")}`);
  return match;
}

function resolveAppIcon(): string | undefined {
  const candidates = [
    path.join(projectRoot(), "desktop", "icons", "app.ico"),
    path.join(projectRoot(), "desktop", "icons", "app.png"),
    path.join(process.resourcesPath, "app.ico"),
  ];
  return candidates.find(fs.existsSync);
}

// ── Backend ──────────────────────────────────────────────────────────
function startBackend() {
  if (backendProcess) return;
  const backend = resolveBackendLaunch();

  if (!fs.existsSync(backend.python)) {
    console.error(`[main] Python not found: ${backend.python}`);
    return;
  }
  if (!fs.existsSync(backend.entrypoint)) {
    console.error(`[main] Backend entrypoint not found: ${backend.entrypoint}`);
    return;
  }

  console.log(`[main] Starting backend (${backend.mode}) — ${backend.entrypoint}`);
  backendProcess = spawn(backend.python, [backend.entrypoint], {
    cwd: backend.cwd,
    stdio: "pipe",
    env: { ...process.env, FLASK_DEBUG: isDev ? "true" : "false" },
  });

  backendProcess.stdout.on("data", (d) => {
    const line = d.toString().trimEnd();
    console.log(`[backend] ${line}`);
    mainWindow?.webContents.send("backend-log", line);
  });
  backendProcess.stderr.on("data", (d) => {
    const line = d.toString().trimEnd();
    console.error(`[backend] ${line}`);
    mainWindow?.webContents.send("backend-log", line);
  });
  backendProcess.on("exit", (code) => {
    console.warn(`[main] Backend exited with code ${code}`);
    backendProcess = null;
  });
  backendProcess.on("error", (err) => {
    console.error(`[main] Backend process error: ${err.message}`);
  });
}

// ── Window ───────────────────────────────────────────────────────────
async function createWindow() {
  const icon = resolveAppIcon();

  mainWindow = new BrowserWindow({
    width:     1440,
    height:    900,
    minWidth:  960,
    minHeight: 600,
    title:     "Production Coding Assistant",
    icon,

    // VS Code-style: custom title bar rendered by the web app
    titleBarStyle:    "hidden",
    titleBarOverlay: {
      color:        "#3c3c3c",
      symbolColor:  "#cccccc",
      height:       30,
    },

    backgroundColor: "#1e1e1e",   // match VS Code dark bg to prevent white flash on load

    webPreferences: {
      preload:          path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,
      webSecurity:      true,
    },
  });

  // Hide the default menu bar (VS Code doesn't show it by default)
  mainWindow.setMenuBarVisibility(false);

  mainWindow.webContents.on("did-fail-load", (_e, code, desc, url) => {
    console.error(`[main] Renderer failed to load — ${code} ${desc} — ${url}`);
  });

  // Open external links in the system browser, not in the app
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  if (isDev && MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    await mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
    if (isDev) mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    await mainWindow.loadFile(resolveRendererEntrypoint());
  }
}

// ── App lifecycle ────────────────────────────────────────────────────
app.whenReady().then(async () => {
  startBackend();
  await createWindow();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) await createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

// ── IPC ──────────────────────────────────────────────────────────────
ipcMain.handle("desktop:get-meta", () => ({
  isDev,
  version: app.getVersion(),
  backendMode: resolveBackendLaunch().mode,
  backendEntrypoint: resolveBackendLaunch().entrypoint,
}));

ipcMain.handle("desktop:open-external", (_e, url: string) => shell.openExternal(url));
