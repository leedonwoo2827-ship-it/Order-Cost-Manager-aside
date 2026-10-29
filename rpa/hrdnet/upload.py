"""3 올리기 — 사람이 로그인해 둔 HRD-Net 설치 프로그램에 매크로(rpa/macros/<id>/steps.yaml) 순서대로 입력한다.

화면 요소를 찾는 순서: UIA(pywinauto) → 화면 이미지(cv2) → 사람 안내(답을 기다림).
그래서 selector 를 하나도 안 채운 지금도 "단계별 안내 + 기록" 도구로 돈다. 채울수록 자동이 된다.

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
        """팝업 창 제목으로 찾는 범위를 좁힌다 — 같은 이름 버튼(비용등록·저장·닫기)이 여러 개라서."""
        if self.simulate:
            return None
        if not title:
            return self.win
        for where in (lambda: self.win.child_window(title_re=title, control_type="Window"),
                      lambda: self.desk.window(title_re=title)):
            try:
                w = where()
                if w.exists(timeout=1):
                    return w
            except Exception:  # noqa: BLE001
                continue
        return None

    def find(self, target: dict | None):
        """→ ('uia', 요소) | ('image', (x, y)) | None"""
        if self.simulate or not target:
            return None
        box = self.scope(target.get("scope"))
        if box is None:
            return None
        uia = {k: v for k, v in (target.get("uia") or {}).items() if v not in (None, "")}
        if uia:
            try:
                el = box.child_window(**uia)
                if el.exists(timeout=2):
                    return ("uia", el)
            except Exception:  # noqa: BLE001 — 같은 조건이 여러 개면 found_index 를 채운다
                pass
        # image: "a.png" 또는 [{image, offset:[dx,dy]}, …] — offset 은 그림 가운데에서 얼마나 떨어진 곳을 누를지.
        # HRD-Net 검색화면은 칸 배치가 고정이라, 늘 같은 모양인 기준 그림(회색 칸 ▼) 하나로 과정명·회차·검색 자리를 잡는다.
        for img, offset in self._images(target.get("image")):
            at = self._match(box, img)
            if at:
                return ("image", (at[0] + offset[0], at[1] + offset[1]))
        return self.learned(target.get("_sid", ""), target.get("learned", "template"), box)

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

            box = box or self.win
            screen = cv2.cvtColor(np.array(box.capture_as_image()), cv2.COLOR_RGB2GRAY)
            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if template is None or template.shape[0] > screen.shape[0] or template.shape[1] > screen.shape[1]:
                return []
            scores = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(scores >= threshold)
            rect = box.rectangle()
            th, tw = template.shape[:2]
            keep: list[tuple[int, int]] = []
            for _s, x, y in sorted(((float(scores[y, x]), int(x), int(y)) for y, x in zip(ys, xs)), reverse=True):
                cx, cy = rect.left + x + tw // 2, rect.top + y + th // 2
                if all(abs(cx - a) > tw // 2 or abs(cy - b) > th // 2 for a, b in keep):
                    keep.append((cx, cy))
            return keep
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

    def texts(self, scope: str | None = None) -> list[str]:
        """창(또는 팝업) 안의 글자들. UIA 로 안 보이면 빈 목록 → 검증은 '확인못함'으로 넘어간다."""
        if self.simulate:
            return []
        box = self.scope(scope)
        if box is None:
            return []
        out = []
        try:
            for c in box.descendants():
                t = (c.window_text() or "").strip()
                if t:
                    out.append(t)
        except Exception:  # noqa: BLE001
            pass
        return out

    def alert(self, timeout: float = 4.0) -> tuple[str, bool]:
        """'알림' 창을 기다렸다가 글자를 읽고 [확인]을 누른다 → (글자, 찾았는지)."""
        if self.simulate:
            return "", False
        end = time.time() + timeout
        while time.time() < end:
            box = self.scope("알림")
            if box is not None:
                text = " ".join(self.texts("알림"))[:500]
                try:
                    box.child_window(title_re="확인", control_type="Button").click_input()
                except Exception:  # noqa: BLE001
                    from pywinauto.keyboard import send_keys
                    send_keys("{ENTER}")
                return text, True
            time.sleep(0.3)
        return "", False

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


def _amount_after(texts: list[str], label: str) -> int | None:
    """'신청액 총액 2,123,550' 처럼 라벨 뒤(같은 칸이나 다음 몇 칸)의 금액."""
    for i, t in enumerate(texts):
        if label in t.replace(" ", ""):
            rest = t.replace(" ", "").split(label, 1)[1]
            for cand in [rest, *texts[i + 1:i + 4]]:
                n = _num(cand)
                if n is not None:
                    return n
    return None


def run(folder: Path, dry: bool = False, simulate: bool = False, fill: bool = False,
        companies: set[str] | None = None, learn: bool = False, continued: bool = False) -> dict:
    """continued: 앞 회차가 검색화면으로 돌아온 뒤라 메뉴 이동(first_round_only)을 건너뛴다."""
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
                _do_step(scr, step, vals, rec, d, name, summary, dry, simulate, fill, learn, course, rnd)
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
                if ask("filled", f"{course} {rnd}회차 — 미리 채워 보기 끝. 화면을 확인한 뒤 [다음 회차로]를 누르면 "
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
             dry: bool, simulate: bool, fill: bool, learn: bool, course: str, rnd: str) -> None:
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
    if act == "verify_errors":
        # 4-4e: 담당자 요청 — 사람에게 묻지 않는다. 오류여부 Y 가 읽히면 이 업체 불가, 못 읽으면 통과(금액 확인이 한 번 더 막는다)
        texts = scr.texts(step.get("scope"))
        if not texts:
            rec["result"] = "자동통과(읽기불가)"
            return
        joined = " ".join(texts)
        if "오류여부" in joined and re.search(r"(?:^|\s)Y(?:\s|$)", joined.split("오류여부", 1)[1][:4000]):
            raise SkipCompany("훈련인원 오류여부 Y — 신청 불가")
        if "체납" in joined:
            raise SkipCompany("고용보험 체납 — 신청 불가")
        rec["result"] = "자동통과"
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

    hit = None if learn else scr.find(dict(step.get("target") or {}, _sid=sid))
    rec["found"] = hit[0] if hit else None
    if not hit and step.get("skip_if_missing") and not learn:
        rec["result"] = "건너뜀(요소 없음)"   # 화면 요소를 아직 못 잡은 보조 단계 — 사람에게 묻지 않는다
        return
    if not hit and step.get("no_human") and not learn and not check_only:
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
        if ask("confirm", f"★ {course} {rnd}회차 — {say}", ["신청", "stop"]) != "신청":
            raise Stop("사람이 최종 신청을 멈춤")

    if act == "search_company":
        _search_company(scr, step, vals, rec, hit, say, learn)
    elif hit:
        scr.click(hit)
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


def _number_after(texts: list[str], company: str) -> str:
    """사업장목록 글자에서 업체명 다음에 나오는 10~11자리 숫자 = 그 업체의 사업장관리번호."""
    ck = status.company_key(company)
    for i, t in enumerate(texts):
        if ck and status.company_key(t) == ck:
            for nxt in texts[i + 1:i + 4]:
                digits = re.sub(r"\D", "", nxt)
                if 10 <= len(digits) <= 11:
                    return digits
    return ""


def _search_company(scr: Screen, step: dict, vals: dict, rec: dict, hit, say: str, learn: bool) -> None:
    """4-1: 참여 업체 목록 팝업에서 이 업체를 찾아 체크한다.
    1) 관리번호(엑셀 · 전에 확인 · 사업자번호+0)로 검색 → 결과 업체명이 같을 때만 체크 (틀리면 누르지 않는다)
    2) 유한회사이거나 1)이 안 맞으면 → 검색칸을 비워 사업장목록(그 회차 참여업체 전부)에서 업체명으로 관리번호를 읽어 다시 검색
    3) 그래도 안 되면 멈추고 사람에게 말한다(그래도 진행 / 이 업체 불가 / 멈춤). 확인된 번호는 업체별로 저장."""
    company = str(vals.get("사업장명", ""))
    no, source = str(vals.get("사업장관리번호", "") or ""), str(vals.get("관리번호출처", "") or "")
    scope = (step.get("target") or {}).get("scope")
    ck = status.company_key(company)
    rec["관리번호"], rec["관리번호출처"] = no, source

    def search(number: str) -> list[str] | None:
        """검색칸에 번호(빈칸이면 전체) → [검색] → 팝업 글자. 화면 요소를 못 잡으면 None."""
        if not hit:
            return None
        scr.click(hit)
        scr.type(number)
        button = scr.find(step.get("search_button"))
        if not button:
            return None
        scr.click(button)
        time.sleep(float(scr.cfg["step_delay"]))
        return scr.texts(scope)

    def check_row(number: str, how: str) -> bool:
        row = scr.find(step.get("row_check"))
        if not row:
            return False
        scr.click(row)
        rec["result"], rec["f11"] = "자동", f"일치({how})"
        if how not in ("엑셀", "확인됨"):
            status.learn_number(company, number, f"업체명 확인({how})")
        return True

    tried = ""
    texts: list[str] | None = None
    if no:   # 1) 번호로 검색 → 업체명 확인
        texts = search(no)
        if texts and any(ck and status.company_key(t) == ck for t in texts) and check_row(no, source or "번호"):
            return
        if texts == [] and source in ("엑셀", "확인됨") and check_row(no, source):
            # 팝업 글자를 못 읽어 업체명은 확인 못 하지만, 엑셀·전에 확인한 번호라 믿고 체크한다
            rec["f11"] = f"번호로 체크({source}, 업체명 글자 못 읽음)"
            return
        tried = "글자 안 읽힘" if texts == [] else "화면 요소 못 찾음" if texts is None else "검색 결과 업체명 다름"
    if texts is None or texts:
        # 2) 목록 전체에서 업체명으로 번호 읽기 (유한회사·추정 틀림)
        texts = search("")
        found = _number_after(texts or [], company)
        if found and found != no:
            again = search(found)
            if again and any(status.company_key(t) == ck for t in again) and check_row(found, "목록에서 확인"):
                return
    # 3) 사람에게 — 왜 못 찾았는지 정확히 말한다
    why = (f"관리번호 {no}({source})로 찾았지만 {tried}" if no else f"관리번호 {source}")
    rec["f11"] = f"사람 확인 — {why}"
    if source.startswith("확인필요"):
        status.ask_later(vals.get("과정명", ""), vals.get("회차", ""), company,
                         f"사업장관리번호를 알 수 없습니다({source}). 알려 주시면 다음부터 자동으로 찾겠습니다.")
    if hit and texts:
        # 목록 글자를 읽었는데 이 업체가 없음(번호 추정이 틀림 등) → 멈추지 않고 이 업체만 불가로 빼고 다음 업체로.
        # 글자를 못 읽는 것(texts == [])은 '틀림'이 아니라 '확인 수단 없음'이라 아래 사람 단계로 간다
        status.ask_later(vals.get("과정명", ""), vals.get("회차", ""), company,
                         f"참여 업체 목록에서 찾지 못해 건너뛰었습니다 ({why}). 사업장관리번호를 알려 주시면 다시 신청하겠습니다.")
        raise SkipCompany(f"참여 업체 목록에서 확인 불가 — 관리번호 확인 필요 ({why})")
    else:                               # 화면 요소를 아직 못 잡음(녹화 전) → 사람 단계(클릭 학습)
        a = _human(scr, step, vals, rec, say + (f" (관리번호 {source})" if source else ""), learn,
                   ["ok", "ineligible", "stop"])
    if a == "ineligible":
        raise SkipCompany(f"참여 업체 목록에서 업체 확인 불가 ({why})")
    if a == "stop":
        raise Stop(f"{step['id']}에서 사람이 중단")
    rec["result"] = "사람"


def _verify_amount(scr: Screen, step: dict, vals: dict, rec: dict, hit) -> None:
    """4-5: [산출액→신청액] 뒤 신청액 총액 == 산출액 총액 == 대시보드 신청금액. 0 이면 한 번 더 누른다."""
    expected = _num(str(int(float(vals.get("신청금액") or 0)))) or 0
    for attempt in (1, 2):
        time.sleep(float(scr.cfg["step_delay"]))
        texts = scr.texts(step.get("target", {}).get("scope"))
        applied, computed = _amount_after(texts, "신청액총액"), _amount_after(texts, "산출액총액")
        if applied is None:
            rec["f10"] = "확인못함(글자 안 읽힘)"
            return
        if applied == 0 and attempt == 1:
            scr.click(hit)                   # 사이드 패널에선 넘어갔는데 실제로 안 눌린 경우가 있었다
            continue
        ok = applied == computed and (not expected or applied == expected)
        rec["f10"] = f"신청 {applied:,} / 산출 {computed or 0:,} / 대시보드 {expected:,}" + (" ✓" if ok else " ✗")
        if ok:
            return
        a = ask("company", f"금액이 맞지 않습니다 — {rec['f10']}. 화면을 확인해 주세요.", ["proceed", "ineligible", "stop"])
        if a == "ineligible":
            raise SkipCompany("신청금액 불일치")
        if a == "stop":
            raise Stop(f"{step['id']} 금액 불일치로 사람이 중단")
        return


def run_all(dry: bool = False, simulate: bool = False, fill: bool = False, only: list[str] | None = None,
            companies: set[str] | None = None, learn: bool = False) -> None:
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
                continued=bool(s.get("복귀")))
        if s["상태"] in ("중단", "오류", "실패") and not (dry or simulate) and k < len(todo) - 1:
            if ask("next", f"{f.name}: {s['상태']} — 다음 회차로 넘어갈까요?", ["next", "stop"]) != "next":
                break
