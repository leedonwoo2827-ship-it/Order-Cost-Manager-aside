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

from .. import config, macros, status

STATIC = Path(__file__).parent / "static"
ALLOWED = {"sample", "fetch", "organize", "inspect", "hrdnet-open", "upload-all", "result", "backup", "report"}
NAMES = {"sample": "샘플 넣기", "fetch": "1 받기(다운로드 감시)", "organize": "2 정리", "inspect": "화면 진단",
         "hrdnet-open": "HRD-Net 열기", "upload-all": "3 올리기", "result": "4 결과", "backup": "백업·정리",
         "report": "보낼 파일 만들기"}
MODES = {"--simulate": "모의 실행", "--dry-run": "점검(찾기만)", "--fill": "미리 채워 보기", "--learn": "학습 미리채워 보기"}
RUN_OPTIONS = ("--simulate", "--dry-run", "--fill", "--learn", "--auto", "--only", "--include-test", "--macro", "--companies")
LOCAL_HOSTS = {"127.0.0.1", "::1"}
UI_PORT = 0
# 대시보드(electron/main.cjs RPA_ENGINE_VERSION)와 같아야 한다. 다르면 대시보드가 이 엔진을 끄고 새로 켠다
# (엔진 창은 최소화로 떠 있어 사람이 찾아 닫기 어렵다). 엔진 코드를 바꾸면 양쪽을 같이 올린다.
ENGINE_VERSION = "2026-10-30.1"

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


def _evidence_index(d) -> dict:
    """inbox/증빙 을 한 번만 훑어 (회차폴더, 업체키, 종류) → 파일 색인을 만든다 (2초마다 600업체도 가볍게).
    구조: 증빙/<과정>_<N>회차/<업체명>/전자계산서_….pdf · 수납확인서_….pdf  (예전 평면 구조도 읽는다)"""
    from ..organize import _company_key

    idx: dict = {"folder": {}, "flat": {}, "count": {}}
    for p in d["증빙"].rglob("*.pdf"):
        parts = p.relative_to(d["증빙"]).parts
        kind = next((k for k, words in config.EVIDENCE.items() if any(w in p.name for w in words)), "")
        if len(parts) >= 3:
            ck = _company_key(parts[-2])
            idx["count"][(parts[0], ck)] = idx["count"].get((parts[0], ck), 0) + 1
            if kind:
                idx["folder"].setdefault((parts[0], ck, kind), p)
        elif len(parts) == 2 and kind:
            idx["flat"].setdefault((parts[0], kind), []).append(p)
    return idx


def _find_in_index(idx: dict, round_folder: str, company: str, kind: str) -> Path | None:
    from ..organize import _company_key

    ck = _company_key(company)
    hit = idx["folder"].get((round_folder, ck, kind))
    if hit or not ck:
        return hit
    flat = [p for p in idx["flat"].get((round_folder, kind), []) if ck in _company_key(p.stem)]
    return flat[0] if len(flat) == 1 else None


