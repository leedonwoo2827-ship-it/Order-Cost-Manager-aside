"""3 올리기 — 사람이 로그인해 둔 HRD-Net 설치 프로그램에 매크로(rpa/macros/<id>/steps.yaml) 순서대로 입력한다.

화면 요소를 찾는 순서: UIA(pywinauto) → 화면 이미지(cv2). 못 찾으면 화면을 찍고 멈추거나(업체 문제면) 그 업체만 불가로 뺀다.
v2.2.3 부터 사람에게 클릭을 넘기지 않는다 — 학습 모드(--learn)만 사람이 누르고 그 클릭을 녹화한다.

모드
  기본       실제로 클릭·입력한다. confirm 단계(최종 신청)는 사람이 [신청]을 눌러야 진행
  --fill     미리 채워 보기 — 다 채우고 confirm 단계(최종 신청) 앞에서 멈춘다.
             사람이 화면을 본 뒤 [다음 회차로]를 누르면 after_round 단계(검색화면 복귀)만 하고 다음 회차로 간다
  --dry-run  화면 요소를 찾기만 하고 누르지 않는다
  --simulate HRD-Net 없이 순서만 훑는다 (개발·시연용)
  --learn    (미리 채워 보기와 함께) 모든 단계를 사람에게 맡기고 클릭을 녹화한다 — 새 매크로 학습용

업체 단위
  대시보드에서 체크한 업체(status 키)만 for_each 로 펼친다. 업체 하나가 불가(미납·체납·업체명 확인 불가)면
  그 업체만 빼고(on_skip 단계로 팝업을 닫고) 다음 업체로 간다. 기록은 status.py 의 f01~f30 에 남긴다.

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

from . import config, macros, status

ERROR_WORDS = ["체납", "오류", "실패", "할 수 없", "불가", "누락", "미납"]


class Stop(Exception):
    pass


class Ineligible(Stop):
    pass


class SkipCompany(Exception):
    """이 업체만 빼고 계속한다 (미납·체납·업체명 확인 불가)."""


def _fmt(s: str, vals: dict) -> str:
    return re.sub(r"\{([^{}]+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), s or "")


def _num(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _selected_businesses(manifest: dict, selected: set[str] | None) -> list[dict]:
    """체크한 업체만. 각 업체에 status 키(_key)를 붙인다."""
    out = []
    for b in manifest.get("사업장", []):
        k = status.key(manifest["과정명"], str(manifest["회차"]), b)
        if selected is None or k in selected:
            out.append(dict(b, _key=k))
    return out


def _flatten(steps: list, manifest: dict, businesses: list[dict]) -> list[tuple[dict, dict]]:
    """for_each 블록을 펼친다 → (단계, 이 단계에서 쓸 값). 업체 단계의 값에는 _key(업체 status 키)가 있다."""
    base = {k: manifest.get(k, "") for k in ("과정명", "회차", "검색시작", "검색종료")}
    base.update({k: manifest.get("첨부", {}).get(k, "") for k in config.EVIDENCE})
    by_name = {status.company_key(b.get("사업장명", "")): b for b in businesses}
    out = []
    for s in steps:
        collection = s.get("for_each")
        if collection:
            items = businesses if collection == "사업장" else [
                dict(it, _key=by_name[status.company_key(it.get("사업장명", ""))]["_key"])
                for it in manifest.get(collection, [])
                if status.company_key(it.get("사업장명", "")) in by_name]
            for i, item in enumerate(items, start=1):
                for sub in s["steps"]:
                    out.append((dict(sub, id=f"{sub['id']}#{i}"), dict(base, **item)))
        else:
            out.append((s, base))
    return out


def _resolve_inbox_evidence(manifest: dict, dirs: dict[str, Path]) -> list[str]:
    """inbox/증빙의 업체별 원본 PDF를 실행할 때마다 다시 찾는다(사람이 폴더에 넣은 뒤 정리를 다시 안 해도 된다).
    → 증빙이 덜 들어온 업체 이름 목록"""
    from .organize import _find_evidence

    pdfs = list(dirs["증빙"].rglob("*.pdf"))
    missing: set[str] = set()
    attachments = manifest.setdefault("첨부", {})
    for kind in config.EVIDENCE:
        items = []
        for business in manifest.get("사업장", []):
            company = str(business.get("사업장명", ""))
            src = _find_evidence(
                kind, str(manifest.get("회차", "")), str(manifest.get("과정명", "")), "",
                pdfs, dirs["inbox"], [company],
            )
            if src:
                items.append({"사업장명": company, "증빙종류": kind, "파일": str(src)})
            else:
                missing.add(company)
        manifest[f"{kind}목록"] = items
        # 구버전 화면/로그 호환용. 실제 첨부 단계는 위 목록을 사용한다.
        attachments[kind] = items[0]["파일"] if len(items) == 1 else ""
    return sorted(missing)


# ── 사람에게 묻기 (콘솔 / 대시보드) ────────────────────────────────────
def ask(kind: str, msg: str, options: list[str], copy_values: list[dict[str, str]] | None = None) -> str:
    """kind: human(사람이 해 줄 단계) / confirm(최종 신청) / next(다음 회차로?) / filled(미리 채움 끝) /
    company(업체명 확인 불가). 답은 options 중 하나."""
    if os.environ.get("HRD_WEB") != "1":
        hint = {"human": "다 했으면 Enter (s=건너뛰기, x=이 업체 불가, q=중단): ",
                "confirm": "진행하려면 '신청' 입력 (그 외 = 중단): ",
                "next": "다음 회차로 넘어갈까요? (y/그 외 = 멈춤): ",
                "filled": "확인했으면 y = 검색화면으로 돌아가 다음 회차 (그 외 = 멈춤): ",
                "company": "p=그래도 진행, x=이 업체 불가 처리, 그 외 = 멈춤: "}[kind]
        try:
            a = input(f"{msg}\n  {hint}").strip().lower()
        except EOFError:
            a = "q"
        ans = {"human": {"": "ok", "s": "skip", "x": "ineligible"}.get(a, "stop"),
               "confirm": "신청" if a == "신청" else "stop",
               "next": "next" if a == "y" else "stop",
               "filled": "next" if a == "y" else "stop",
               "company": {"p": "proceed", "x": "ineligible"}.get(a, "stop")}[kind]
        return ans if ans in options else "stop"
    d = config.dirs()
    qid = uuid.uuid4().hex[:8]
    ans = d["logs"] / "_answer.json"
    ans.unlink(missing_ok=True)
    payload = {"id": qid, "kind": kind, "msg": msg, "options": options}
    if copy_values:
        payload["copy"] = copy_values
    (d["logs"] / "_ask.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
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

    def __init__(self, title_re: str, simulate: bool, cfg: dict, macro_dir: Path):
        self.simulate = simulate
        self.cfg = cfg
        self.macro_dir = macro_dir
        self.title_re = title_re
        self.win = None
        self.round_typed = ""     # [2-r] 회차 칸에 넣고 OCR 로 다시 읽어 확인한 회차
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

    def keep_place(self) -> bool:
        """HRD-Net 이 중간에 최대로 커지면 정해진 자리로 되돌린다(이미지·학습 좌표가 어긋나지 않게)."""
        if self.simulate:
            return False
        try:
            from . import winpos
            return winpos.keep_place(self.title_re)
        except Exception:  # noqa: BLE001
            return False

    def scope(self, title: str | None):
        """팝업 창 제목으로 찾는 범위를 좁힌다(UIA) — HRD-Net 팝업은 Window 가 아니라 Pane 으로 보인다(10/30 진단)."""
        if self.simulate:
            return None
        if not title:
            return self.win
        for where in (lambda: self.win.child_window(title_re=title),
                      lambda: self.desk.window(title_re=title)):
            try:
                w = where()
                if w.exists(timeout=1):
                    return w
            except Exception:  # noqa: BLE001
                continue
        return None

    # ── 화면 그림 찾기 ─────────────────────────────────────────────────
    # HRD-Net 은 UIA·DOM 으로 버튼이 안 보여(10/29·10/30 진단) 화면 그림이 유일한 수단이다.
    # 오탐을 막는 규칙: 점수 ≥ image_confidence, 정해진 영역 안에서 '딱 1곳'(unique)일 때만 누른다.
    # 영역은 늘 같은 모양인 기준 그림(팝업 제목줄 등 — scope_image)에서 떨어진 거리로 정한다.
    # 비용등록 팝업은 HRD-Net 주 창 밖(화면 전체)으로 커지기도 해서 창이 아니라 화면을 캡처한다.
    SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 0.8)   # 다른 PC 의 화면 배율(100~200%) — 맞은 배율을 기억해 먼저 쓴다

    def windows_scale(self) -> int:
        """HRD-Net 창이 떠 있는 모니터의 Windows 디스플레이 배율(%) — 100 이 아니면 숫자 점글꼴·그림 모양이 달라져
        4단계 업체 찾기가 안 된다. 모니터마다 배율이 다를 수 있어(주 모니터 세로 100% + 가로 150% 등) 창 기준으로 본다."""
        try:
            import ctypes
            from ctypes import wintypes
            mon = ctypes.windll.user32.MonitorFromWindow(wintypes.HWND(self.win.handle), 2)   # 가장 가까운 모니터
            x, y = wintypes.UINT(), wintypes.UINT()
            if ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
                return round(x.value * 100 / 96)
            return round(ctypes.windll.user32.GetDpiForSystem() * 100 / 96)
        except Exception:  # noqa: BLE001
            return 100

    def screen_rect(self) -> tuple[int, int, int, int]:
        import ctypes
        u = ctypes.windll.user32
        left, top = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        return left, top, left + u.GetSystemMetrics(78), top + u.GetSystemMetrics(79)

    def _region(self, box) -> tuple[int, int, int, int]:
        """box: None(주 창) | 'screen' | (l, t, r, b) 화면 좌표 | pywinauto 요소 → 화면 안으로 자른 영역."""
        sl, st, sr, sb = self.screen_rect()
        if box == "screen":
            return sl, st, sr, sb
        if isinstance(box, tuple):
            l, t, r, b = box
        else:
            rect = (box or self.win).rectangle()
            l, t, r, b = rect.left, rect.top, rect.right, rect.bottom
        return max(l, sl), max(t, st), min(r, sr), min(b, sb)

    def px(self, v) -> int:
        """기준 화면(100%)에서 잰 거리 → 이 PC 배율의 거리."""
        return int(round(float(v) * getattr(self, "scale", 1.0)))

    def _find_region(self, target: dict):
        """target.scope_image {image, box:[l,t,r,b]} → (영역, 기준점) | (None, None)=기준 그림 없음 | ('', None)=지정 없음."""
        si = target.get("scope_image")
        if not si:
            return "", None
        imgs = self._images(si.get("image"))
        if not imgs:
            return None, None
        hits = self.match_all(imgs[0][0], float(si.get("threshold", self.cfg["image_confidence"])), "screen")
        if len(hits) != 1:
            return None, None
        ax, ay = hits[0]
        l, t, r, b = (self.px(v) for v in si.get("box") or (-2000, -2000, 2000, 2000))
        return self._region((ax + l, ay + t, ax + r, ay + b)), (ax, ay)

    def find(self, target: dict | None):
        """→ ('uia', 요소) | ('image', (x, y)) | None.  target.wait 초 동안 다시 찾는다(화면이 늦게 뜰 때)."""
        if self.simulate or not target:
            return None
        end = time.time() + float(target.get("wait", 0))
        while True:
            hit = self._find_once(target)
            if hit or time.time() >= end:
                return hit
            time.sleep(0.5)

    def _find_once(self, target: dict):
        uia = {k: v for k, v in (target.get("uia") or {}).items() if v not in (None, "")}
        if uia:
            box = self.scope(target.get("scope"))
            if box is not None:
                try:
                    el = box.child_window(**uia)
                    if el.exists(timeout=1):
                        return ("uia", el)
                except Exception:  # noqa: BLE001 — 같은 조건이 여러 개면 found_index 를 채운다
                    pass
        region, anchor = self._find_region(target)
        if region is None:
            return None
        where = region or ("screen" if target.get("scope") else None)
        unique = bool(target.get("unique"))
        # image: "a.png" 또는 [{image, offset:[dx,dy]} | {at:[dx,dy]}, …] — offset 은 그림 가운데에서 얼마나 떨어진 곳을 누를지,
        # at 은 scope_image 기준점에서 떨어진 곳. HRD-Net 화면은 칸 배치가 고정이라 기준 그림 하나로 자리를 잡는다.
        entries = target.get("image")
        for e in entries if isinstance(entries, list) else [entries] if entries else []:
            if isinstance(e, dict) and "at" in e and anchor:
                return ("image", (anchor[0] + self.px(e["at"][0]), anchor[1] + self.px(e["at"][1])))
        for img, offset in self._images(entries):
            hits = self.match_all(img, float(target.get("threshold", self.cfg["image_confidence"])), where)
            if unique and len(hits) != 1:
                continue
            if hits:
                return ("image", (hits[0][0] + self.px(offset[0]), hits[0][1] + self.px(offset[1])))
        return self.learned(target.get("_sid", ""), target.get("learned", "template"), self.win)

    def _images(self, value) -> list[tuple[Path, tuple[int, int]]]:
        entries = value if isinstance(value, list) else [value] if value else []
        out = []
        for e in entries:
            name, offset = (e.get("image", ""), e.get("offset") or (0, 0)) if isinstance(e, dict) else (e, (0, 0))
            if not name:
                continue
            p = self.macro_dir / name
            if not p.exists():
                p = config.ROOT / name
            if p.exists():
                out.append((p, (int(offset[0]), int(offset[1]))))
        return out

    def _match(self, box, template_path: Path):
        """창(또는 팝업) 화면에서 버튼 이미지를 찾는다 → 화면 좌표(x, y) | None"""
        hits = self.match_all(template_path, float(self.cfg["image_confidence"]), box)
        return hits[0] if hits else None

    def match_all(self, template_path: Path, threshold: float = 0.9, box=None) -> list[tuple[int, int]]:
        """화면에서 그림과 같은 곳을 모두 → 화면 좌표 목록(점수 높은 순). 겹친 자리는 하나로 친다."""
        if self.simulate:
            return []
        try:
            import cv2
            import numpy as np

            l, t, r, b = self._region(box)
            if r - l < 4 or b - t < 4:
                return []
            screen = cv2.cvtColor(np.array(self.grab(l, t, r, b).convert("RGB")), cv2.COLOR_RGB2GRAY)
            base = cv2.imdecode(np.fromfile(str(template_path), np.uint8), cv2.IMREAD_GRAYSCALE)
            if base is None:
                return []
            first = getattr(self, "scale", 1.0)
            for s in (first, *[v for v in self.SCALES if v != first]):
                template = base if s == 1.0 else cv2.resize(
                    base, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR if s > 1 else cv2.INTER_AREA)
                if template.shape[0] > screen.shape[0] or template.shape[1] > screen.shape[1]:
                    continue
                scores = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(scores >= threshold)
                if not len(xs):
                    continue
                th, tw = template.shape[:2]
                keep: list[tuple[int, int]] = []
                for _s, x, y in sorted(((float(scores[y, x]), int(x), int(y)) for y, x in zip(ys, xs)), reverse=True):
                    cx, cy = l + x + tw // 2, t + y + th // 2
                    if all(abs(cx - a) > tw // 2 or abs(cy - b2) > th // 2 for a, b2 in keep):
                        keep.append((cx, cy))
                self.scale = s
                return keep
            return []
        except Exception:  # noqa: BLE001
            return []

    def grab(self, left: int, top: int, right: int, bottom: int):
        """화면 좌표 영역 캡처 (PIL)."""
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)

    def learned(self, sid: str, how: str, box):
        """학습 녹화(learned_actions.json) 재생 — 사람이 그 단계에서 누른 곳을 다시 누른다.
        how=template  녹화 때 잘라 둔 버튼 주변 이미지로 찾는다(기본, 화면이 조금 바뀌어도 됨)
        how=coords    창 크기 대비 비율 좌표 그대로 (검색으로 걸러 목표 행이 늘 첫 줄일 때만)
        how=off       재생 안 함 (행 내용이 매번 바뀌는 단계)"""
        if how == "off" or not sid or box is None:
            return None
        if not hasattr(self, "_learned"):
            p = self.macro_dir / "learned_actions.json"
            try:
                self._learned = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            except (OSError, json.JSONDecodeError):
                self._learned = {}
        events = (self._learned.get(re.sub(r"#\d+$", "", sid)) or {}).get("events") or []
        if len(events) != 1:      # 여러 번 누른 단계는 순서가 바뀌면 위험해서 재생하지 않는다(단계를 나눠 녹화)
            return None
        ev = events[0]
        if how == "coords":
            rect = self.win.rectangle()       # 녹화는 HRD-Net 주 창 기준 비율
            return ("image", (int(rect.left + ev["x_ratio"] * rect.width()),
                              int(rect.top + ev["y_ratio"] * rect.height())))
        if ev.get("template"):
            at = self._match(box, self.macro_dir / ev["template"])
            if at:
                return ("image", at)
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

    def read_box(self, at: tuple[int, int], crop) -> str:
        """입력한 칸을 다시 읽는다(점글꼴 표 먼저, 안 되면 OCR) — crop 은 누른 자리 기준 [왼, 위, 오른, 아래]."""
        from . import ocr
        x, y = at
        return ocr.read_numbers([self.grab(x + crop[0], y + crop[1], x + crop[2], y + crop[3])])[0]

    def round_buttons(self, rnd: str, step: dict) -> tuple[list, str, dict]:
        """목록에서 실시회차가 rnd 인 '신청대상' 행의 [신청] → (hit 목록, 판정 방법, 정보).
        [신청] 버튼은 그림으로 모두 찾고(신청대상 행에만 있다), 각 버튼 행의 실시회차 칸을 읽는다(ocr.read_numbers: 점글꼴 표 먼저).
          · 읽은 회차가 rnd 인 버튼이 딱 하나 → 그것 ('회차읽기')
          · 읽지 못했어도, 프로그램이 회차 칸에 rnd 를 넣은 것을 확인했고([2-r]) 목록에 [신청]이 하나뿐 → 그것 ('회차검색')
          · 그 밖에는 고르지 않는다 → 멈춤. 회차를 확인하지 못한 [신청]은 절대 누르지 않는다."""
        from . import ocr
        # [검색] 뒤 목록이 늦게 뜰 수 있다 — 10/29 녹화: 바로 찾아서 [신청] 0개로 멈춤. 버튼이 보일 때까지 기다린다
        buttons, end = [], time.time() + float(step.get("list_wait", 10))
        while True:
            for path, _offset in self._images(step.get("button")):
                buttons = self.match_all(path, float(step.get("button_threshold", 0.9)))
                if buttons:
                    break
            if buttons or time.time() >= end:
                break
            time.sleep(0.5)
        info: dict = {"신청버튼": len(buttons), "회차입력확인": self.round_typed == rnd}
        if not buttons:
            return [], "", info
        # 처리상태가 '신청대상'인 행만 — 정상지급(직권반려) 행에도 [신청]이 있을 수 있다.
        # 글자 그림(status_image)으로 먼저 보고, 그림이 없을 때만 OCR 로 읽는다
        sl, st, sr, sb = step.get("status_cell") or (-50, -44, 50, -10)
        cells = [self.grab(x + sl, y + st, x + sr, y + sb) for x, y in buttons]
        shapes = self._images(step.get("status_image"))
        if shapes:
            status = ["신청대상" if _has_shape(c, shapes[0][0]) else "" for c in cells]
        else:
            status = ocr.read_texts(cells)
        info["처리상태"] = status
        targets = [i for i, s in enumerate(status) if "신청대상" in s]
        buttons = [buttons[i] for i in targets]
        if not buttons:
            return [], "", info
        l, t, r, b = step.get("round_cell") or (-475, -36, -420, 6)
        readings = ocr.read_numbers([self.grab(x + l, y + t, x + r, y + b) for x, y in buttons])
        info["읽은회차"] = readings
        picked = [i for i, v in enumerate(readings) if v == str(rnd)]
        if len(picked) == 1:
            return [("image", buttons[picked[0]])], "회차읽기", info
        if not picked and len(buttons) == 1 and self.round_typed == rnd:
            return [("image", buttons[0])], "회차검색", info
        return [], "", info

    def menu_search(self, text: str, step: dict) -> str:
        """우측 상단 메뉴검색 칸에 메뉴 이름 → 돋보기(안 되면 Enter) → 검색화면 기준 그림이 보이면 성공.
        → '이미 열림' | 'image' | ''(실패)"""
        from pywinauto.keyboard import send_keys
        expect = self._images(step.get("expect_image"))

        def opened(seconds: float) -> bool:
            end = time.time() + seconds
            while True:
                if any(self._match(self.win, p) for p, _o in expect):
                    return True
                if time.time() >= end:
                    return False
                time.sleep(0.5)

        if expect and opened(0):
            return "이미 열림"
        icon = None
        for path, _offset in self._images(step.get("icon")):
            icon = self._match(self.win, path)
            if icon:
                break
        if not icon:
            return ""
        dx, dy = step.get("box_offset") or (-80, 0)
        self.click(("image", (icon[0] + dx, icon[1] + dy)))     # 검색칸 글자 자리
        self.type(text)
        self.click(("image", icon))                              # 돋보기
        if opened(8):
            return "image"
        send_keys("{ENTER}")
        return "image" if opened(6) else ""

    def attach(self, path: str):
        """[첨부] 를 누른 뒤 뜨는 윈도우 '첨부파일' 열기 창에 전체 경로를 넣고 Enter.
        #32770 대화상자는 여러 개 떠 있을 수 있어서(ElementAmbiguousError) 제목으로 고른다."""
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
        desk = Desktop(backend="win32")
        dlg = None
        for crit in ({"title": "첨부파일", "class_name": "#32770"},
                     {"title_re": ".*(첨부|열기|Open).*", "class_name": "#32770", "found_index": 0},
                     {"class_name": "#32770", "active_only": True, "found_index": 0}):
            try:
                w = desk.window(**crit)
                if w.exists(timeout=5):
                    dlg = w
                    break
            except Exception:  # noqa: BLE001
                continue
        if dlg is None:
            raise Stop("첨부파일 열기 창을 찾지 못했습니다")
        dlg.wait("ready", timeout=15)
        dlg.set_focus()
        try:
            dlg.child_window(class_name="Edit", found_index=0).set_edit_text(path)
        except Exception:  # noqa: BLE001 — 칸을 못 잡으면 키보드로
            send_keys("%n")
            self.type(path)
        send_keys("{ENTER}")
        dlg.wait_not("exists", timeout=15)

    # HRD-Net 확인창 — UIA 로 안 보여서 제목줄 그림으로 찾는다 (10/30 녹화에서 잘라 냄).
    # (이름, 제목줄 그림, [확인] 그림, 제목줄 기준 글자 영역)
    DIALOGS = (
        ("Confirm", "templates/dlg_confirm_title.png", "templates/btn_dlg_ok_confirm.png", (-40, 35, 260, 95)),
        ("알림", "templates/dlg_alert_title.png", "templates/btn_dlg_ok_alert.png", (-40, 35, 440, 140)),
    )

    def dialog(self):
        """떠 있는 확인창 → (이름, 제목줄 자리, [확인] 그림) | None"""
        for kind, title, ok, text_box in self.DIALOGS:
            imgs = self._images(title)
            if imgs:
                hits = self.match_all(imgs[0][0], 0.85, "screen")
                if len(hits) == 1:
                    return kind, hits[0], ok, text_box
        return None

    def alert(self, timeout: float = 4.0) -> tuple[str, bool]:
        """확인창(Confirm '저장하시겠습니까?' → 알림 '저장되었습니다' 처럼 이어서 뜰 수 있다)을 기다렸다가
        글자를 읽고 [확인]을 누른다 → (글자, 찾았는지). [확인]을 눌러도 안 닫히면 멈춘다(저장이 안 된 채 넘어가지 않게)."""
        if self.simulate:
            return "", False
        from . import ocr
        texts: list[str] = []
        end = time.time() + timeout
        while time.time() < end and len(texts) < 3:
            dlg = self.dialog()
            if not dlg:
                if texts:       # 하나를 닫았으면 이어서 뜨는 창만 잠깐 더 본다
                    end = min(end, time.time() + 1.5)
                time.sleep(0.3)
                continue
            kind, (x, y), ok, (l, t, r, b) = dlg
            text = (ocr.read_texts([self.grab(x + self.px(l), y + self.px(t), x + self.px(r), y + self.px(b))], 2)
                    or [""])[0]
            texts.append(f"{kind}: {text}")
            hits = []
            for p, _o in self._images(ok):
                hits = self.match_all(p, 0.85, (x - self.px(60), y + self.px(40), x + self.px(460), y + self.px(200)))
            if len(hits) == 1:
                self.click(("image", hits[0]))
            else:
                from pywinauto.keyboard import send_keys
                send_keys("{ENTER}")
            time.sleep(0.8)
            again = self.dialog()
            if again and again[0] == kind and abs(again[1][0] - x) < 5 and abs(again[1][1] - y) < 5:
                raise Stop(f"확인창 [{kind}]의 [확인]을 눌렀는데 닫히지 않았습니다 — {text[:80]}")
            end = max(end, time.time() + 1.5)
        return " / ".join(texts)[:500], bool(texts)

    def list_rows(self, col: tuple[int, int, int, int], number: tuple[int, int, int, int] | None) -> list[dict]:
        """표의 체크칸 열(col, 화면 좌표) 안 체크칸마다 → {'at', 'checked', '번호'}(위에서부터).
        번호는 체크칸 가운데 기준 number=[l,t,r,b](100% 기준) 칸을 점글꼴 숫자표로만 읽는다(못 읽으면 '')."""
        from . import ocr
        found = []
        for name, checked in (("templates/checkbox_empty.png", False), ("templates/checkbox_checked.png", True)):
            for p, _o in self._images(name):
                found += [(pt, checked) for pt in self.match_all(p, 0.85, col)]
        rows = []
        for (x, y), checked in sorted(found, key=lambda v: v[0][1]):
            if rows and abs(rows[-1]["at"][1] - y) < self.px(6):
                continue
            seen = ""
            if number:
                l, t, r, b = (self.px(v) for v in number)
                seen = ocr.read_digits(self.grab(x + l, y + t, x + r, y + b))
            rows.append({"at": (x, y), "checked": checked, "번호": seen})
        return rows

    def is_checked(self, at: tuple[int, int]) -> bool:
        x, y, d = at[0], at[1], self.px(10)
        return any(self.match_all(p, 0.85, (x - d, y - d, x + d, y + d))
                   for p, _o in self._images("templates/checkbox_checked.png"))

    def red_marks(self, l: int, t: int, r: int, b: int) -> int:
        """영역 안 빨간 점 수 — 훈련인원 현황 「오류여부」 Y 는 빨간 글자다(화면 (144,15,36) 정도)."""
        import numpy as np
        a = np.array(self.grab(l, t, r, b).convert("RGB")).astype(int)
        return int(((a[..., 0] > 110) & (a[..., 0] - a[..., 1] > 70) & (a[..., 0] - a[..., 2] > 60)).sum())

    def text_rows(self, l: int, t: int, r: int, b: int) -> list[int]:
        """세로 띠 안 짙은 글자 줄들의 가운데 y (위에서부터). 줄 사이가 크게 비면(표 끝) 거기서 멈춘다."""
        import numpy as np
        ys = np.where((np.array(self.grab(l, t, r, b).convert("L")) < 110).any(axis=1))[0]
        out: list[int] = []
        start = prev = None
        for y in ys:
            if prev is not None and y - prev > self.px(8):
                out.append(t + (start + prev) // 2)
                if y - prev > self.px(80):
                    start = None
                    break
                start = y
            if start is None and prev is None:
                start = y
            prev = y
        else:
            if prev is not None:
                out.append(t + (start + prev) // 2)
        return out

    def total_value(self, label: str):
        """「산출액 총액」/「신청액 총액」 라벨 오른쪽 첫 숫자 덩어리 → (점 그림 배열, 화면 영역) | None.
        창 폭에 따라 칸 너비가 바뀌어서 거리 대신 '라벨 다음 첫 글자 덩어리'를 잡는다."""
        import numpy as np
        p = self._images(label)
        if not p:
            return None
        hits = self.match_all(p[0][0], float(self.cfg["image_confidence"]), "screen")
        if len(hits) != 1:
            return None
        from PIL import Image
        half = int(Image.open(p[0][0]).width * getattr(self, "scale", 1.0) / 2)
        x, y = hits[0]
        l, t, r, b = x + half + 2, y - self.px(9), x + half + self.px(700), y + self.px(9)
        dark = np.array(self.grab(l, t, r, b).convert("L")) < 110
        cols = np.where(dark.any(axis=0))[0]
        if not len(cols):
            return None
        start = end = cols[0]
        for c in cols[1:]:
            if c - end > self.px(10):
                break
            end = c
        g = dark[:, start:end + 1]
        rows = np.where(g.any(axis=1))[0]
        return g[rows.min():rows.max() + 1], (l + start, t, l + end + 1, b)

    def tidy(self) -> list[str]:
        """멈춘 회차가 남긴 확인창·비용등록 팝업·참여 업체 목록 팝업을 닫는다(다음 회차가 검색화면에서 시작하게)."""
        done: list[str] = []
        closers = (
            ("비용등록 [닫기]", {"scope_image": {"image": "templates/costreg_title.png", "box": [-60, 25, 1950, 70]},
                               "image": "templates/btn_close_costreg.png", "unique": True}),
            ("참여 업체 목록 [닫기]", {"scope_image": {"image": "templates/popup_company_title.png", "box": [650, 15, 740, 50]},
                                   "image": "templates/btn_popup_close.png", "unique": True}),
        )
        for _ in range(4):
            text, found = self.alert(1.0)
            if found:
                done.append(f"확인창 닫음({text[:40]})")
                continue
            for label, target in closers:
                hit = self.find(target)
                if hit:
                    self.click(hit)
                    time.sleep(1.0)
                    done.append(label)
                    break
            else:
                break
        return done

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
        if self.win:
            try:
                self.win.capture_as_image().save(path)
                return
            except Exception:  # noqa: BLE001 — 일부 화면은 창 캡처를 막는다
                pass
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=True).save(path)


def run(folder: Path, dry: bool = False, simulate: bool = False, fill: bool = False,
        companies: set[str] | None = None, learn: bool = False, continued: bool = False,
        auto: bool = False, tidy: bool = False) -> dict:
    """continued: 앞 회차가 검색화면으로 돌아온 뒤라 메뉴 이동(first_round_only)을 건너뛴다.
    auto: 연속 실행 — 대시보드에서 한 번 확인했으니 회차마다 묻지 않는다(최종 신청·미리 채움 끝·다음 회차).
    tidy: 앞 회차가 중간에 멈췄다 — 남은 확인창·팝업부터 닫는다."""
    cfg = config.load()
    d = config.dirs(cfg)
    mdir = macros.path()
    mmeta = macros.meta(mdir)
    spec = macros.spec(mdir.name)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    course, rnd = manifest["과정명"], str(manifest["회차"])
    missing_evidence = set(_resolve_inbox_evidence(manifest, d))
    mode = "simulate" if simulate else "dry-run" if dry else ("학습" if learn else "미리채움") if fill else "실행"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{stamp}_{course}_{rnd}회차"
    logf = d["logs"] / f"{name}.jsonl"

    # 증빙(계산서·수납확인서)이 아직 폴더에 다 안 들어온 업체는 이번에 빼고, 신청완료·불가로 바꾼 업체도 뺀다
    saved = status.load()
    businesses, left_out = [], []
    for b in _selected_businesses(manifest, companies):
        st = (saved.get(b["_key"]) or {}).get("상태", "")
        if b.get("제외사유") and st != "신청가능":     # 사람이 콤보로 신청가능으로 바꾼 업체만 돌린다
            left_out.append(f"{b.get('사업장명')}({b['제외사유']})")
        elif b.get("사업장명", "") in missing_evidence:
            left_out.append(f"{b.get('사업장명')}(증빙 대기)")
        elif st in ("신청완료", "불가"):
            left_out.append(f"{b.get('사업장명')}({st})")
        else:
            businesses.append(b)
    keys = [b["_key"] for b in businesses]
    # 관리번호: 엑셀 → 전에 확인한 번호 → 사업자번호+0(유한회사 빼고). status 키는 원래 값으로 이미 정해져 있다
    known = status.known_numbers()
    for b in businesses:
        b["사업장관리번호"], b["관리번호출처"] = status.resolve_number(b, known)

    summary = {"과정명": course, "회차": rnd, "모드": mode, "폴더": str(folder),
               "매크로": mmeta["id"], "매크로이름": mmeta["표시명"],
               "시작": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "상태": "", "단계수": 0, "완료": 0,
               "자동": 0, "사람": 0, "못찾음": [], "오류": "",
               "신청금액": sum(float(b.get("신청금액") or 0) for b in businesses),
               "업체": [b.get("사업장명", "") for b in businesses], "빠진업체": left_out, "불가업체": []}
    plan = _flatten(spec["steps"], manifest, businesses)
    summary["단계수"] = len(plan)
    print(f"[{mode}] {mmeta['표시명']} · {course} {rnd}회차 — 업체 {len(businesses)}곳, {len(plan)}단계", flush=True)
    if left_out:
        print("  이번에 뺀 업체: " + ", ".join(left_out), flush=True)
    status.record(keys, f01=mmeta["id"], f02=mmeta["표시명"], f03=mode, f04=summary["시작"], f05="",
                  f06="", f07="", f08="진행중", f09="", reset_steps=True)

    def log(rec):
        with open(logf, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(rec, at=datetime.now().strftime("%H:%M:%S")), ensure_ascii=False) + "\n")

    skipped: set[str] = set()      # 이번 회차에서 불가로 뺀 업체 키
    after_round_only = False       # 미리 채움이 끝나 '검색화면 복귀' 단계만 남았을 때

    def drop_company(vals: dict, why: str) -> None:
        k = vals.get("_key")
        if not k:
            raise Ineligible(why)   # 회차 전체 단계에서 난 불가 — 회차를 멈춘다
        if k in skipped:            # 닫기(on_skip) 단계에서 또 불가가 나도 한 번만 센다 (10/30 '초연테크' 두 번)
            return
        skipped.add(k)
        summary["불가업체"].append(vals.get("사업장명", ""))
        status.record(k, f08="불가", f09=why)
        status.update([{"key": k, "상태": "불가", "사유": why}])
        status.ask_later(course, rnd, vals.get("사업장명", ""), why + " — 다음 신청 때 다시 확인 부탁드립니다.")
        print(f"  ✗ {vals.get('사업장명')}: {why} → 이 업체만 빼고 계속합니다", flush=True)

    try:
        if not businesses:
            raise Stop("이번에 신청할 업체가 없습니다 — 증빙 폴더에 계산서·수납확인서가 들어왔는지 확인해 주세요")
        scr = Screen(spec.get("window", ".*HRD.*"), simulate, cfg, mdir)
        if not simulate and scr.windows_scale() != 100:
            summary["배율"] = scr.windows_scale()
            print(f"  ⚠ HRD-Net 이 떠 있는 모니터의 배율이 {summary['배율']}% 입니다 — 100% 로 바꿔야 업체 관리번호를 읽을 수"
                  " 있습니다 (설정 > 디스플레이 > 그 모니터 선택 > 배율)", flush=True)
        if tidy and not simulate:
            summary["정리"] = scr.tidy()
        for i, (step, vals) in enumerate(plan, start=1):
            sid, act = step["id"], step.get("action", "click")
            k = vals.get("_key")
            if k in skipped and not step.get("on_skip"):
                continue
            if step.get("only_on_skip") and k not in skipped:
                continue
            if continued and step.get("first_round_only"):
                continue
            if after_round_only and not step.get("after_round"):
                continue
            if step.get("after_round") and not after_round_only and fill:
                continue                       # 미리 채움에서 복귀는 사람이 [다음 회차로]를 누른 뒤에만
            if skipped and len(skipped) == len(keys) and not step.get("on_skip") and not step.get("after_round"):
                raise Ineligible("고른 업체가 모두 불가라 이 회차는 신청하지 않습니다")
            say = _fmt(step.get("say", ""), vals)
            rec = {"id": sid, "action": act, "say": say}
            _now(d, {"folder": folder.name, "과정명": course, "회차": rnd, "모드": mode, "매크로": mmeta["표시명"],
                     "업체": vals.get("사업장명", ""), "i": i, "n": len(plan), "id": sid, "say": say})
            if scr.keep_place():
                rec["창"] = "최대화/이동 → 제자리로"
                print(f"  {sid:6} HRD-Net 창 크기가 바뀌어 제자리로 되돌렸습니다", flush=True)
            try:
                _do_step(scr, step, vals, rec, d, name, summary, dry, simulate, fill, learn, course, rnd, auto)
            except SkipCompany as e:
                rec["result"] = "불가"
                log(rec)
                drop_company(vals, str(e))
                continue
            except _FillDone:
                summary["상태"] = "채움완료"
                log(rec)
                status.record(keys, step=(sid, "채움"), f06=sid, f07=say)
                if not any(s.get("after_round") for s, _v in plan[i:]):
                    break
                if not auto and ask("filled", f"{course} {rnd}회차 — 미리 채워 보기 끝. 화면을 확인한 뒤 [다음 회차로]를 누르면 "
                       "검색화면으로 돌아가 다음 회차를 시작합니다.", ["next", "stop"]) != "next":
                    break
                after_round_only = True
                continue
            log(rec)
            summary["완료"] += 1
            if step.get("after_round") and rec.get("result") in ("자동", "사람"):
                summary["복귀"] = True
            targets = [k] if k else [x for x in keys if x not in skipped]
            status.record(targets, step=(sid.split("#")[0], rec.get("result", "")), f06=sid, f07=say,
                          **{f: rec[f] for f in ("f10", "f11", "f12") if f in rec})
        if not summary["상태"]:
            summary["상태"] = {"simulate": "모의완료", "dry-run": "점검완료"}.get(mode, "성공")
            if mode == "실행" and summary.get("완료확인") is False:
                summary["상태"] = "확인필요"
    except Ineligible as e:
        summary["상태"], summary["오류"] = "신청불가", str(e)
        print("  신청불가:", e, flush=True)
    except Stop as e:
        summary["상태"], summary["오류"] = ("실패" if "알림" in str(e) else "중단"), str(e)
        print("  멈춤:", e, flush=True)
    except Exception as e:  # noqa: BLE001
        summary["상태"], summary["오류"] = "오류", f"{type(e).__name__}: {e}"
        print("  오류:", summary["오류"], flush=True)
    finally:
        _now(d, None)
    summary["끝"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    alive = [x for x in keys if x not in skipped]
    # 완료 반영은 업체 단위 — 이 회차에서 실제로 신청까지 간 업체만 (result.py → 완료처리대상 CSV 사업장명)
    summary["신청업체"] = [b.get("사업장명", "") for b in businesses if b["_key"] not in skipped]
    status.record(alive, f05=summary["끝"], f08=summary["상태"], f09=summary["오류"][:200])
    if summary["상태"] == "성공":
        status.update([{"key": x, "상태": "신청완료"} for x in alive])

    (d["logs"] / f"{name}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    manifest["올리기"] = {k2: summary[k2] for k2 in ("모드", "상태", "끝", "오류", "매크로")}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {summary['상태']}  (완료 {summary['완료']}/{summary['단계수']}, 자동 {summary['자동']}, "
          f"사람 {summary['사람']}, 못찾음 {len(summary['못찾음'])}, 불가 업체 {len(summary['불가업체'])})"
          f"  기록: {logf.name}", flush=True)
    return summary


class _FillDone(Exception):
    """미리 채워 보기가 confirm 단계에 닿았다."""


def _human(scr: Screen, step: dict, vals: dict, rec: dict, say: str, learn: bool, options: list[str]) -> str:
    """화면 요소를 못 찾았거나 학습 중일 때 사람에게 맡긴다 (클릭은 학습 녹화)."""
    sid, act = step["id"], step.get("action", "click")
    extra = ""
    copy_values = []
    if act == "type":
        text_value = _fmt(step.get("text", ""), vals)
        then_value = _fmt(step.get("then_text", ""), vals)
        extra = f"  입력값: {text_value} {then_value}"
        if sid == "2-a":
            copy_values.append({"label": "과정명", "value": text_value})
        elif sid == "2-r":
            copy_values.append({"label": "회차", "value": text_value})
        elif sid == "2-b":
            copy_values.append({"label": "검색 시작일", "value": text_value})
            if then_value:
                copy_values.append({"label": "검색 종료일", "value": then_value})
        else:
            copy_values.append({"label": "입력값", "value": text_value})
            if then_value:
                copy_values.append({"label": "다음 입력값", "value": then_value})
    if act == "attach":
        file_value = _fmt(step["file"], vals)
        extra = f"  파일: {file_value}"
        copy_values.append({"label": "첨부파일 경로", "value": file_value})
    if vals.get("_key"):
        copy_values.append({"label": "사업장명", "value": str(vals.get("사업장명", ""))})
        if vals.get("사업장관리번호"):
            copy_values.append({"label": "사업장관리번호", "value": str(vals["사업장관리번호"])})
    from .learn_recorder import StepRecorder
    recorder = StepRecorder(scr.win.handle if scr.win else 0, sid, say)
    recorder.start()
    a = ask("human", f"[{sid}] {say}{extra}" + ("  (학습 녹화)" if learn else ""), options, copy_values)
    learned_clicks = recorder.stop(save=a == "ok")
    if learned_clicks:
        rec["learned_clicks"] = learned_clicks
    return a


def _do_step(scr: Screen, step: dict, vals: dict, rec: dict, d: dict, name: str, summary: dict,
             dry: bool, simulate: bool, fill: bool, learn: bool, course: str, rnd: str, auto: bool = False) -> None:
    sid, act = step["id"], step.get("action", "click")
    say = rec["say"]
    company = vals.get("사업장명", "")
    check_only = simulate or dry

    if act == "focus":
        scr.focus()
        rec["result"] = "ok"
        return
    if act == "screenshot":
        p = d["shots"] / f"{name}_{sid}.png"
        scr.shot(p)
        rec["result"], rec["file"] = "ok", p.name
        return
    if act == "wait":
        time.sleep(float(step.get("seconds", 1)))
        rec["result"] = "ok"
        return
    if act == "alert":
        # 저장·고용보험확인 뒤에 뜨는 주황 '알림' 창 → 글자로 오류 판정 후 [확인]
        if check_only:
            rec["result"] = "확인만"
            return
        text, found = scr.alert(float(step.get("seconds", 4)))
        rec["popup"], rec["result"] = text, "자동" if found else "알림없음"
        if not found and step.get("expect"):
            # 저장 확인창을 못 보고 넘어가면 저장이 안 된 채 다음으로 간다(10/30 22단계) — 멈춘다
            _stop_missing(scr, d, name, sid, summary, rec, f"{sid}: 확인창(Confirm/알림)이 보이지 않습니다 — {say}")
        if found and any(w in text for w in ERROR_WORDS):
            if vals.get("_key"):
                raise SkipCompany(f"{sid} 알림: {text[:120]}")
            if "체납" in text or "미납" in text:
                raise Ineligible(f"{sid} 알림: {text[:120]}")
            raise Stop(f"{sid} 뒤 알림: {text[:120]}")
        return
    if act == "verify_done":
        # 신청이 끝나면 상단 버튼이 [회수] [신청서 출력]만 남는다
        if check_only or fill:
            rec["result"] = "확인만"
            return
        hit = scr.find(dict(step.get("target") or {}, _sid=sid))
        summary["완료확인"] = bool(hit)
        rec["result"] = "완료확인" if hit else "확인못함"
        return
    if act == "maximize":
        # 4-3m: 비용등록 팝업이 작게 열리면 오른쪽 「신청액 총액」 칸이 창 밖으로 잘린다(10/30 5회차) → 제목줄을 두 번 눌러 최대화.
        # 이미 화면 왼쪽 위에 붙어 있으면(최대화) 누르지 않는다 — 두 번 누르면 도로 작아진다
        if check_only:
            rec["result"] = "확인만"
            return
        hit = scr.find(dict(step.get("target") or {}, _sid=sid))
        if not hit:
            _stop_missing(scr, d, name, sid, summary, rec, f"{sid}: 비용등록 팝업이 열리지 않았습니다 — {say}")
        sl, st, _sr, _sb = scr.screen_rect()
        x, y = hit[1]
        if x - sl > scr.px(120) or y - st > scr.px(60):
            import pyautogui
            pyautogui.doubleClick(x, y)
            time.sleep(1.2)
            again = scr.find(dict(step.get("target") or {}, wait=3))
            rec["최대화"] = "했음" if again and again[1][1] - st <= scr.px(60) else "안 됨(그대로 진행)"
        else:
            rec["최대화"] = "이미 최대"
        rec["result"] = "자동"
        summary["자동"] += 1
        return
    if act == "verify_errors":
        # 4-4e: 사람에게 묻지 않는다. 훈련인원 현황 각 행의 「오류여부」 칸에 빨간 Y 가 있으면 이 업체 불가.
        # 표를 못 찾으면 '통과'가 아니라 불가(확인 못 한 채 신청하지 않는다)
        if check_only:
            rec["result"] = "확인만"
            return
        _verify_errors(scr, step, rec)
        return

    days = step.get("only_if_older_than_days")
    if days:
        # 화면 기본 검색기간(최근 1년) 안에서 시작한 과정은 날짜를 건드리지 않는다 — 회차로 거르면 충분하다
        try:
            old = (datetime.now() - datetime.strptime(str(vals.get("검색시작", "")), "%Y-%m-%d")).days > int(days)
        except ValueError:
            old = False
        if not old:
            rec["result"] = "건너뜀(기본 검색기간 안)"
            return

    if act == "menu_search":
        # 2: 우측 상단 메뉴검색으로 화면 이동 — 사람에게 넘기지 않는다. 못 하면 이유를 남기고 멈춘다
        if check_only:
            rec["result"] = "확인만"
            return
        how = scr.menu_search(_fmt(step.get("text", ""), vals), step)
        if not how:
            _stop_missing(scr, d, name, sid, summary, rec,
                          f"{sid}: 우측 상단 메뉴검색 칸(돋보기)을 찾지 못했거나 「{step.get('text')}」 화면이 열리지 않았습니다")
        rec["found"], rec["result"] = how, "자동"
        summary["자동"] += 1
        print(f"  {sid:6} {'자동 ' + how:10} {say}", flush=True)
        time.sleep(float(scr.cfg["step_delay"]))
        return

    if act == "click_round_row":
        # 3: 실시회차가 맞는 '신청대상' 행의 [신청]만 누른다. 하나로 정해지지 않으면 누르지 않고 멈춘다
        if simulate:
            rec["result"] = "확인만"
            return
        hits, how, info = scr.round_buttons(rnd, step)
        rec["found"], rec["행찾기"] = how or None, info
        if dry:
            rec["result"] = "확인만"
            print(f"  {sid:6} {f'{rnd}회차 {len(hits)}행':10} {say}  ({info})", flush=True)
            return
        if len(hits) != 1:
            _stop_missing(scr, d, name, sid, summary, rec,
                          f"{sid}: 목록에서 {rnd}회차 '신청대상' 행의 [신청]을 하나로 정하지 못했습니다 "
                          f"([신청] {info.get('신청버튼', 0)}개, 읽은 회차 {info.get('읽은회차', [])}, "
                          f"회차칸 입력확인 {'O' if info.get('회차입력확인') else 'X'}) — 잘못 누르지 않도록 멈춥니다")
        scr.click(hits[0])
        summary["자동"] += 1
        rec["result"] = "자동"
        print(f"  {sid:6} {'자동 ' + how:10} {say}", flush=True)
        _after_click(scr, sid, vals, rec)
        return

    if act == "attach" and not _fmt(step.get("file", ""), vals).strip("{}"):
        if step.get("optional"):
            rec["result"] = "건너뜀(파일 없음)"
            print(f"  {sid:6} {'건너뜀':10} {say} — 파일 없음", flush=True)
            return
        raise SkipCompany(f"{sid}: 첨부할 파일이 없습니다")
    if fill and step.get("confirm"):
        shot = d["shots"] / f"{name}_{sid}_채움.png"
        scr.shot(shot)
        rec["result"], rec["file"] = "채움까지만", shot.name
        print(f"  {sid:6} {'멈춤':10} {say} — 미리 채워 보기라 누르지 않음", flush=True)
        raise _FillDone()

    if act in ("search_company", "check_company_row") and not learn:
        # 4-1·4-2: 관리번호를 점글꼴 숫자표로 읽어 그 업체 행만 체크한다 — 사람에게 넘기지 않는다
        if check_only:
            rec["result"] = "확인만"
            return
        (_search_company if act == "search_company" else _check_company_row)(scr, step, vals, rec, d, name, summary)
        summary["자동"] += 1
        rec["result"] = "자동"
        print(f"  {sid:6} {'자동':10} {say}", flush=True)
        _after_click(scr, sid, vals, rec)
        return

    hit = None if learn else scr.find(dict(step.get("target") or {}, _sid=sid))
    rec["found"] = hit[0] if hit else None
    if not hit and step.get("skip_if_missing") and not learn:
        rec["result"] = "건너뜀(요소 없음)"   # 화면 요소를 아직 못 잡은 보조 단계 — 사람에게 묻지 않는다
        return
    if not hit and not learn and not check_only:
        # v2.2.3 — 사람에게 클릭을 넘기지 않는다(담당자 요청). 화면을 찍어 두고 이 회차를 멈춘다
        _stop_missing(scr, d, name, sid, summary, rec, f"{sid}: 화면 요소를 찾지 못해 멈춥니다 — {say}")
    if not hit:
        summary["못찾음"].append(sid)
        if not check_only and not learn:
            missing_shot = d["shots"] / f"{name}_{sid}_찾기실패.png"
            scr.shot(missing_shot)
            rec["file"] = missing_shot.name
    if check_only:
        rec["result"] = "확인만"
        print(f"  {sid:6} {'찾음 ' + hit[0] if hit else '못찾음':10} {say}", flush=True)
        return
    if step.get("confirm"):
        shot = d["shots"] / f"{name}_{sid}_확인전.png"
        scr.shot(shot)
        rec["file"] = shot.name
        if not auto and ask("confirm", f"★ {course} {rnd}회차 — {say}", ["신청", "stop"]) != "신청":
            raise Stop("사람이 최종 신청을 멈춤")

    if hit:
        box_check = act == "check" and hit[0] == "image"
        if not (box_check and scr.is_checked(hit[1])):     # 이미 체크된 칸을 누르면 풀린다
            scr.click(hit)
        if box_check:
            time.sleep(0.5)
            if not scr.is_checked(hit[1]):
                _stop_missing(scr, d, name, sid, summary, rec, f"{sid}: 체크칸을 눌렀는데 체크되지 않았습니다 — {say}")
        if act == "type":
            scr.type(_fmt(step.get("text", ""), vals))
            if step.get("verify_crop") and hit[0] == "image":
                # 넣은 값을 화면에서 다시 읽는다 (2-r: 3단계가 '회차검색'으로 판정할 근거)
                time.sleep(0.3)
                seen = scr.read_box(hit[1], step["verify_crop"])
                rec["입력확인"] = seen
                if sid == "2-r" and seen == str(rnd):
                    scr.round_typed = str(rnd)
            if step.get("then_text"):
                second = scr.find(step.get("then_target")) if step.get("then_target") else None
                if second:      # 시작일과 종료일 사이에 달력 아이콘이 있어 TAB 대신 칸을 직접 누른다
                    scr.click(second)
                else:
                    from pywinauto.keyboard import send_keys
                    send_keys("{TAB}")
                scr.type(_fmt(step["then_text"], vals))
        elif act == "attach":
            scr.attach(_fmt(step["file"], vals))
        summary["자동"] += 1
        rec["result"] = "자동"
    else:
        if step.get("eligibility_check"):
            options = ["ok", "ineligible", "stop"]
        else:
            options = ["ok", "stop"] if step.get("required") else ["ok", "skip", "ineligible", "stop"] \
                if vals.get("_key") else ["ok", "skip", "stop"]
        a = _human(scr, step, vals, rec, say, learn, options)
        if a == "ineligible":
            if vals.get("_key"):
                raise SkipCompany(f"{sid}: 사람이 신청불가로 판단")
            raise Ineligible(f"{sid}: 훈련생 오류 또는 고용보험 체납으로 신청 불가")
        if a == "stop":
            raise Stop(f"{sid}에서 사람이 중단")
        summary["사람"] += 1
        rec["result"] = "건너뜀" if a == "skip" else "사람"

    if act == "click" and step.get("verify_amount") and rec.get("result") == "자동":
        _verify_amount(scr, step, vals, rec, hit)

    _after_click(scr, sid, vals, rec)


def _has_shape(image, template_path: Path, threshold: float = 0.95) -> bool:
    """칸 이미지에 글자 그림이 있는지 — 짙은 점만 남겨 비교한다(행 배경색이 선택·보통이어도 같게)."""
    import cv2
    import numpy as np

    cell = (np.array(image.convert("L")) < 110).astype(np.uint8) * 255
    shape = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if shape is None or shape.shape[0] > cell.shape[0] or shape.shape[1] > cell.shape[1]:
        return False
    shape = (shape < 110).astype(np.uint8) * 255
    return float(cv2.matchTemplate(cell, shape, cv2.TM_CCOEFF_NORMED).max()) >= threshold


def _after_click(scr: Screen, sid: str, vals: dict, rec: dict) -> None:
    """단계 뒤 잠깐 기다렸다가 HRD-Net 알림창에 오류 글자가 있으면 업체를 빼거나 회차를 멈춘다."""
    time.sleep(float(scr.cfg["step_delay"]))
    pop = scr.popup_text()
    if pop:
        rec["popup"] = pop
        if any(w in pop for w in ERROR_WORDS):
            if vals.get("_key"):
                raise SkipCompany(f"{sid} 뒤 알림: {pop[:120]}")
            raise Stop(f"{sid} 뒤 알림: {pop[:120]}")


def _stop_missing(scr: Screen, d: dict, name: str, sid: str, summary: dict, rec: dict, why: str) -> None:
    """사람에게 맡기지 않는 단계에서 화면 요소를 못 찾았을 때 — 화면을 찍어 두고 이 회차를 멈춘다."""
    summary["못찾음"].append(sid)
    shot = d["shots"] / f"{name}_{sid}_찾기실패.png"
    scr.shot(shot)
    rec["file"], rec["result"] = shot.name, "멈춤"
    raise Stop(why)


def _company_rows(scr: Screen, step: dict, key: str, wait: float = 0) -> list[dict]:
    """step[key] = {scope_image, col:[l,t,r,b](기준점 기준 체크칸 열), number:[l,t,r,b](체크칸 기준 관리번호 칸)} → 행 목록."""
    spec = step.get(key) or {}
    end = time.time() + wait
    while True:
        _region, anchor = scr._find_region(spec)
        rows = []
        if anchor:
            l, t, r, b = (scr.px(v) for v in spec["col"])
            rows = scr.list_rows((anchor[0] + l, anchor[1] + t, anchor[0] + r, anchor[1] + b), tuple(spec["number"]))
        if rows or time.time() >= end:
            return rows
        time.sleep(0.5)


def _tick(scr: Screen, d: dict, name: str, sid: str, summary: dict, rec: dict, row: dict, what: str) -> None:
    """행 체크칸을 체크 상태로(이미 체크면 그대로) — 누른 뒤 체크 표시를 다시 확인한다."""
    if not row["checked"]:
        scr.click(("image", row["at"]))
        time.sleep(0.5)
    if not scr.is_checked(row["at"]):
        _stop_missing(scr, d, name, sid, summary, rec, f"{sid}: {what} 체크칸이 체크되지 않았습니다")


def _search_company(scr: Screen, step: dict, vals: dict, rec: dict, d: dict, name: str, summary: dict) -> None:
    """4-1: 참여 업체 목록 팝업 아래 「사업장목록」에서 사업장관리번호가 같은 행 하나만 체크한다(사람에게 넘기지 않는다).
    1) 목록을 그대로 읽는다 — 관리번호 열은 점글꼴 숫자표로만 읽어서 못 읽으면 '' (다른 업체를 고를 수 없다)
    2) 없으면(목록이 길어 안 보이는 등) 관리번호 칸에 번호를 넣고 [검색] 뒤 다시 읽는다
    3) 그래도 하나로 안 정해지면 이 업체만 불가로 빼고 관리번호 확인을 요청한다"""
    company = str(vals.get("사업장명", ""))
    no = re.sub(r"\D", "", str(vals.get("사업장관리번호", "") or ""))
    source = str(vals.get("관리번호출처", "") or "")
    rec["관리번호"], rec["관리번호출처"] = no, source
    if not scr.find(step.get("popup")):
        _stop_missing(scr, d, name, step["id"], summary, rec, f"{step['id']}: 참여 업체 목록 팝업이 보이지 않습니다")
    if not no:
        raise SkipCompany(f"사업장관리번호를 알 수 없습니다({source or '엑셀·사업자번호 없음'})")
    for attempt in ("목록", "검색"):
        if attempt == "검색":
            box, button = scr.find(step.get("input")), scr.find(step.get("search_button"))
            if not (box and button):
                rec["검색"] = "관리번호 칸/[검색]을 못 찾음"
                break
            scr.click(box)
            scr.type(no)
            scr.click(button)
            time.sleep(float(scr.cfg["step_delay"]) + 0.7)
        rows = _company_rows(scr, step, "rows", wait=3)
        rec.setdefault("읽은번호", {})[attempt] = [r["번호"] for r in rows]
        same = [r for r in rows if r["번호"] == no]
        if len(same) == 1:
            _tick(scr, d, name, step["id"], summary, rec, same[0], "사업장목록")
            rec["f11"] = f"관리번호 일치({source or '번호'}, {attempt})"
            if source not in ("엑셀", "확인됨"):
                status.learn_number(company, no, f"참여 업체 목록 번호 일치({source})")
            return
        if len(same) > 1:
            break                      # 같은 번호가 여러 줄 — 고르지 않는다
    why = f"참여 업체 목록에서 관리번호 {no}({source}) 행을 하나로 찾지 못했습니다"
    rec["f11"] = why
    raise SkipCompany(why + " — 사업장관리번호 확인 필요")


def _check_company_row(scr: Screen, step: dict, vals: dict, rec: dict, d: dict, name: str, summary: dict) -> None:
    """4-2: 위쪽 「비용신청대상 사업장」 목록에서 이 업체(관리번호) 행만 체크하고, 앞 업체 행 체크는 푼다."""
    no = re.sub(r"\D", "", str(vals.get("사업장관리번호", "") or ""))
    rows = _company_rows(scr, step, "rows", wait=5)
    same = [r for r in rows if r["번호"] == no]
    if len(same) != 1:
        rec["읽은번호"] = [r["번호"] for r in rows]
        _stop_missing(scr, d, name, step["id"], summary, rec,
                      f"{step['id']}: 비용신청대상 사업장에서 관리번호 {no} 행을 하나로 찾지 못했습니다 ({len(rows)}줄)")
    for r in rows:
        if r is not same[0] and r["checked"]:
            scr.click(("image", r["at"]))          # 한 번에 한 업체만 비용등록한다
            time.sleep(0.3)
    _tick(scr, d, name, step["id"], summary, rec, same[0], "비용신청대상 사업장")


def _verify_errors(scr: Screen, step: dict, rec: dict) -> None:
    """4-4e: 훈련인원 현황 표의 행(체크칸)마다 「오류여부」 칸에 빨간 Y 가 있는지 본다 → 있으면 이 업체 불가."""
    end = time.time() + float(step.get("wait", 5))
    err = seq = []
    while True:
        err = [h for p, _o in scr._images(step.get("error_header")) for h in scr.match_all(p, 0.85, "screen")]
        seq = [h for p, _o in scr._images(step.get("row_header")) for h in scr.match_all(p, 0.85, "screen")]
        if (len(err) == 1 and len(seq) == 1) or time.time() >= end:
            break
        time.sleep(0.5)
    if len(err) != 1 or len(seq) != 1:
        raise SkipCompany("훈련인원 현황 표(오류여부 칸)를 찾지 못해 오류여부를 확인하지 못했습니다")
    (ex, _ey), (sx, sy) = err[0], seq[0]
    # 오류가 있는 훈련생 행에는 체크칸이 없다(10/30 19회차) — 행은 「연번」 열 글자로 세고, Y 는 「오류여부」 열의 빨간 줄로 센다.
    # 「선택 인원」 노란 줄 아래부터 본다. 비용등록 창은 4-3m 에서 최대화해 두어 아래쪽은 창 안이다
    top, bottom = sy + scr.px(55), sy + scr.px(step.get("rows_height", 900))
    rows = scr.text_rows(sx + scr.px(-50), top, sx + scr.px(-25), bottom)
    if not rows:
        raise SkipCompany("훈련인원 현황에 훈련생 행이 보이지 않습니다")
    half = scr.px(20)
    bad = sum(scr.red_marks(ex - scr.px(16), y - half, ex + scr.px(16), y + half) >= 5 for y in rows)
    rec["오류여부"] = f"{len(rows)}명 중 Y {bad}명"
    if bad:
        raise SkipCompany(f"훈련인원 오류여부 Y {bad}명 — 신청 불가")
    rec["result"] = "자동통과"


def _verify_amount(scr: Screen, step: dict, vals: dict, rec: dict, hit) -> None:
    """4-5: [산출액→신청액] 뒤 「신청액 총액」 숫자가 「산출액 총액」 숫자와 점 하나까지 같고 0 이 아닌지(글자 읽기 없이 그림 비교).
    0 이면 한 번 더 누른다. 그래도 다르면 이 업체 불가. 대시보드 금액과의 비교는 OCR 로 읽어 기록만 한다."""
    from . import ocr
    expected = _num(str(int(float(vals.get("신청금액") or 0)))) or 0
    for attempt in (1, 2):
        time.sleep(float(scr.cfg["step_delay"]) + 0.4)
        c, a = scr.total_value(step.get("computed_label")), scr.total_value(step.get("applied_label"))
        if not c or not a:
            raise SkipCompany("산출액·신청액 총액 칸을 찾지 못해 금액을 확인하지 못했습니다")
        same = c[0].shape == a[0].shape and bool((c[0] == a[0]).all())
        if same and a[0].shape[1] >= scr.px(12):          # 한 글자(0)보다 넓어야 금액이 들어간 것
            seen = _num((ocr.read_texts([scr.grab(*c[1])], 4, binarize=True) or [""])[0]) or 0
            rec["f10"] = f"산출액 = 신청액 (그림 일치) · 읽은 금액 {seen:,} / 대시보드 {expected:,}"
            if expected and seen and seen != expected:
                rec["f10"] += " — 대시보드와 다름(기록만, HRD 산출액 기준)"
            return
        if attempt == 1:
            scr.click(hit)                   # 사이드 패널에선 넘어갔는데 실제로 안 눌린 경우가 있었다
    rec["f10"] = "산출액 ≠ 신청액"
    raise SkipCompany("신청액 총액이 산출액 총액과 같지 않습니다")


def run_all(dry: bool = False, simulate: bool = False, fill: bool = False, only: list[str] | None = None,
            companies: set[str] | None = None, learn: bool = False, auto: bool = False) -> None:
    """only 가 있으면 그 회차 폴더들만, 없으면 아직 신청 안 된 회차 전부.
    증빙은 실행할 때 폴더를 다시 보고 판단하므로 manifest 의 정리 상태는 따지지 않는다."""
    d = config.dirs()
    todo = []
    for m in sorted(d["outbox"].glob("*/manifest.json")):
        j = json.loads(m.read_text(encoding="utf-8"))
        if only is not None:
            if m.parent.name in only:
                todo.append(m.parent)
        elif (j.get("올리기") or {}).get("상태") != "성공":
            todo.append(m.parent)
    if only:   # 대시보드에서 고른 순서대로
        todo.sort(key=lambda p: only.index(p.name))
    print(f"올릴 회차 {len(todo)}개" + (f" · 업체 {len(companies)}곳" if companies is not None else ""), flush=True)
    s: dict = {}
    for k, f in enumerate(todo):
        s = run(f, dry=dry, simulate=simulate, fill=fill, companies=companies, learn=learn,
                continued=bool(s.get("복귀")), auto=auto, tidy=bool(s) and not s.get("복귀"))
        if s["상태"] in ("중단", "오류", "실패") and not (dry or simulate) and k < len(todo) - 1:
            if auto:
                print(f"  → {f.name}: {s['상태']} — 연속 실행이라 화면을 정리하고 다음 회차로 갑니다", flush=True)
                continue
            if ask("next", f"{f.name}: {s['상태']} — 다음 회차로 넘어갈까요?", ["next", "stop"]) != "next":
                break
