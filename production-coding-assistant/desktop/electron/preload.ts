import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("desktopBridge", {
  getMeta: () => ipcRenderer.invoke("desktop:get-meta"),
  onBackendLog: (callback: (message: string) => void) => {
    const listener = (_event: unknown, message: string) => callback(message);
    ipcRenderer.on("backend-log", listener);
    return () => ipcRenderer.removeListener("backend-log", listener);
  },
});
