"""HRD-Net의 Internet Explorer_Server 내장 문서 접근 도구.

CyWindowClass 내부의 MSHTML DOM을 좌표 대신 직접 다루기 위한 브리지다.
진단에서는 입력값을 읽거나 기록하지 않고 요소의 구조만 확인한다.
"""
from __future__ import annotations

import re
from typing import Any


def _server_hwnds(parent_hwnd: int) -> list[int]:
    import win32gui

    found: list[int] = []

    def visit(hwnd: int, _extra: Any) -> bool:
        if win32gui.GetClassName(hwnd) == "Internet Explorer_Server":
            found.append(hwnd)
        return True

    win32gui.EnumChildWindows(parent_hwnd, visit, None)
    return found


def document_from_server(hwnd: int):
    """Internet Explorer_Server HWND에서 MSHTML document를 얻는다."""
    import pythoncom
    import win32api
    import win32con
    import win32gui
    import win32com.client

    message = win32api.RegisterWindowMessage("WM_HTML_GETOBJECT")
    result = win32gui.SendMessageTimeout(hwnd, message, 0, 0, win32con.SMTO_ABORTIFHUNG, 1500)
    lresult = result[1] if isinstance(result, tuple) else result
    if not lresult:
        raise RuntimeError("WM_HTML_GETOBJECT 응답 없음")
    dispatch = pythoncom.ObjectFromLresult(lresult, pythoncom.IID_IDispatch, 0)
    return win32com.client.Dispatch(dispatch)


def documents(window_pattern: str) -> list[tuple[int, Any]]:
    """제목 패턴과 일치하는 창 아래 접근 가능한 MSHTML 문서를 반환한다."""
    import win32gui

    rx = re.compile(window_pattern, re.I)
    roots: list[int] = []

    def visit(hwnd: int, _extra: Any) -> bool:
        if win32gui.IsWindowVisible(hwnd) and rx.search(win32gui.GetWindowText(hwnd) or ""):
            roots.append(hwnd)
        return True

    win32gui.EnumWindows(visit, None)
    found = []
    for root in roots:
        for server in _server_hwnds(root):
            try:
                found.append((server, document_from_server(server)))
            except Exception:  # noqa: BLE001 — 접근 불가 프레임은 건너뛴다
                continue
    return found


def describe(window_pattern: str) -> list[dict]:
    """민감한 입력값 없이 자동화에 필요한 DOM 구조만 요약한다."""
    result = []
    for hwnd, doc in documents(window_pattern):
        item: dict[str, Any] = {"hwnd": hwnd, "title": "", "url": "", "elements": []}
        try:
            item["title"] = str(doc.title or "")
        except Exception:  # noqa: BLE001
            pass
        try:
            item["url"] = str(doc.url or "").split("?", 1)[0]
        except Exception:  # noqa: BLE001
            pass
        try:
            elements = doc.all
            for index in range(min(int(elements.length), 10000)):
                el = elements.item(index)
                tag = str(getattr(el, "tagName", "") or "").upper()
                role = str(getattr(el, "type", "") or "").lower()
                if tag not in ("INPUT", "BUTTON", "SELECT", "A", "TEXTAREA"):
                    continue
                text = str(getattr(el, "innerText", "") or getattr(el, "title", "") or "").strip()
                item["elements"].append({
                    "index": index,
                    "tag": tag,
                    "type": role,
                    "id": str(getattr(el, "id", "") or ""),
                    "name": str(getattr(el, "name", "") or ""),
                    "text": text[:100],
                })
        except Exception as exc:  # noqa: BLE001
            item["error"] = f"{type(exc).__name__}: {exc}"
        result.append(item)
    return result

