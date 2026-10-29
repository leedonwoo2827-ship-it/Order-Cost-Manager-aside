const {app, BrowserWindow, Menu, shell, ipcMain, dialog, screen} = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {createReceiptPdf} = require('./receiptPdf.cjs');

const APP_ID = 'kr.co.ubion.order-cost-manager';

app.setAppUserModelId(APP_ID);

// 대시보드는 하나만 — 두 번째로 켜면 있던 창을 앞으로
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}
app.on('second-instance', () => {
  const win = mainWindow();
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

const mainWindow = () => BrowserWindow.getAllWindows()[0] || null;

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
  if (rows.length === 0) return {saved: false, reason: '내보낼 회차가 없습니다'};

  const root = rpaDataRoot();
  const inbox = path.join(root, 'inbox');
  await fs.mkdir(inbox, {recursive: true});

  // 사업자번호: 엔진이 사업장관리번호(대개 사업자번호+0, 유한회사 제외)를 추정하는 데 쓴다
  const header = ['과정명', '회차', '시작일', '종료일', '사업장명', '사업자번호', '훈련인원', '신청금액'];
  const lines = [header.join(',')];
  for (const row of rows) {
    lines.push(
      [row.course, row.round, row.start, row.end, row.company, row.bizNo || '', row.headcount, row.amount].map(csvCell).join(','),
    );
  }
  const stamp = new Date().toISOString().replace(/\D/g, '').slice(0, 12);
  const csvPath = path.join(inbox, `비용신청대상_${stamp}.csv`);
  await fs.writeFile(csvPath, `\uFEFF${lines.join('\r\n')}\r\n`, 'utf8');

  // 증빙/<과정>_<N>회차/<업체명>/ 빈 폴더 — 사람이 전자계산서·수납확인서 2개를 넣으면 비용신청 탭에서 '신청가능'이 된다.
  // (폴더 이름 규칙은 rpa/hrdnet/organize.py folder_name 과 같다. 백업도 같은 회차 폴더 이름으로 옮긴다)
  const folders = new Set();
  for (const row of rows) {
    const round = String(row.round ?? '').replace(/회차$/, '').trim();
    const dir = path.join(inbox, '증빙', `${cleanName(row.course)}_${cleanName(round)}회차`, cleanName(row.company));
    if (!folders.has(dir) && cleanName(row.company)) {
      folders.add(dir);
      await fs.mkdir(dir, {recursive: true});
    }
  }
  return {saved: true, root, csvPath, rows: rows.length, folders: folders.size,
    evidenceRoot: path.join(inbox, '증빙')};
});

// rpa 엔진(8820)을 켜고 사이드 패널(오른쪽 좁은 창)을 연다. 로그인·인증서는 사람이 한다.
let launching = null;   // 엔진을 켜는 중에 또 누르면 같은 작업을 기다린다(run.bat·패널이 두 번 뜨지 않게)

ipcMain.handle('rpa:launch', () => {
  if (!launching) launching = launchRpa().finally(() => { launching = null; });
  return launching;
});

