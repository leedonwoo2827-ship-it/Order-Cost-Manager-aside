"""사람이 수행한 HRD-Net 클릭을 단계별로 학습 자료로 저장한다.

키보드 입력은 기록하지 않는다. 현재 HRD-Net 주 창 안에서 발생한 왼쪽 클릭만
창 크기 대비 상대 좌표와 버튼 주변 이미지로 저장한다.
"""
from __future__ import annotations

import ctypes
import json
import re
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from . import config, macros

VK_LBUTTON = 0x01


def _base_step(step_id: str) -> str:
    return re.sub(r"#\d+$", "", step_id)


class StepRecorder:
    def __init__(self, hwnd: int, step_id: str, description: str):
        self.hwnd = int(hwnd or 0)
        self.step_id = _base_step(step_id)
        self.description = description
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pressed = False
        self.macro_dir = macros.path()
        self.templates = self.macro_dir / "templates" / "learned"
        self.templates.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if not self.hwnd or not ctypes.windll.user32.IsWindow(self.hwnd):
            return
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self, save: bool) -> int:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        if save and self.events:
            self._save()
        return len(self.events)

    def _rect(self) -> tuple[int, int, int, int] | None:
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return None
        return rect.left, rect.top, rect.right, rect.bottom

    def _watch(self) -> None:
        user32 = ctypes.windll.user32
        while not self._stop.is_set():
            down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if down and not self._pressed:
                point = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                rect = self._rect()
                if rect:
                    left, top, right, bottom = rect
                    if left <= point.x < right and top <= point.y < bottom and len(self.events) < 20:
                        self._record(point.x, point.y, rect)
            self._pressed = down
            time.sleep(0.025)

    def _record(self, x: int, y: int, rect: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = rect
        width, height = max(1, right - left), max(1, bottom - top)
        index = len(self.events) + 1
        safe_step = re.sub(r"[^0-9A-Za-z가-힣_-]", "_", self.step_id)
        template = self.templates / f"{safe_step}_{index}.png"
        try:
            image = ImageGrab.grab(bbox=rect, all_screens=True)
            rel_x, rel_y = x - left, y - top
            x1, y1 = max(0, rel_x - 70), max(0, rel_y - 28)
            x2, y2 = min(width, rel_x + 70), min(height, rel_y + 28)
            image.crop((x1, y1, x2, y2)).save(template)
            template_path = str(template.relative_to(self.macro_dir)).replace("\\", "/")
        except Exception:  # noqa: BLE001 — 좌표 기록은 유지한다
            template_path = ""
        self.events.append({
            "x_ratio": round((x - left) / width, 6),
            "y_ratio": round((y - top) / height, 6),
            "window_width": width,
            "window_height": height,
            "template": template_path,
        })

    def _save(self) -> None:
        path = self.macro_dir / "learned_actions.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            data = {}
        data[self.step_id] = {
            "description": self.description,
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": self.events,
            "reviewed": False,
        }
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

