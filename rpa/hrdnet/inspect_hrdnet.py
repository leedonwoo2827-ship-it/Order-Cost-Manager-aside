"""HRD-Net 화면 진단 — 담당자 PC 에서 로그인한 뒤 한 번 돌린다.

UIA 로 버튼·칸의 이름이 보이면 steps.yaml 에 uia target 을 채우고(빠르고 튼튼함),
안 보이면 버튼 이미지를 templates/ 에 넣어 image target 을 쓴다.
결과: logs/inspect_<시각>.txt  (개인정보가 화면에 있으면 이 파일에도 들어가므로 PC 밖으로 보내지 않는다)
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from . import config

KEY_BUTTONS = ["검색", "신청", "비용등록", "저장", "닫기", "고용보험확인", "훈련비용 신청", "첨부", "산출액"]


def run() -> None:
    try:
        from pywinauto import Desktop
    except ImportError:
        print("pywinauto 가 없습니다 — setup.bat 을 먼저 실행하세요")
        return
    import yaml

    d = config.dirs()
    out = d["logs"] / f"inspect_{datetime.now():%Y%m%d_%H%M%S}.txt"
    lines = []
    spec = yaml.safe_load((config.ROOT / config.load()["steps"]).read_text(encoding="utf-8")) or {}
    pattern = spec.get("window", ".*(?:HRD|Edubion).*")
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
    out.write_text("\n".join(lines), encoding="utf-8")
    print("자세한 목록:", out)
