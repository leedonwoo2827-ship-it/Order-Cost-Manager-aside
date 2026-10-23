"""창 배치 — 왼쪽 HRD-Net 설치 프로그램, 오른쪽 좁은 사이드 패널(브라우저 앱 창). 롱폼 공방의 place() 와 같은 그림.

HRD-Net 은 설치 프로그램이라 CDP 로 붙을 수 없다. 창 제목으로 찾아 Win32 MoveWindow 로 옮긴다.
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

from . import config

user32 = ctypes.windll.user32 if sys.platform.startswith("win") else None


def screen() -> tuple[int, int]:
    """작업 표시줄을 뺀 작업 영역 (가로, 세로)."""
    try:
        user32.SetProcessDPIAware()
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


def place_left(pattern: str) -> bool:
    """HRD-Net 창을 화면 왼쪽(패널 자리를 뺀 나머지)으로."""
    w, h = screen()
    pw = int(config.load()["panel_width"])
    hits = windows(pattern)
    for hwnd, _t in hits:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE (최대화 풀기)
        user32.MoveWindow(hwnd, 0, 0, w - pw, h, True)
    return bool(hits)


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


def open_panel(port: int) -> bool:
    """오른쪽 끝에 좁은 패널(앱 창). 전용 프로필이라 평소 브라우저와 섞이지 않는다."""
    exe = browser()
    if not exe:
        return False
    w, h = screen()
    pw = int(config.load()["panel_width"])
    # screen()은 실제 화소, Chrome 창 옵션은 배율(예: 150%)을 나눈 값이라 맞춰 준다. 안 그러면 화면 밖에 뜬다.
    try:
        k = max(1.0, user32.GetDpiForSystem() / 96)
    except Exception:  # noqa: BLE001
        k = 1.0
    prof = config.dirs()["root"] / "_panel_profile"
    subprocess.Popen([exe, f"--app=http://127.0.0.1:{port}/panel", f"--user-data-dir={prof}",
                      "--no-first-run", "--no-default-browser-check",
                      f"--window-size={int(pw / k)},{int(h / k)}", f"--window-position={int((w - pw) / k)},0"],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True


def open_hrdnet() -> None:
    """HRD-Net 이 떠 있으면 왼쪽으로 옮기고, 없으면 실행한다. 로그인(인증서)은 사람이 한다."""
    import yaml
    spec = yaml.safe_load((config.ROOT / config.load()["steps"]).read_text(encoding="utf-8"))
    pattern = spec.get("window", ".*HRD.*")
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
