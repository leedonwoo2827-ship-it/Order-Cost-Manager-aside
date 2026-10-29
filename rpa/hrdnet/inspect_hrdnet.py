"""HRD-Net 화면 진단 — 담당자 PC 에서 로그인한 뒤 한 번 돌린다.

UIA 로 버튼·칸의 이름이 보이면 steps.yaml 에 uia target 을 채우고(빠르고 튼튼함),
안 보이면 버튼 이미지를 templates/ 에 넣어 image target 을 쓴다.
결과: logs/inspect_<시각>.txt + .png(HRD-Net 창 화면) — 훈련생 정보가 보이는 화면(비용등록 팝업)에서는 돌리지 않는다
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from . import config

KEY_BUTTONS = ["검색", "신청", "비용등록", "저장", "닫기", "고용보험확인", "훈련비용 신청", "첨부", "산출액"]
CHECK_STEPS = ["2-a", "2-r", "2-c"]       # 검색화면 칸 — 지금 화면에서 찾기만 해 본다
TEMPLATES = {                              # 그림 이름 → 무엇인지 (화면에 몇 개, 가장 비슷한 점수)
    "menu_search_icon.png": "첫 화면 우측 상단 메뉴검색 돋보기",
    "round_box_anchor.png": "검색화면 기준 그림(회색 칸 ▼)",
    "learned/2-c_1.png": "[검색] 버튼",
    "claim_button.png": "목록의 [신청] 버튼",
}
_JUMIN = re.compile(r"\d{6}\s*-\s*[0-9*]{1,7}")


def _mask(line: str) -> str:
    """진단 파일에 주민번호 모양이 들어가지 않게."""
    return _JUMIN.sub("######-*******", line)


def _scores(scr, path) -> tuple[float, tuple[int, int], int]:
    """그림이 화면 어디에 얼마나 비슷하게 있는지 → (최고 점수, 위치, 0.85 이상 개수)."""
    import cv2
    import numpy as np

    screen = cv2.cvtColor(np.array(scr.win.capture_as_image()), cv2.COLOR_RGB2GRAY)
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    scores = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _lo, best, _at0, at = cv2.minMaxLoc(scores)
    rect = scr.win.rectangle()
    return best, (rect.left + at[0] + template.shape[1] // 2, rect.top + at[1] + template.shape[0] // 2),         len(scr.match_all(path, 0.85))


def automation_check(shot_path=None) -> list[str]:
    """v2.2.2 자동화가 지금 화면에서 무엇을 찾는지 — 누르거나 입력하지 않고 찾기만 한다.
    HRD-Net 화면은 UIA·웹 구조로 보이지 않아(10/29 진단) 그림 찾기와 OCR(윈도우 내장 글자 읽기)로 판정한다.
    첫 화면에서는 메뉴검색 돋보기, 비용신청관리(위탁) 검색 목록에서는 기준 그림·[신청] 버튼·각 행의 회차 읽기를 본다.
    shot_path 를 주면 HRD-Net 창 화면을 저장한다 — 실제 화면으로 그림을 다시 다듬는 데 쓴다."""
    from . import macros, ocr
    from .upload import Screen

    out = ["### 자동화 판정 (v2.2.2 — 찾기만 함, 누르지 않음)"]
    try:
        mdir = macros.path()
        spec = macros.spec(mdir.name)
        scr = Screen(spec.get("window", ".*HRD.*"), False, config.load(), mdir)
    except Exception as exc:  # noqa: BLE001
        return out + [f"HRD-Net 창 열기 실패: {type(exc).__name__}: {exc}"]
    rect = scr.win.rectangle()
    out.append(f"HRD-Net 창 위치·크기: ({rect.left},{rect.top}) {rect.width()}×{rect.height()}  (영상 기준 1400×1030)")
    if shot_path:
        try:
            scr.win.capture_as_image().save(shot_path)
            out.append(f"화면 저장: {shot_path}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"화면 저장 실패: {type(exc).__name__}")
    for name, what in TEMPLATES.items():
        path = mdir / "templates" / name
        try:
            best, at, n = _scores(scr, path)
            out.append(f"그림 {what:24} 최고 {best:.2f} 위치 {at}  0.85이상 {n}개")
        except Exception as exc:  # noqa: BLE001
            out.append(f"그림 {what:24} 확인 실패 ({type(exc).__name__})")
    steps = {s.get("id"): s for s in spec.get("steps", []) if isinstance(s, dict)}
    box_seen = ""
    for sid in CHECK_STEPS:
        step = steps.get(sid) or {}
        hit = scr.find(dict(step.get("target") or {}, _sid=sid))
        out.append(f"단계 {sid:4} {step.get('say', '')[:24]!r}: {('자리 ' + str(hit[1])) if hit else '못 찾음'}")
        if hit and sid == "2-r":
            x, y = hit[1]
            l, t, r, b = step.get("verify_crop") or [-21, -9, 22, 9]
            im = scr.grab(x + l, y + t, x + r, y + b)
            box_seen = ocr.read_digits(im)
            out.append(f"      회차 칸 글자 — 점글꼴: {box_seen or '못 읽음'!r}  (참고 윈도우OCR: {ocr.read_texts([im], 6, True)[0]!r})")
    claim = steps.get("3") or {}
    buttons = []
    for path, _o in scr._images(claim.get("button")):
        buttons = scr.match_all(path, 0.9)
    if buttons:
        l, t, r, b = claim.get("round_cell") or (-475, -36, -420, 6)
        cells = [scr.grab(x + l, y + t, x + r, y + b) for x, y in buttons]
        readings = ocr.read_numbers(cells)
        out.append(f"목록 [신청] {len(buttons)}개 — 각 행 실시회차 읽기(점글꼴 먼저): " +
                   ", ".join(f"{v or '?'}@{y}" for (x, y), v in zip(buttons, readings)) +
                   f"  (참고 윈도우OCR: {ocr.read_texts(cells, 6, True)})")
        if box_seen:
            hits = [v for v in readings if v == box_seen]
            out.append(f"3단계 예상: {box_seen}회차 [신청] " +
                       ("1개 → 자동으로 누름" if len(hits) == 1 else f"{len(hits)}개 → 멈춤(하나로 정하지 못함)"))
        out.append("※ 읽은 회차가 실제 화면과 다르면 알려 주세요 (3단계는 이 값이 맞아야 자동으로 누릅니다)")
    else:
        out.append("목록 [신청] 버튼: 없음 (검색 목록 화면이 아니거나 그림이 안 맞음)")
    return out


def run() -> None:
    try:
        from pywinauto import Desktop
    except ImportError:
        print("pywinauto 가 없습니다 — setup.bat 을 먼저 실행하세요")
        return
    from . import macros

    d = config.dirs()
    out = d["logs"] / f"inspect_{datetime.now():%Y%m%d_%H%M%S}.txt"
    lines = []
    pattern = macros.window_pattern()
    wins = [w for w in Desktop(backend="uia").windows() if re.search(pattern, w.window_text() or "", re.I)]
    if not wins:
        print(f"설정한 창 제목 패턴과 맞는 창이 없습니다: {pattern!r}")
        print("지금 열린 창:", [w.window_text() for w in Desktop(backend="uia").windows() if w.window_text()][:20])
        return
    for w in wins:
        title = w.window_text()
        pid = w.process_id()
        lines.append(f"### UIA 창: {title!r}  class={w.class_name()!r}  pid={pid}")
        found, named, total = {}, 0, 0
        for c in w.descendants():
            total += 1
            t = (c.window_text() or "").strip()
            ct = c.element_info.control_type
            aid = c.element_info.automation_id
            if t:
                named += 1
            for b in KEY_BUTTONS:
                if t and b in t and b not in found:
                    found[b] = (ct, t, aid)
            if total <= 3000:
                lines.append(f"{ct:14} title={t[:40]!r:44} auto_id={aid!r}")
        lines.insert(1, f"요소 {total}개, 이름 있는 요소 {named}개")
        lines.insert(2, "핵심 버튼: " + ", ".join(f"{b}={'O' if b in found else 'X'}" for b in KEY_BUTTONS))
        print(f"창 {title!r}: 요소 {total}개, 이름 있음 {named}개")
        for b in KEY_BUTTONS:
            print(f"  {b:10} {'O  ' + str(found[b][:2]) if b in found else 'X'}")
        verdict = ("→ UIA 방식 가능: steps.yaml 의 uia 에 title/control_type 을 채우세요"
                   if len(found) >= 4 else
                   "→ UIA 로는 잘 안 보입니다: 버튼 이미지를 templates/ 에 넣고 image target 을 쓰세요")
        print(verdict)
        lines.insert(3, verdict)

        # 대량 자동화 판단용: 같은 프로세스의 Win32 클래스 트리도 조사한다.
        win32_wins = [x for x in Desktop(backend="win32").windows()
                      if x.process_id() == pid and re.search(pattern, x.window_text() or title, re.I)]
        if not win32_wins:
            win32_wins = [x for x in Desktop(backend="win32").windows() if x.process_id() == pid]
        for native in win32_wins:
            controls = [native, *native.descendants()]
            classes = Counter((c.class_name() or "(없음)") for c in controls)
            lines.append("")
            lines.append(f"### Win32 창: {native.window_text()!r} class={native.class_name()!r} pid={pid}")
            lines.append("클래스 집계: " + ", ".join(f"{k}={v}" for k, v in classes.most_common()))
            embedded = [name for name in classes
                        if any(word.lower() in name.lower() for word in
                               ("Internet Explorer_Server", "Chrome_RenderWidgetHost", "WebView", "CefBrowser"))]
            lines.append("내장 웹 화면: " + (", ".join(embedded) if embedded else "발견 안 됨"))
            for c in controls[:3000]:
                try:
                    text = (c.window_text() or "").strip().replace("\r", " ").replace("\n", " ")
                    rect = c.rectangle()
                    lines.append(
                        f"{c.class_name()!r:34} text={text[:55]!r:59} "
                        f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom})"
                    )
                except Exception:  # noqa: BLE001 — 일부 네이티브 컨트롤은 조회 중 사라질 수 있다
                    continue
            print("Win32 클래스:", ", ".join(f"{k}={v}" for k, v in classes.most_common(12)))
            print("내장 웹 화면:", ", ".join(embedded) if embedded else "발견 안 됨")

    # Internet Explorer_Server가 있으면 MSHTML DOM을 직접 읽을 수 있는지 확인한다.
    try:
        from .ie_dom import describe

        doms = describe(pattern)
        lines.append("")
        lines.append(f"### MSHTML DOM 문서: {len(doms)}개")
        print(f"MSHTML DOM 문서: {len(doms)}개")
        for i, dom in enumerate(doms, start=1):
            lines.append(
                f"DOM {i}: title={dom.get('title', '')!r} url={dom.get('url', '')!r} "
                f"조작요소={len(dom.get('elements', []))} error={dom.get('error', '')!r}"
            )
            print(f"  DOM {i}: 조작요소 {len(dom.get('elements', []))}개  title={dom.get('title', '')!r}")
            for el in dom.get("elements", []):
                lines.append(
                    f"  [{el['index']}] {el['tag']}/{el['type']} id={el['id']!r} "
                    f"name={el['name']!r} text={el['text']!r}"
                )
    except Exception as exc:  # noqa: BLE001
        lines.append("")
        lines.append(f"### MSHTML DOM 접근 실패: {type(exc).__name__}: {exc}")
        print(f"MSHTML DOM 접근 실패: {type(exc).__name__}: {exc}")
    try:
        check = automation_check(out.with_suffix(".png"))
    except Exception as exc:  # noqa: BLE001 — 판정이 실패해도 아래 원본 목록은 남긴다
        check = ["### 자동화 판정 실패", f"{type(exc).__name__}: {exc}"]
    print("\n".join(check))
    out.write_text("\n".join(_mask(line) for line in [*check, "", *lines]), encoding="utf-8")
    print("자세한 목록:", out)
