const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("studyosDesktop", {
  getStartupError: () => ipcRenderer.invoke("studyos:get-startup-error"),
  openDiagnostics: () => ipcRenderer.invoke("studyos:open-diagnostics"),
  useLocalBackend: () => ipcRenderer.invoke("studyos:use-local-backend"),
  saveBackendUrl: (backendUrl) =>
    ipcRenderer.invoke("studyos:save-backend", backendUrl),

  onStartupProgress: (callback) => {
    const handler = (_event, message) => callback(message);
    ipcRenderer.on("studyos:startup-progress", handler);
    return () => ipcRenderer.removeListener("studyos:startup-progress", handler);
  },

  onUpdateProgress: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on("studyos:update-progress", handler);
    return () => ipcRenderer.removeListener("studyos:update-progress", handler);
  },
  restartAndUpdate: () => ipcRenderer.invoke("studyos:restart-and-update"),
  closeUpdateWindow: () => ipcRenderer.invoke("studyos:close-update-window"),
});
