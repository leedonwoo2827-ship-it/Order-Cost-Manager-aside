"""비용신청 공방 대시보드 — 롱폼 공방(aside-long)과 같은 Runner 방식.

무거운 일(정리·HRD-Net 입력·결과)은 전부 `python -m hrdnet …` 하위 프로세스로 돌리고 로그만 읽는다. 한 번에 하나만 돈다.
올리기 중 사람이 답해야 할 때(사람 단계·최종 신청)는 하위 프로세스가 logs/_ask.json 을 쓰고, 화면 버튼이 _answer.json 을 쓴다.

권한: 이 PC(127.0.0.1) = 전부. 다른 PC = run_lan.bat(HRD_PUBLIC=1)으로 켰을 때만, 열람 비밀번호(Basic), 보기만.
다른 PC 에는 HRD-Net 화면 캡처를 보여 주지 않는다(훈련생 정보가 찍혀 있을 수 있다).
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .. import config

STATIC = Path(__file__).parent / "static"
ALLOWED = {"sample", "fetch", "organize", "inspect", "hrdnet-open", "upload-all", "result", "backup"}
NAMES = {"sample": "샘플 넣기", "fetch": "1 받기(다운로드 감시)", "organize": "2 정리", "inspect": "화면 진단",
         "hrdnet-open": "HRD-Net 열기", "upload-all": "3 올리기", "result": "4 결과", "backup": "백업·정리"}
MODES = {"--simulate": "모의 실행", "--dry-run": "점검(찾기만)", "--fill": "미리 채워 보기"}
LOCAL_HOSTS = {"127.0.0.1", "::1"}
UI_PORT = 0

app = FastAPI(title="비용신청 공방")


def public() -> bool:
    return os.environ.get("HRD_PUBLIC") == "1"


@app.middleware("http")
async def guard(request: Request, call_next):
    host = request.client.host if request.client else ""
    request.state.admin = host in LOCAL_HOSTS
    if request.state.admin:
        return await call_next(request)
    if not public():
        return PlainTextResponse("외부 접속이 꺼져 있습니다 (담당자 PC 에서 run_lan.bat 으로 켜야 함)", status_code=403)
    pw = config.load().get("viewer_password") or ""
    got = ""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            got = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)[-1]
        except Exception:  # noqa: BLE001
            got = ""
    if not pw or not hmac.compare_digest(got, pw):
        return Response("열람 비밀번호가 필요합니다", status_code=401,
                        headers={"WWW-Authenticate": 'Basic realm="HRD claim (any id)"'})
    if request.method not in ("GET", "HEAD"):
        return PlainTextResponse("읽기 전용입니다 — 실행은 담당자 PC 에서만", status_code=403)
    if request.url.path.startswith("/shots"):
        return PlainTextResponse("화면 캡처는 담당자 PC 에서만 볼 수 있습니다", status_code=403)
    return await call_next(request)


# ── Runner ────────────────────────────────────────────────────────────
class Runner:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.lines: List[str] = []
        self.base = 0
        self.lock = threading.Lock()
        self.stopped = False
        self.label = ""

    @property
    def busy(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def add(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > 4000:
            del self.lines[:1000]
            self.base += 1000

    def start(self, args: List[str]) -> None:
        with self.lock:
            if self.busy:
                raise HTTPException(409, "지금 다른 일을 하는 중이에요. 끝나면 다시 눌러 주세요.")
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", HRD_WEB="1")
            env.pop("HRD_PUBLIC", None)
            self.stopped = False
            mode = next((MODES[a] for a in args if a in MODES), "")
            self.label = NAMES.get(args[0], args[0]) + (f" · {mode}" if mode else "")
            only = next((a.split("=", 1)[1] for a in args if a.startswith("--only=")), "")
            self.add(f"▶ {self.label}" + (f"  [{only}]" if only else ""))
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "hrdnet", *args], cwd=str(config.ROOT), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            self.add(line.rstrip("\n"))
        code = proc.wait()
        if not self.stopped:
            self.add("✓ 다 됐어요" if code == 0 else "✗ 중간에 멈췄어요 — 바로 위 줄을 확인해 주세요")

    def stop(self) -> None:
        if self.busy:
            self.stopped = True
            self.add("■ 멈췄어요. 이미 된 건 남아 있고, 다시 누르면 남은 것만 이어서 해요.")
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            d = config.dirs()
            for f in ("_ask.json", "_answer.json", "_now.json"):
                (d["logs"] / f).unlink(missing_ok=True)


RUN = Runner()


# ── 읽기 ──────────────────────────────────────────────────────────────
def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _rounds(d) -> list[dict]:
    from ..organize import _company_key

    out = []
    for m in sorted(d["outbox"].glob("*/manifest.json")):
        j = _read(m)
        if not j:
            continue
        up = j.get("올리기") or {}
        invoices = {str(item.get("사업장명", "")).strip(): item.get("파일", "")
                    for item in (j.get("전자계산서목록") or []) if isinstance(item, dict)}
        receipts = {str(item.get("사업장명", "")).strip(): item.get("파일", "")
                    for item in (j.get("수납확인서목록") or []) if isinstance(item, dict)}
        # 구버전 manifest에는 회차 전체 대표 파일만 들어 있거나 목록이 일부만 저장되어 있다.
        # 상세 표는 실제 회차 증빙 폴더도 확인해 업체별 파일을 빠짐없이 보여 준다.
        evidence_dir = d["증빙"] / m.parent.name
        evidence_pdfs = list(evidence_dir.glob("*.pdf")) if evidence_dir.exists() else []

        def evidence_file(kind: str, company: str, saved: dict[str, str]) -> str:
            stored = saved.get(company, "")
            if stored and Path(stored).exists():
                return Path(stored).name
            company_key = _company_key(company)
            words = config.EVIDENCE.get(kind, [kind])
            for pdf in evidence_pdfs:
                if any(word in pdf.name for word in words) and company_key and company_key in _company_key(pdf.stem):
                    return pdf.name
            return ""

        businesses = []
        for item in (j.get("사업장") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("사업장명", "")).strip()
            businesses.append({
                "사업장명": name,
                "사업장관리번호": str(item.get("사업장관리번호", "")).strip(),
                "훈련인원": item.get("훈련인원", 0),
                "신청금액": item.get("신청금액", 0),
                "전자계산서": evidence_file("전자계산서", name, invoices),
                "수납확인서": evidence_file("수납확인서", name, receipts),
            })
        out.append({"folder": m.parent.name, "과정명": j.get("과정명"), "회차": j.get("회차"),
                    "사업장": len(j.get("사업장", [])), "첨부": list(j.get("첨부", {})),
                    "사업장내역": businesses,
                    "신청금액": j.get("신청금액", 0), "훈련인원": j.get("훈련인원", 0), "정리": j.get("상태"),
                    "정리일시": j.get("정리일시", ""), "올리기": up.get("상태") or "미실행", "모드": up.get("모드", ""),
                    "끝": up.get("끝", ""), "오류": up.get("오류", "")})
    return out


def _runs(d, folder: str = "", limit: int = 30) -> list[dict]:
    out = []
    for p in sorted(d["logs"].glob("*.summary.json"), reverse=True):
        s = _read(p)
        if not s or (folder and Path(s.get("폴더", "")).name != folder):
            continue
        s["log"] = p.name.replace(".summary.json", ".jsonl")
        s["못찾음"] = len(s.get("못찾음", []))
        out.append(s)
        if len(out) >= limit:
            break
    return out


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "dashboard.html").read_text(encoding="utf-8")


@app.get("/panel", response_class=HTMLResponse)
def panel() -> str:
    return (STATIC / "panel.html").read_text(encoding="utf-8")


@app.get("/api/backups")
def backups():
    from .. import backup
    cfg = config.load()
    return {"root": str(backup.backup_root(cfg)), "keep_days": int(cfg.get("backup_keep_days", backup.DEFAULT_KEEP_DAYS) or 0),
            "archive_root": cfg.get("archive_root", ""), "items": backup.list_backups(cfg)}


@app.get("/api/state")
def state(request: Request):
    cfg = config.load()
    d = config.dirs(cfg)
    rs = _rounds(d)
    inbox = [{"name": p.name, "kind": "엑셀"} for p in sorted(d["inbox"].iterdir())
             if p.is_file() and p.suffix.lower() in (".xlsx", ".csv") and not p.name.startswith("~$")]
    pdfs = [str(p.relative_to(d["증빙"])) for p in sorted(d["증빙"].rglob("*.pdf"))]
    reports = sorted(d["outbox"].glob("_검증리포트_*.txt"))
    results = sorted(p.name for p in d["결과"].glob("*") if p.is_file())
    from .. import winpos
    try:
        import yaml
        pattern = (yaml.safe_load((config.ROOT / cfg["steps"]).read_text(encoding="utf-8")) or {}).get("window", "HRD")
        hrd = [t for _h, t in winpos.windows(pattern)]
    except Exception:  # noqa: BLE001
        hrd = []
    count = lambda k, v: sum(1 for r in rs if r[k] == v)  # noqa: E731
    return {
        "admin": request.state.admin, "busy": RUN.busy, "label": RUN.label if RUN.busy else "",
        "root": str(d["root"]), "hrdnet": hrd, "hrdnet_exe": cfg.get("hrdnet_exe", ""),
        "kpi": {"회차": len(rs), "준비완료": count("정리", "준비완료"), "증빙누락": count("정리", "증빙누락"),
                "채움완료": count("올리기", "채움완료"), "성공": count("올리기", "성공"),
                "문제": sum(1 for r in rs if r["올리기"] in ("실패", "오류", "중단"))},
        "rounds": rs, "inbox": inbox, "pdfs": pdfs, "results": results,
        "report": reports[-1].read_text(encoding="utf-8") if reports else "",
        "report_name": reports[-1].name if reports else "",
        "ask": _read(d["logs"] / "_ask.json"), "now": _read(d["logs"] / "_now.json"),
        "runs": _runs(d, limit=12),
    }


@app.get("/api/round/{folder}")
def round_detail(folder: str, request: Request):
    d = config.dirs()
    if Path(folder).name != folder:
        raise HTTPException(400, "잘못된 이름")
    m = _read(d["outbox"] / folder / "manifest.json")
    if not m:
        raise HTTPException(404, "없는 회차예요")
    m["첨부"] = {k: Path(v).name for k, v in m.get("첨부", {}).items()}
    runs = _runs(d, folder, 10)
    steps = []
    if runs:
        lp = d["logs"] / runs[0]["log"]
        if lp.exists():
            steps = [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines() if x.strip()]
            if not request.state.admin:
                for s in steps:
                    s.pop("file", None)
    return {"manifest": m, "runs": runs, "steps": steps}


@app.get("/api/log")
def get_log(since: int = 0):
    start = max(0, since - RUN.base)
    return {"lines": RUN.lines[start:], "next": RUN.base + len(RUN.lines), "busy": RUN.busy}


@app.get("/shots/{name}")
def shot(name: str):
    p = config.dirs()["shots"] / Path(name).name
    if not p.exists() or p.suffix.lower() != ".png":
        raise HTTPException(404, "없음")
    return FileResponse(p)


# ── 실행 ──────────────────────────────────────────────────────────────
class RunReq(BaseModel):
    args: List[str]


@app.post("/api/run")
def run(req: RunReq):
    if not req.args or req.args[0] not in ALLOWED:
        raise HTTPException(400, "허용되지 않은 명령이에요")
    for a in req.args[1:]:
        if a.startswith("--") and a.split("=", 1)[0] not in ("--simulate", "--dry-run", "--fill", "--only", "--include-test"):
            raise HTTPException(400, f"허용되지 않은 옵션: {a}")
    if req.args[0] == "upload-all" and not any(a.startswith("--only=") for a in req.args):
        raise HTTPException(400, "올릴 회차를 골라 주세요")
    RUN.start(req.args)
    if req.args[0] == "hrdnet-open" or (req.args[0] == "upload-all" and "--simulate" not in req.args):
        from .. import winpos
        threading.Thread(target=winpos.open_panel, args=(UI_PORT,), daemon=True).start()
    return {"ok": True}


@app.post("/api/stop")
def stop():
    RUN.stop()
    return {"ok": True}


class AnswerReq(BaseModel):
    id: str
    answer: str


@app.post("/api/answer")
def answer(req: AnswerReq):
    d = config.dirs()
    ask = _read(d["logs"] / "_ask.json")
    if not ask or ask.get("id") != req.id or req.answer not in ask.get("options", []):
        raise HTTPException(409, "지금 기다리는 질문이 아니에요")
    (d["logs"] / "_answer.json").write_text(json.dumps({"id": req.id, "answer": req.answer}), encoding="utf-8")
    RUN.add(f"  ↳ 답: {req.answer}")
    return {"ok": True}


@app.post("/api/panel/open")
def panel_open():
    from .. import winpos
    return {"ok": winpos.open_panel(UI_PORT)}


class FileReq(BaseModel):
    filename: str
    data: str            # data URL 또는 base64
    kind: str = "auto"   # auto: 엑셀→inbox, pdf→inbox/증빙


@app.post("/api/file")
def put_file(req: FileReq):
    d = config.dirs()
    fn = Path(req.filename).name
    ext = Path(fn).suffix.lower()
    if ext not in (".xlsx", ".csv", ".pdf"):
        raise HTTPException(400, "엑셀(xlsx/csv)이나 pdf 만 넣을 수 있어요")
    raw = req.data.split(",", 1)[1] if req.data.startswith("data:") else req.data
    to = (d["증빙"] if ext == ".pdf" else d["inbox"]) / fn
    to.write_bytes(base64.b64decode(raw))
    RUN.add(f"넣었어요 → {to.relative_to(d['root'])}")
    return {"ok": True}


class OpenReq(BaseModel):
    what: str


@app.post("/api/open")
def open_folder(req: OpenReq):
    d = config.dirs()
    p = {"inbox": d["inbox"], "증빙": d["증빙"], "outbox": d["outbox"], "결과": d["결과"], "logs": d["logs"],
         "steps": config.ROOT / "steps.yaml", "templates": config.ROOT / "templates"}.get(req.what)
    if not p:
        raise HTTPException(400, "모르는 폴더")
    os.startfile(p)  # noqa: S606
    return {"ok": True}


@app.get("/api/config")
def get_config():
    cfg = config.load()
    return {k: cfg.get(k) for k in ("data_root", "downloads", "dashboard_url", "hrdnet_exe", "step_delay",
                                    "image_confidence", "panel_width", "browser")} | {
        "viewer_password": bool(cfg.get("viewer_password"))}


@app.put("/api/config")
def put_config(body: dict):
    cfg = config.load()
    for k in ("downloads", "dashboard_url", "hrdnet_exe", "browser"):
        if k in body:
            cfg[k] = str(body[k]).strip()
    for k in ("step_delay", "image_confidence", "panel_width"):
        if k in body and str(body[k]).strip():
            cfg[k] = float(body[k]) if k != "panel_width" else int(float(body[k]))
    if body.get("viewer_password"):
        cfg["viewer_password"] = str(body["viewer_password"])
    config.LOCAL.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}


# ── 켜기 ──────────────────────────────────────────────────────────────
def _lan_ips() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(i for i in ips if i.startswith(("192.168.", "10.", "172.")))


def serve() -> None:
    import uvicorn
    global UI_PORT
    UI_PORT = int(config.load()["port"])
    host = "0.0.0.0" if public() else "localhost"
    url = f"http://localhost:{UI_PORT}/"
    print(f"비용신청 공방 → {url}  (이 창을 닫으면 꺼져요 · 외부 읽기 전용: {'켜짐' if public() else '꺼짐'})", flush=True)
    if public():
        for ip in _lan_ips():
            print(f"  다른 PC 에서: http://{ip}:{UI_PORT}  (아이디 아무거나 + 열람 비밀번호)", flush=True)
    if not os.environ.get("HRD_NO_BROWSER"):
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=host, port=UI_PORT, log_level="warning", log_config=None)
