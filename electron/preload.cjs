const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('receiptPdf', {
  saveOne: (payload) => ipcRenderer.invoke('receipt-pdf:save-one', payload),
  saveMany: (payload) => ipcRenderer.invoke('receipt-pdf:save-many', payload),
});

contextBridge.exposeInMainWorld('rpa', {
  exportClaims: (payload) => ipcRenderer.invoke('rpa:export', payload),
  launch: () => ipcRenderer.invoke('rpa:launch'),
  completed: () => ipcRenderer.invoke('rpa:completed'),
  openResults: () => ipcRenderer.invoke('rpa:open-results'),
  openBackup: () => ipcRenderer.invoke('rpa:open-backup'),
});

contextBridge.exposeInMainWorld('rpaApi', {
  call: (req) => ipcRenderer.invoke('rpa:api', req),
});
