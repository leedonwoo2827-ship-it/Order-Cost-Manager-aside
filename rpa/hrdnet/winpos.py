"""창 배치 — 왼쪽 HRD-Net 설치 프로그램, 오른쪽 좁은 사이드 패널(브라우저 앱 창). 롱폼 공방의 place() 와 같은 그림.

HRD-Net 은 설치 프로그램이라 CDP 로 붙을 수 없다. 창 제목으로 찾아 Win32 MoveWindow 로 옮긴다.
모니터 판단(듀얼/단일)은 대시보드(Electron)가 하고, 자리(물리 화소)를 /api/layout 으로 넘긴다 → logs/_layout.json.
자리를 받은 적이 없으면 예전처럼 주 모니터 작업 영역에서 왼쪽 HRD-Net · 오른쪽 패널.
패널은 하나만 — 이미 떠 있으면 새로 띄우지 않고 앞으로 가져와 자리만 맞춘다.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from . import config, macros

PANEL_TITLE = r"(비용신청 · 패널|답해 주세요 · 비용신청)"   # panel.html 의 <title> (질문이 있으면 바뀐다)

user32 = ctypes.windll.user32 if sys.platform.startswith("win") else None


def screen() -> tuple[int, int]:
    """작업 표시줄을 뺀 작업 영역 (가로, 세로)."""
    try:
        _dpi_aware()
        r = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
        return r.right - r.left, r.bottom - r.top
    except Exception:  # noqa: BLE001
        return 1920, 1040


def windows(pattern: str) -> list[tuple[int, str]]:
    out = []
    rx = re.compile(pattern, re.I)
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if rx.search(buf.value):
                    out.append((hwnd, buf.value))
        return True

    user32.EnumWindows(proto(cb), 0)
    return out


def _layout_file() -> Path:
    return config.dirs()["logs"] / "_layout.json"


def saved_layout() -> dict:
    """대시보드가 정해 준 자리 → 없으면 주 모니터 기본(왼쪽 HRD-Net, 오른쪽 패널)."""
    import json
    try:
        lay = json.loads(_layout_file().read_text(encoding="utf-8"))
        if lay.get("hrdnet") and lay.get("panel"):
            return lay
    except (OSError, ValueError):
        pass
    w, h = screen()
    pw = int(config.load()["panel_width"])
    return {"hrdnet": {"x": 0, "y": 0, "width": w - pw, "height": h},
            "panel": {"x": w - pw, "y": 0, "width": pw, "height": h}, "scale": 1.0}


def _dpi_aware() -> None:
    """좌표를 모니터마다 실제 화소로 다룬다(모니터별 배율 인식). 배율이 다른 모니터가 섞여도
    (예: 세로 주모니터 100% + 가로 보조 150%) 창이 엉뚱한 자리·크기로 가지 않게."""
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # PER_MONITOR_AWARE_V2
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)                 # PER_MONITOR_AWARE
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        user32.SetProcessDPIAware()  # 마지막 수단(시스템 배율만)
    except Exception:  # noqa: BLE001
        pass


def _move(hwnd: int, r: dict) -> None:
    """두 번 옮긴다 — 배율이 다른 모니터로 넘어가면 창(Chrome 등)이 배율에 맞춰 스스로 크기를 바꿔
    자리가 밀리기 때문에, 넘어간 뒤 한 번 더 정확히 맞춘다."""
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE (최대화 풀기)
    for _ in range(2):
        user32.MoveWindow(hwnd, int(r["x"]), int(r["y"]), int(r["width"]), int(r["height"]), True)
        time.sleep(0.15)


def place_left(pattern: str) -> bool:
    """HRD-Net 창을 정해진 자리(기본: 화면 왼쪽, 패널 자리를 뺀 나머지)로."""
    _dpi_aware()
    r = saved_layout()["hrdnet"]
    hits = windows(pattern)
    for hwnd, _t in hits:
        _move(hwnd, r)
    return bool(hits)


def keep_place(pattern: str) -> bool:
    """실행 중 HRD-Net 창이 최대화되거나 자리를 벗어났으면 정해진 자리로 되돌린다 → 되돌렸는지.
    (창 크기가 바뀌면 버튼 이미지·학습 좌표가 어긋나서 단계마다 확인한다)"""
    _dpi_aware()
    r = saved_layout()["hrdnet"]
    fixed = False
    for hwnd, _t in windows(pattern):
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        off = (abs(rect.left - int(r["x"])) > 8 or abs(rect.top - int(r["y"])) > 8
               or abs((rect.right - rect.left) - int(r["width"])) > 16
               or abs((rect.bottom - rect.top) - int(r["height"])) > 16)
        if user32.IsZoomed(hwnd) or off:
            _move(hwnd, r)
            fixed = True
    return fixed


def arrange(hrdnet: dict, panel: dict, scale: float, port: int) -> dict:
    """대시보드가 정한 자리로 HRD-Net·패널을 옮긴다(패널이 없으면 연다). 자리는 다음에도 쓰게 저장."""
    import json
    _layout_file().write_text(json.dumps({"hrdnet": hrdnet, "panel": panel, "scale": scale}), encoding="utf-8")
    moved = place_left(macros.window_pattern())
    return {"hrdnet": moved, "panel": open_panel(port)}


def browser() -> str:
    cfg = config.load()
    cands = [cfg.get("browser") or "",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    for c in cands:
        if c and Path(c).exists():
            return c
    return ""


_panel_lock = __import__("threading").Lock()


def _bring_front(hwnd: int) -> None:
    """패널을 맨 앞으로. 윈도우는 뒤에서 도는 프로그램이 창을 앞으로 가져오는 것을 막아서
    (작업 표시줄만 깜빡이고 뒤에 숨는다) Alt 키를 한 번 눌렀다 떼어 허락을 받은 뒤 올린다."""
    user32.keybd_event(0x12, 0, 0, 0)        # Alt 누름
    user32.keybd_event(0x12, 0, 0x0002, 0)   # Alt 뗌
    user32.ShowWindow(hwnd, 9)               # SW_RESTORE
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_TOP, 크기·자리 그대로, 보이기
    user32.SetForegroundWindow(hwnd)


def open_panel(port: int) -> bool:
    """정해진 자리에 좁은 패널(앱 창). 전용 프로필이라 평소 브라우저와 섞이지 않는다.
    이미 떠 있으면 새로 띄우지 않는다 — 여러 버튼이 동시에 불러도 하나만(잠금)."""
    with _panel_lock:
        _dpi_aware()
        r = saved_layout()["panel"]
        found = windows(PANEL_TITLE)
        if found:
            for hwnd, _t in found[1:]:        # 예전에 여러 개 떠 버린 것은 닫는다
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            _move(found[0][0], r)
            _bring_front(found[0][0])
            return True
        exe = browser()
        if not exe:
            return False
        # Chrome 창 옵션은 배율(예: 150%)을 나눈 값이라 대충 맞춰 띄우고, 뜬 뒤 제목으로 찾아 정확히 옮긴다
        try:
            k = max(1.0, user32.GetDpiForSystem() / 96)
        except Exception:  # noqa: BLE001
            k = 1.0
        prof = config.dirs()["root"] / "_panel_profile"
        subprocess.Popen([exe, f"--app=http://localhost:{port}/panel", f"--user-data-dir={prof}",
                          "--no-first-run", "--no-default-browser-check",
                          f"--window-size={int(r['width'] / k)},{int(r['height'] / k)}",
                          f"--window-position={int(r['x'] / k)},{int(r['y'] / k)}"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(40):
            time.sleep(0.25)
            found = windows(PANEL_TITLE)
            if found:
                _move(found[0][0], r)
                time.sleep(0.8)              # 막 뜬 Chrome 이 배율에 맞춰 크기를 고친 뒤 한 번 더 맞춘다
                _move(found[0][0], r)
                _bring_front(found[0][0])
                break
        return True


def open_hrdnet() -> None:
    """HRD-Net 이 떠 있으면 왼쪽으로 옮기고, 없으면 실행한다. 로그인(인증서)은 사람이 한다."""
    pattern = macros.window_pattern()
    if place_left(pattern):
        print("HRD-Net 창을 왼쪽으로 옮겼습니다. 로그인이 되어 있는지 확인하세요.", flush=True)
        return
    exe = config.load().get("hrdnet_exe")
    if not exe or not Path(exe).exists():
        print("HRD-Net 창이 없습니다. 직접 실행하거나, [설정]에 HRD-Net 실행 파일(바로가기) 경로를 넣어 주세요.", flush=True)
        return
    os.startfile(exe)  # noqa: S606 — 사람이 설정한 바로가기
    print("HRD-Net 을 실행했습니다 — 로그인(인증서)을 해 주세요. 창이 뜨면 왼쪽으로 옮깁니다.", flush=True)
    for _ in range(90):
        time.sleep(2)
        if place_left(pattern):
            print("HRD-Net 창을 왼쪽으로 옮겼습니다.", flush=True)
            return
    print("HRD-Net 창을 찾지 못했습니다 — 창 제목이 steps.yaml 의 window 와 맞는지 [화면 진단]으로 확인하세요.", flush=True)
