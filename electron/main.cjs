const {app, BrowserWindow, Menu, shell, ipcMain, dialog} = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {createReceiptPdf} = require('./receiptPdf.cjs');

const APP_ID = 'kr.co.ubion.order-cost-manager';

app.setAppUserModelId(APP_ID);

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    backgroundColor: '#f8fafc',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  });

  window.once('ready-to-show', () => {
    window.show();
  });

  window.webContents.setWindowOpenHandler(({url}) => {
    if (url.startsWith('https://') || url.startsWith('http://')) {
      void shell.openExternal(url);
    }

    return {action: 'deny'};
  });

  void window.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
}

function safePdfFileName(fileName) {
  const clean = String(fileName || '수납확인서.pdf')
    .replace(/[\\/:*?"<>|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return clean.toLowerCase().endsWith('.pdf') ? clean : `${clean}.pdf`;
}

ipcMain.handle('receipt-pdf:save-one', async (event, payload) => {
  const owner = BrowserWindow.fromWebContents(event.sender);
  const fileName = safePdfFileName(payload?.fileName);
  const options = {
    title: '수납확인서 PDF 저장',
    defaultPath: fileName,
    filters: [{name: 'PDF 문서', extensions: ['pdf']}],
  };
  const result = owner ? await dialog.showSaveDialog(owner, options) : await dialog.showSaveDialog(options);

  if (result.canceled || !result.filePath) return {saved: false};
  const pdf = await createReceiptPdf(payload?.html);
  await fs.writeFile(result.filePath, pdf);
  return {saved: true, filePath: result.filePath};
});

ipcMain.handle('receipt-pdf:save-many', async (event, payload) => {
  const documents = Array.isArray(payload?.documents) ? payload.documents.slice(0, 500) : [];
  if (documents.length === 0) return {saved: false};

  const owner = BrowserWindow.fromWebContents(event.sender);
  const options = {
    title: '수납확인서 PDF 저장 폴더 선택',
    properties: ['openDirectory', 'createDirectory'],
  };
  const result = owner ? await dialog.showOpenDialog(owner, options) : await dialog.showOpenDialog(options);

  if (result.canceled || !result.filePaths[0]) return {saved: false};
  const directory = result.filePaths[0];
  const usedNames = new Map();

  for (const document of documents) {
    const original = safePdfFileName(document?.fileName);
    const count = usedNames.get(original) || 0;
    usedNames.set(original, count + 1);
    const fileName = count === 0 ? original : original.replace(/\.pdf$/i, ` (${count + 1}).pdf`);
    const pdf = await createReceiptPdf(document?.html);
    await fs.writeFile(path.join(directory, fileName), pdf);
  }

  return {saved: true, directory, count: documents.length};
});


// ── HRD-Net 비용신청 RPA(어사이드, Python 사이드카) ─────────────────────────
const RPA_PORT = 8820;
const DEFAULT_DATA_ROOT = 'D:/00data_edu/비용신청';

function rpaDir() {
  if (process.env.ORDER_RPA_DIR) return process.env.ORDER_RPA_DIR;
  const base = app.isPackaged
    ? process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(process.execPath)
    : path.join(__dirname, '..');
  return path.join(base, 'rpa');
}

function rpaDataRoot() {
  try {
    const local = JSON.parse(fsSync.readFileSync(path.join(rpaDir(), 'local.json'), 'utf8'));
    if (local.data_root) return local.data_root;
  } catch {
    // local.json은 rpa 엔진을 처음 켤 때 생긴다
  }
  return DEFAULT_DATA_ROOT;
}

function rpaRequest(method, urlPath, timeout = 1500) {
  return new Promise((resolve) => {
    const req = http.request(
      {host: '127.0.0.1', port: RPA_PORT, path: urlPath, method, timeout, headers: {'Content-Type': 'application/json'}},
      (res) => {
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 300);
      },
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    if (method === 'POST') req.write('{}');
    req.end();
  });
}

const cleanName = (value) => String(value || '').replace(/[\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim();

const csvCell = (value) => {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

// 대시보드 → rpa inbox: 비용신청대상 CSV + 사업장별 수납확인서 PDF
ipcMain.handle('rpa:export', async (event, payload) => {
  const rows = Array.isArray(payload?.rows) ? payload.rows.slice(0, 5000) : [];
  const receipts = Array.isArray(payload?.receipts) ? payload.receipts.slice(0, 500) : [];
  if (rows.length === 0) return {saved: false, reason: '내보낼 회차가 없습니다'};

  const root = rpaDataRoot();
  const inbox = path.join(root, 'inbox');
  await fs.mkdir(inbox, {recursive: true});

  const header = ['과정명', '회차', '시작일', '종료일', '사업장명', '훈련인원', '신청금액'];
  const lines = [header.join(',')];
  for (const row of rows) {
    lines.push(
      [row.course, row.round, row.start, row.end, row.company, row.headcount, row.amount].map(csvCell).join(','),
    );
  }
  const stamp = new Date().toISOString().replace(/\D/g, '').slice(0, 12);
  const csvPath = path.join(inbox, `비용신청대상_${stamp}.csv`);
  await fs.writeFile(csvPath, `\uFEFF${lines.join('\r\n')}\r\n`, 'utf8');

  let receiptCount = 0;
  for (const receipt of receipts) {
    const dir = path.join(inbox, '증빙', `${cleanName(receipt.course)}_${cleanName(receipt.round)}`);
    await fs.mkdir(dir, {recursive: true});
    const pdf = await createReceiptPdf(receipt.html);
    await fs.writeFile(path.join(dir, safePdfFileName(receipt.fileName)), pdf);
    receiptCount += 1;
  }
  return {saved: true, root, csvPath, rows: rows.length, receipts: receiptCount};
});

// rpa 엔진(8820)을 켜고 사이드 패널(오른쪽 좁은 창)을 연다. 로그인·인증서는 사람이 한다.
ipcMain.handle('rpa:launch', async () => {
  const dir = rpaDir();
  if (!(await rpaRequest('GET', '/api/state'))) {
    const bat = path.join(dir, 'run.bat');
    if (!fsSync.existsSync(bat)) return {ok: false, reason: `rpa 폴더를 찾지 못했습니다: ${dir}`};
    const child = spawn('cmd.exe', ['/c', 'run.bat'], {
      cwd: dir,
      detached: true,
      stdio: 'ignore',
      windowsHide: false,
      env: {...process.env, HRD_NO_BROWSER: '1'},
    });
    child.unref();
    let up = false;
    for (let i = 0; i < 90 && !up; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      up = await rpaRequest('GET', '/api/state');
    }
    if (!up) return {ok: false, reason: 'rpa 엔진이 켜지지 않았습니다. rpa 폴더 run.bat 창의 메시지를 확인하세요'};
  }
  const opened = await rpaRequest('POST', '/api/panel/open', 5000);
  return {ok: opened, reason: opened ? '' : 'Chrome 또는 Edge를 찾지 못해 패널을 열지 못했습니다'};
});

// 엔진이 만든 완료처리대상 CSV → 대시보드가 비용신청여부를 일괄 반영
ipcMain.handle('rpa:completed', async () => {
  const dir = path.join(rpaDataRoot(), '결과');
  let names = [];
  try {
    names = (await fs.readdir(dir)).filter((n) => /^완료처리대상_\d+\.csv$/.test(n)).sort();
  } catch {
    return {items: []};
  }
  const items = [];
  for (const name of names) {
    const text = (await fs.readFile(path.join(dir, name), 'utf8')).replace(/^\uFEFF/, '');
    text.split(/\r?\n/).slice(1).forEach((line) => {
      const [course, round] = line.split(',');
      if (course && round) items.push({course: course.trim(), round: round.trim()});
    });
  }
  return {items};
});

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