async function launchRpa() {
  const dir = rpaDir();
  if (!(await rpaRequest('GET', '/api/state'))) {
    const bat = path.join(dir, 'run.bat');
    if (!fsSync.existsSync(bat)) return {ok: false, reason: `rpa 폴더를 찾지 못했습니다: ${dir}`};
    // 경로 없이 run.bat 만 쓰면 NoDefaultCurrentDirectoryInExePath 가 켜진 PC에서 못 찾는다
    const child = spawn('cmd.exe', ['/c', 'start', '', '/min', bat], {
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
  const placed = await arrangeWindows();
  return {ok: placed.ok, layout: placed.layout,
    reason: placed.ok ? '' : 'Chrome 또는 Edge를 찾지 못해 패널을 열지 못했습니다'};
}

// ── 창 배치 ──────────────────────────────────────────────────────────────
// 가로형 모니터가 2개 이상: 작업 모니터(local.json work_display, 기본 주 모니터)에 HRD-Net(왼쪽)+패널(오른쪽),
//                         대시보드는 남는 모니터에 최대화.
// 모니터 1개: 한 화면에 3개 — 왼쪽 약 65% HRD-Net, 오른쪽 위 패널(약 55%), 오른쪽 아래 대시보드(축소 보기).
function rpaLocal() {
  try {
    return JSON.parse(fsSync.readFileSync(path.join(rpaDir(), 'local.json'), 'utf8'));
  } catch {
    return {};
  }
}

function planLayout() {
  const local = rpaLocal();
  const displays = screen.getAllDisplays();
  const isLandscape = (d) => d.bounds.width >= d.bounds.height;
  const landscape = displays.filter(isLandscape);
  const primary = screen.getPrimaryDisplay();
  const wanted = Number.parseInt(local.work_display, 10);
  const work = (Number.isInteger(wanted) && displays[wanted] && isLandscape(displays[wanted]))
    ? displays[wanted]
    : (isLandscape(primary) ? primary : landscape[0] || primary);
  const mode = local.layout === 'single' || local.layout === 'dual'
    ? local.layout
    : (landscape.length >= 2 ? 'dual' : 'single');
  const other = displays.find((d) => d.id !== work.id && isLandscape(d))
    || displays.find((d) => d.id !== work.id);
  const a = work.workArea;   // DIP
  const panelWidth = Math.max(360, Math.min(Number(local.panel_width) || 520, Math.round(a.width * 0.4)));
  if (mode === 'dual' && other) {
    return {
      mode, compact: false, work,
      hrdnet: {x: a.x, y: a.y, width: a.width - panelWidth, height: a.height},
      panel: {x: a.x + a.width - panelWidth, y: a.y, width: panelWidth, height: a.height},
      dashboard: other.workArea, maximize: true,
    };
  }
  const left = Math.round(a.width * 0.65);
  const right = a.width - left;
  const panelHeight = Math.round(a.height * 0.55);
  return {
    mode: 'single', compact: true, work,
    hrdnet: {x: a.x, y: a.y, width: left, height: a.height},
    panel: {x: a.x + left, y: a.y, width: right, height: panelHeight},
    dashboard: {x: a.x + left, y: a.y + panelHeight, width: right, height: a.height - panelHeight}, maximize: false,
  };
}

// DIP → 물리 화소 (Win32 MoveWindow 는 물리 화소). 모니터마다 배율이 달라도 맞게.
const toPhysical = (rect) => (process.platform === 'win32' && screen.dipToScreenRect
  ? screen.dipToScreenRect(null, rect)
  : rect);

async function arrangeWindows() {
  const plan = planLayout();
  const win = mainWindow();
  if (win) {
    win.unmaximize();
    win.setMinimumSize(320, 240);
    win.setBounds(plan.dashboard);
    if (plan.maximize) win.maximize();
    win.webContents.send('layout:changed', {mode: plan.mode, compact: plan.compact});
  }
  const body = JSON.stringify({hrdnet: toPhysical(plan.hrdnet), panel: toPhysical(plan.panel), scale: plan.work.scaleFactor});
  const res = await rpaCall('POST', '/api/layout', body, 15000);
  return {ok: res.ok && res.data?.panel !== false, layout: {mode: plan.mode, compact: plan.compact}};
}

ipcMain.handle('rpa:layout', async () => {
  if (!(await rpaRequest('GET', '/api/state'))) {
    return {ok: false, reason: '엔진이 꺼져 있습니다. 「사이드 패널 열기」를 먼저 누르세요'};
  }
  return arrangeWindows();
});

// 대시보드 화면 → rpa 엔진 API (허용한 경로만). 회차 정리·모의/미리채움/신청 실행·상태 조회에 쓴다.
const RPA_API_ALLOWED = new Set([
  '/api/state', '/api/run', '/api/stop', '/api/backups', '/api/answer', '/api/open',
  '/api/companies', '/api/macros', '/api/macros/clone', '/api/macros/promote', '/api/macros/select',
]);

ipcMain.handle('rpa:api', async (event, req) => {
  const method = req?.method === 'POST' ? 'POST' : 'GET';
  const urlPath = String(req?.path || '');
  if (!RPA_API_ALLOWED.has(urlPath)) return {ok: false, status: 400, error: '허용되지 않은 경로'};
  const body = method === 'POST' ? JSON.stringify(req?.body ?? {}) : '';
  return rpaCall(method, urlPath, body);
});

function rpaCall(method, urlPath, body, timeout = 8000) {
  return new Promise((resolve) => {
    const r = http.request(
      {host: '127.0.0.1', port: RPA_PORT, path: urlPath, method, timeout,
        headers: {'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body)}},
      (res) => {
        let text = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { text += chunk; });
        res.on('end', () => {
          let data = null;
          try { data = JSON.parse(text); } catch { data = null; }
          resolve({ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, data,
            error: data?.detail || ''});
        });
      },
    );
    r.on('error', () => resolve({ok: false, status: 0, error: '엔진에 연결할 수 없습니다'}));
    r.on('timeout', () => { r.destroy(); resolve({ok: false, status: 0, error: '엔진 응답 없음'}); });
    if (body) r.write(body);
    r.end();
  });
}

// 결과표(결과_YYYYMMDD.xlsx · 완료처리대상_*.csv)가 있는 폴더를 탐색기로 연다
ipcMain.handle('rpa:open-results', async () => {
  const dir = path.join(rpaDataRoot(), '결과');
  await fs.mkdir(dir, {recursive: true});
  const err = await shell.openPath(dir);
  return {ok: !err, dir, error: err};
});

// 백업 폴더(기본 <data_root>/_백업)를 탐색기로 연다
ipcMain.handle('rpa:open-backup', async () => {
  let dir = path.join(rpaDataRoot(), '_백업');
  try {
    const local = JSON.parse(fsSync.readFileSync(path.join(rpaDir(), 'local.json'), 'utf8'));
    if (local.backup_root) dir = local.backup_root;
  } catch {
    // 설정이 없으면 기본 위치
  }
  await fs.mkdir(dir, {recursive: true});
  const err = await shell.openPath(dir);
  return {ok: !err, dir, error: err};
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
  if (!gotLock) return;
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
