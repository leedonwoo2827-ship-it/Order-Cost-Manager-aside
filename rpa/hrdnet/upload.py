"""3 올리기 — 사람이 로그인해 둔 HRD-Net 설치 프로그램에 steps.yaml 순서대로 입력한다.

화면 요소를 찾는 순서: UIA(pywinauto) → 화면 이미지(pyautogui) → 사람 안내(답을 기다림).
그래서 selector 를 하나도 안 채운 지금도 "단계별 안내 + 기록" 도구로 돈다. 채울수록 자동이 된다.

모드
  기본       실제로 클릭·입력한다. confirm 단계(최종 신청)는 사람이 [신청]을 눌러야 진행
  --fill     미리 채워 보기 — 다 채우고 confirm 단계(최종 신청) 앞에서 멈춘다 (롱폼 공방의 「미리 채워 보기」)
  --dry-run  화면 요소를 찾기만 하고 누르지 않는다
  --simulate HRD-Net 없이 순서만 훑는다 (개발·시연용)

사람에게 묻는 곳: 콘솔이면 input(), 대시보드(HRD_WEB=1)에서 돌면 logs/_ask.json 을 쓰고
대시보드·사이드 패널의 버튼이 logs/_answer.json 을 쓸 때까지 기다린다.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from . import config

ERROR_WORDS = ["체납", "오류", "실패", "할 수 없", "불가", "누락"]


class Stop(Exception):
    pass


def _fmt(s: str, vals: dict) -> str:
    return re.sub(r"\{([^{}]+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), s or "")


def _flatten(steps: list, manifest: dict) -> list[tuple[dict, dict]]:
    """for_each: 사업장 블록을 사업장 수만큼 펼친다 → (단계, 이 단계에서 쓸 값)."""
    base = {k: manifest.get(k, "") for k in ("과정명", "회차", "검색시작", "검색종료")}
    base.update({k: manifest.get("첨부", {}).get(k, "") for k in config.EVIDENCE})
    out = []
    for s in steps:
        if s.get("for_each") == "사업장":
            for i, biz in enumerate(manifest.get("사업장", []), start=1):
                for sub in s["steps"]:
                    out.append((dict(sub, id=f"{sub['id']}#{i}"), dict(base, **biz)))
        else:
            out.append((s, base))
    return out


# ── 사람에게 묻기 (콘솔 / 대시보드) ────────────────────────────────────
def ask(kind: str, msg: str, options: list[str]) -> str:
    """kind: human(사람이 해 줄 단계) / confirm(최종 신청) / next(다음 회차로?). 답은 options 중 하나."""
    if os.environ.get("HRD_WEB") != "1":
        hint = {"human": "다 했으면 Enter (s=건너뛰기, q=중단): ", "confirm": "진행하려면 '신청' 입력 (그 외 = 중단): ",
                "next": "다음 회차로 넘어갈까요? (y/그 외 = 멈춤): "}[kind]
        try:
            a = input(f"{msg}\n  {hint}").strip().lower()
        except EOFError:
            a = "q"
        return {"human": {"": "ok", "s": "skip"}.get(a, "stop"),
                "confirm": "신청" if a == "신청" else "stop",
                "next": "next" if a == "y" else "stop"}[kind]
    d = config.dirs()
    qid = uuid.uuid4().hex[:8]
    ans = d["logs"] / "_answer.json"
    ans.unlink(missing_ok=True)
    (d["logs"] / "_ask.json").write_text(json.dumps({"id": qid, "kind": kind, "msg": msg, "options": options},
                                                    ensure_ascii=False), encoding="utf-8")
    print(f"  ? {msg}  → 대시보드/사이드 패널에서 답해 주세요", flush=True)
    try:
        while True:
            if ans.exists():
                try:
                    a = json.loads(ans.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    a = {}
                if a.get("id") == qid and a.get("answer") in options:
                    return a["answer"]
            time.sleep(0.4)
    finally:
        (d["logs"] / "_ask.json").unlink(missing_ok=True)
        ans.unlink(missing_ok=True)


def _now(d, data: dict | None) -> None:
    """사이드 패널이 읽는 '지금 하는 단계'."""
    p = d["logs"] / "_now.json"
    if data is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class Screen:
    """HRD-Net 창. simulate 에서는 아무것도 하지 않는다."""

    def __init__(self, title_re: str, simulate: bool, cfg: dict):
        self.simulate = simulate
        self.cfg = cfg
        self.win = None
        if simulate:
            return
        from pywinauto import Desktop
        self.desk = Desktop(backend="uia")
        self.win = self.desk.window(title_re=title_re)
        if not self.win.exists(timeout=5):
            raise Stop(f"HRD-Net 창을 찾지 못했습니다 (제목 정규식 {title_re!r}). 로그인해 두었는지, "
                       "[화면 진단]으로 창 제목을 확인하세요.")

    def focus(self):
        if self.win:
            self.win.set_focus()

    def find(self, target: dict | None):
        """→ ('uia', 요소) | ('image', (x, y)) | None"""
        if self.simulate or not target:
            return None
        uia = {k: v for k, v in (target.get("uia") or {}).items() if v not in (None, "")}
        if uia:
            el = self.win.child_window(**uia)
            if el.exists(timeout=2):
                return ("uia", el)
        img = target.get("image")
        if img:
            p = config.ROOT / img
            if p.exists():
                import pyautogui
                try:
                    box = pyautogui.locateCenterOnScreen(str(p), confidence=self.cfg["image_confidence"])
                except Exception:  # noqa: BLE001 — 못 찾으면 예외를 던지는 버전이 있다
                    box = None
                if box:
                    return ("image", (box.x, box.y))
        return None

    def click(self, hit):
        kind, el = hit
        if kind == "uia":
            el.click_input()
        else:
            import pyautogui
            pyautogui.click(*el)

    def type(self, text: str):
        from pywinauto.keyboard import send_keys
        send_keys("^a{BACKSPACE}", pause=0.02)
        send_keys(re.sub(r"([{}+^%~()])", r"{\1}", text), with_spaces=True, pause=0.02)

    def attach(self, path: str):
        """[첨부] 를 누른 뒤 뜨는 윈도우 '열기' 창에 전체 경로를 넣고 Enter."""
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
        dlg = Desktop(backend="win32").window(class_name="#32770")
        dlg.wait("ready", timeout=15)
        dlg.set_focus()
        try:
            dlg.child_window(class_name="Edit", found_index=0).set_edit_text(path)
        except Exception:  # noqa: BLE001 — 칸을 못 잡으면 키보드로
            send_keys("%n")
            self.type(path)
        send_keys("{ENTER}")
        dlg.wait_not("exists", timeout=15)

    def popup_text(self) -> str:
        """HRD-Net 이 띄운 알림창 글자 (오류 판정용)."""
        if self.simulate:
            return ""
        texts = []
        try:
            for w in self.win.children(control_type="Window"):
                texts.append(" ".join(t for t in w.texts() if t))
                for c in w.descendants(control_type="Text"):
                    texts.extend(t for t in c.texts() if t)
        except Exception:  # noqa: BLE001
            pass
        return " ".join(texts)[:500]

    def shot(self, path: Path):
        if self.simulate:
            return
        from PIL import ImageGrab
        ImageGrab.grab().save(path)


def run(folder: Path, dry: bool = False, simulate: bool = False, fill: bool = False) -> dict:
    cfg = config.load()
    d = config.dirs(cfg)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load((config.ROOT / cfg["steps"]).read_text(encoding="utf-8"))
    mode = "simulate" if simulate else "dry-run" if dry else "미리채움" if fill else "실행"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{stamp}_{manifest['과정명']}_{manifest['회차']}회차"
    logf = d["logs"] / f"{name}.jsonl"
    summary = {"과정명": manifest["과정명"], "회차": manifest["회차"], "모드": mode, "폴더": str(folder),
               "시작": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "상태": "", "단계수": 0, "완료": 0,
               "자동": 0, "사람": 0, "못찾음": [], "오류": "", "신청금액": manifest.get("신청금액", 0)}
    plan = _flatten(spec["steps"], manifest)
    summary["단계수"] = len(plan)
    print(f"[{mode}] {manifest['과정명']} {manifest['회차']}회차 — {len(plan)}단계", flush=True)

    def log(rec):
        with open(logf, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(rec, at=datetime.now().strftime("%H:%M:%S")), ensure_ascii=False) + "\n")

    try:
        scr = Screen(spec.get("window", ".*HRD.*"), simulate, cfg)
        for i, (step, vals) in enumerate(plan, start=1):
            sid, act = step["id"], step.get("action", "click")
            say = _fmt(step.get("say", ""), vals)
            rec = {"id": sid, "action": act, "say": say}
            _now(d, {"folder": folder.name, "과정명": manifest["과정명"], "회차": manifest["회차"], "모드": mode,
                     "i": i, "n": len(plan), "id": sid, "say": say})
            if act == "focus":
                scr.focus()
                rec["result"] = "ok"
            elif act == "screenshot":
                p = d["shots"] / f"{name}_{sid}.png"
                scr.shot(p)
                rec["result"], rec["file"] = "ok", p.name
            elif act == "wait":
                time.sleep(float(step.get("seconds", 1)))
                rec["result"] = "ok"
            else:
                if act == "attach" and not _fmt(step.get("file", ""), vals).strip("{}"):
                    if step.get("optional"):
                        rec["result"] = "건너뜀(파일 없음)"
                        print(f"  {sid:6} {'건너뜀':10} {say} — 파일 없음", flush=True)
                        log(rec)
                        summary["완료"] += 1
                        continue
                    raise Stop(f"{sid}: 첨부할 파일이 manifest 에 없습니다")
                if fill and step.get("confirm"):
                    shot = d["shots"] / f"{name}_{sid}_채움.png"
                    scr.shot(shot)
                    rec["result"], rec["file"] = "채움까지만", shot.name
                    print(f"  {sid:6} {'멈춤':10} {say} — 미리 채워 보기라 누르지 않음", flush=True)
                    log(rec)
                    summary["완료"] += 1
                    summary["상태"] = "채움완료"
                    break
                hit = scr.find(step.get("target"))
                rec["found"] = hit[0] if hit else None
                if not hit:
                    summary["못찾음"].append(sid)
                if simulate or dry:
                    rec["result"] = "확인만"
                    print(f"  {sid:6} {'찾음 ' + hit[0] if hit else '못찾음':10} {say}", flush=True)
                    log(rec)
                    summary["완료"] += 1
                    continue
                if step.get("confirm"):
                    shot = d["shots"] / f"{name}_{sid}_확인전.png"
                    scr.shot(shot)
                    rec["file"] = shot.name
                    if ask("confirm", f"★ {manifest['과정명']} {manifest['회차']}회차 — {say}",
                           ["신청", "stop"]) != "신청":
                        raise Stop("사람이 최종 신청을 멈춤")
                if hit:
                    scr.click(hit)
                    if act == "type":
                        scr.type(_fmt(step.get("text", ""), vals))
                        if step.get("then_text"):
                            from pywinauto.keyboard import send_keys
                            send_keys("{TAB}")
                            scr.type(_fmt(step["then_text"], vals))
                    elif act == "attach":
                        scr.attach(_fmt(step["file"], vals))
                    summary["자동"] += 1
                    rec["result"] = "자동"
                else:
                    extra = ""
                    if act == "type":
                        extra = f"  입력값: {_fmt(step.get('text', ''), vals)} {_fmt(step.get('then_text', ''), vals)}"
                    if act == "attach":
                        extra = f"  파일: {_fmt(step['file'], vals)}"
                    a = ask("human", f"[{sid}] {say}{extra}", ["ok", "skip", "stop"])
                    if a == "stop":
                        raise Stop(f"{sid}에서 사람이 중단")
                    summary["사람"] += 1
                    rec["result"] = "건너뜀" if a == "skip" else "사람"
                time.sleep(cfg["step_delay"])
                pop = scr.popup_text()
                if pop:
                    rec["popup"] = pop
                    if any(w in pop for w in ERROR_WORDS):
                        log(rec)
                        raise Stop(f"{sid} 뒤 알림: {pop[:120]}")
            log(rec)
            summary["완료"] += 1
        if not summary["상태"]:
            summary["상태"] = {"simulate": "모의완료", "dry-run": "점검완료"}.get(mode, "성공")
    except Stop as e:
        summary["상태"], summary["오류"] = ("실패" if "알림" in str(e) else "중단"), str(e)
        print("  멈춤:", e, flush=True)
    except Exception as e:  # noqa: BLE001
        summary["상태"], summary["오류"] = "오류", f"{type(e).__name__}: {e}"
        print("  오류:", summary["오류"], flush=True)
    finally:
        _now(d, None)
    summary["끝"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (d["logs"] / f"{name}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    manifest["올리기"] = {k: summary[k] for k in ("모드", "상태", "끝", "오류")}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {summary['상태']}  (완료 {summary['완료']}/{summary['단계수']}, 자동 {summary['자동']}, "
          f"사람 {summary['사람']}, 못찾음 {len(summary['못찾음'])})  기록: {logf.name}", flush=True)
    return summary


def run_all(dry: bool = False, simulate: bool = False, fill: bool = False, only: list[str] | None = None) -> None:
    """only 가 있으면 그 회차 폴더들만(상태와 상관없이 증빙누락만 빼고), 없으면 아직 신청 안 된 준비완료 회차 전부."""
    d = config.dirs()
    todo = []
    for m in sorted(d["outbox"].glob("*/manifest.json")):
        j = json.loads(m.read_text(encoding="utf-8"))
        if only is not None:
            if m.parent.name in only and j.get("상태") == "준비완료":
                todo.append(m.parent)
        elif j.get("상태") == "준비완료" and (j.get("올리기") or {}).get("상태") != "성공":
            todo.append(m.parent)
    print(f"올릴 회차 {len(todo)}개", flush=True)
    for k, f in enumerate(todo):
        s = run(f, dry=dry, simulate=simulate, fill=fill)
        if s["상태"] in ("중단", "오류", "실패") and not (dry or simulate) and k < len(todo) - 1:
            if ask("next", f"{f.name}: {s['상태']} — 다음 회차로 넘어갈까요?", ["next", "stop"]) != "next":
                break