def _rounds(d) -> list[dict]:
    """회차 목록 + 업체별 상태. 증빙은 manifest 가 아니라 지금 폴더를 보고 판단한다
    (사람이 업체 폴더에 계산서·수납확인서를 넣으면 다음 새로고침에 바로 '신청가능'이 된다)."""
    from ..organize import _company_key

    idx = _evidence_index(d)
    saved = status.load()
    known = status.known_numbers()
    out = []
    for m in sorted(d["outbox"].glob("*/manifest.json")):
        j = _read(m)
        if not j:
            continue
        up = j.get("올리기") or {}
        folder = m.parent.name
        course, rnd = j.get("과정명", ""), str(j.get("회차", ""))
        businesses = []
        for item in (j.get("사업장") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("사업장명", "")).strip()
            inv = _find_in_index(idx, folder, name, "전자계산서")
            rec = _find_in_index(idx, folder, name, "수납확인서")
            st = status.merged(course, rnd, item, bool(inv), bool(rec), saved)
            n = idx["count"].get((folder, _company_key(name)), 0)
            number, number_from = status.resolve_number(item, known)
            businesses.append({
                "사업장명": name,
                "사업장관리번호": number,
                "관리번호출처": number_from,
                "사업자번호": str(item.get("사업자번호", "") or "").strip(),
                "훈련인원": item.get("훈련인원", 0),
                "신청금액": item.get("신청금액", 0),
                "전자계산서": inv.name if inv else "",
                "수납확인서": rec.name if rec else "",
                "증빙확인": f"업체 폴더에 PDF {n}개 (2개여야 함)" if n and n != 2 else "",
                "제외사유": str(item.get("제외사유", "") or ""),
                **st,
            })
        ready = sum(1 for b in businesses if b["상태"] == "신청가능")
        # 제외(입금 미확인 등)는 증빙을 기다리는 업체가 아니다
        waiting = sum(1 for b in businesses if not b["제외사유"] and not (b["전자계산서"] and b["수납확인서"]))
        excluded: dict[str, int] = {}
        for b in businesses:
            if b["제외사유"]:
                excluded[b["제외사유"]] = excluded.get(b["제외사유"], 0) + 1
        out.append({"folder": folder, "과정명": course, "회차": rnd,
                    "사업장": len(businesses), "첨부": list(j.get("첨부", {})),
                    "사업장내역": businesses, "신청가능": ready, "증빙대기": waiting, "제외": excluded,
                    "신청금액": j.get("신청금액", 0), "훈련인원": j.get("훈련인원", 0),
                    "정리": "준비완료" if ready else ("증빙대기" if waiting else "대상없음"),
                    "정리일시": j.get("정리일시", ""), "올리기": up.get("상태") or "미실행", "모드": up.get("모드", ""),
                    "매크로": up.get("매크로", ""), "끝": up.get("끝", ""), "오류": up.get("오류", "")})
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
        hrd = [t for _h, t in winpos.windows(macros.window_pattern())]
    except Exception:  # noqa: BLE001
        hrd = []
    count = lambda k, v: sum(1 for r in rs if r[k] == v)  # noqa: E731
    return {
        "engine": ENGINE_VERSION,
        "admin": request.state.admin, "busy": RUN.busy, "label": RUN.label if RUN.busy else "",
        "root": str(d["root"]), "hrdnet": hrd, "hrdnet_exe": cfg.get("hrdnet_exe", ""),
        "kpi": {"회차": len(rs), "준비완료": count("정리", "준비완료"), "증빙대기": count("정리", "증빙대기"),
                "업체": sum(r["사업장"] for r in rs), "업체_신청가능": sum(r["신청가능"] for r in rs),
                "채움완료": count("올리기", "채움완료"), "성공": count("올리기", "성공"),
                "문제": sum(1 for r in rs if r["올리기"] in ("실패", "오류", "중단"))},
        "rounds": rs, "inbox": inbox, "pdfs": pdfs, "results": results,
        "report": reports[-1].read_text(encoding="utf-8") if reports else "",
        "report_name": reports[-1].name if reports else "",
        "ask": _read(d["logs"] / "_ask.json"), "now": _read(d["logs"] / "_now.json"),
        "runs": _runs(d, limit=12), "macro": cfg.get("macro") or macros.DEFAULT_ID,
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
    companies: Optional[List[str]] = None   # 체크한 업체(status 키) — 파일로 넘긴다(600곳이면 명령줄이 너무 길다)


@app.post("/api/run")
def run(req: RunReq):
    if not req.args or req.args[0] not in ALLOWED:
        raise HTTPException(400, "허용되지 않은 명령이에요")
    for a in req.args[1:]:
        if a.startswith("--") and a.split("=", 1)[0] not in RUN_OPTIONS:
            raise HTTPException(400, f"허용되지 않은 옵션: {a}")
    args = [a for a in req.args if not a.startswith("--companies=")]
    if args[0] == "upload-all":
        if not any(a.startswith("--only=") for a in args):
            raise HTTPException(400, "올릴 회차를 골라 주세요")
        mid = next((a.split("=", 1)[1] for a in args if a.startswith("--macro=")), "")
        try:
            meta = macros.meta(macros.path(mid or None))
        except FileNotFoundError as e:
            raise HTTPException(400, str(e)) from e
        live = not any(a in args for a in ("--simulate", "--dry-run", "--fill", "--learn"))
        if live and meta.get("상태") == "시험중":
            raise HTTPException(400, f"‘{meta['표시명']}’은 시험중인 매크로라 [신청]을 할 수 없어요. "
                                     "미리 채워 보기로 확인한 뒤 [사용 승격]을 눌러 주세요.")
        if req.companies is not None:
            d = config.dirs()
            f = d["logs"] / "_companies.json"
            f.write_text(json.dumps(sorted(set(req.companies)), ensure_ascii=False), encoding="utf-8")
            args.append(f"--companies={f}")
    RUN.start(args)
    if args[0] == "hrdnet-open" or (args[0] == "upload-all" and "--simulate" not in args):
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


# ── 업체 상태 ─────────────────────────────────────────────────────────
class CompaniesReq(BaseModel):
    items: List[dict]   # [{key, 상태?, 사유?}]


@app.get("/api/companies")
def companies_get():
    return {"states": list(status.STATES), "slots": status.SLOTS, "data": status.load()}


@app.post("/api/companies")
def companies_post(req: CompaniesReq):
    bad = [it.get("상태") for it in req.items if it.get("상태") and it["상태"] not in status.STATES]
    if bad:
        raise HTTPException(400, f"상태는 {', '.join(status.STATES)} 중 하나예요")
    return {"ok": True, "n": status.update(req.items)}


# ── 매크로 ────────────────────────────────────────────────────────────
class MacroReq(BaseModel):
    id: str = ""
    name: str = ""
    source: str = ""


@app.get("/api/macros")
def macros_get():
    cfg = config.load()
    return {"macros": macros.listing(), "current": cfg.get("macro") or macros.DEFAULT_ID,
            "default": macros.DEFAULT_ID, "modes": macros.MODES, "slots": status.SLOTS}


@app.post("/api/macros/clone")
def macros_clone(req: MacroReq):
    try:
        return {"ok": True, "macro": macros.clone(req.name, req.source or macros.DEFAULT_ID)}
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/macros/promote")
def macros_promote(req: MacroReq):
    try:
        return {"ok": True, "macro": macros.promote(req.id)}
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/macros/select")
def macros_select(req: MacroReq):
    try:
        macros.path(req.id)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e
    cfg = config.load()
    cfg["macro"] = req.id
    config.LOCAL.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}


# ── 창 배치 ───────────────────────────────────────────────────────────
class LayoutReq(BaseModel):
    hrdnet: dict                   # HRD-Net 자리 {x, y, width, height} (물리 화소)
    panel: dict                    # 사이드 패널 자리
    scale: float = 1.0             # 그 모니터의 배율 (Chrome 창 옵션은 배율로 나눈 값)


@app.post("/api/layout")
def layout(req: LayoutReq):
    from .. import winpos
    return {"ok": True, **winpos.arrange(req.hrdnet, req.panel, req.scale, UI_PORT)}


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
         "steps": macros.path(), "templates": macros.path() / "templates",
         "status": d["root"] / "status"}.get(req.what)
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
