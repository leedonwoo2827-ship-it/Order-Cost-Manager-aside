"""HRD-Net 화면 진단 — 담당자 PC 에서 로그인한 뒤 한 번 돌린다.

UIA 로 버튼·칸의 이름이 보이면 steps.yaml 에 uia target 을 채우고(빠르고 튼튼함),
안 보이면 버튼 이미지를 templates/ 에 넣어 image target 을 쓴다.
결과: logs/inspect_<시각>.txt  (개인정보가 화면에 있으면 이 파일에도 들어가므로 PC 밖으로 보내지 않는다)
"""
from __future__ import annotations

from datetime import datetime

from . import config

KEY_BUTTONS = ["검색", "신청", "비용등록", "저장", "닫기", "고용보험확인", "훈련비용 신청", "첨부", "산출액"]


def run() -> None:
    try:
        from pywinauto import Desktop
    except ImportError:
        print("pywinauto 가 없습니다 — setup.bat 을 먼저 실행하세요")
        return
    d = config.dirs()
    out = d["logs"] / f"inspect_{datetime.now():%Y%m%d_%H%M%S}.txt"
    lines = []
    wins = [w for w in Desktop(backend="uia").windows() if "HRD" in (w.window_text() or "").upper()]
    if not wins:
        print("제목에 HRD 가 들어간 창이 없습니다. HRD-Net 에 로그인한 뒤 다시 실행하세요.")
        print("지금 열린 창:", [w.window_text() for w in Desktop(backend="uia").windows() if w.window_text()][:20])
        return
    for w in wins:
        title = w.window_text()
        lines.append(f"### 창: {title!r}  class={w.class_name()!r}  pid={w.process_id()}")
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
    out.write_text("\n".join(lines), encoding="utf-8")
    print("자세한 목록:", out)
