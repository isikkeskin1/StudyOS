const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("studyosDesktop", {
  saveBackendUrl: (backendUrl) =>
    ipcRenderer.invoke("studyos:save-backend", backendUrl),
});
