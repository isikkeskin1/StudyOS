const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("studyosDesktop", {
  getStartupError: () => ipcRenderer.invoke("studyos:get-startup-error"),
  openDiagnostics: () => ipcRenderer.invoke("studyos:open-diagnostics"),
  useLocalBackend: () => ipcRenderer.invoke("studyos:use-local-backend"),
  saveBackendUrl: (backendUrl) =>
    ipcRenderer.invoke("studyos:save-backend", backendUrl),
});
