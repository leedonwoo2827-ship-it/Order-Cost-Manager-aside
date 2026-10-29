"""화면 글자 읽기 — Windows 내장 OCR(Windows.Media.Ocr, 한국어).

HRD-Net 행정지원시스템은 화면을 직접 그리는 프로그램이라(CyWindowClass) UIA·웹 구조(DOM)로는 글자가 하나도 안 보인다
(2026-10-29 화면 진단: UIA 요소 0개, 본 화면 DOM 없음). 그래서 칸·버튼 위치는 그림(템플릿)으로 찾고,
회차처럼 '어느 것인지' 확인해야 하는 곳은 화면을 캡처해 OCR 로 읽는다. 추가 설치 없이 윈도우 기능만 쓴다.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("ocr.ps1")
SCALE = 2          # 작은 글씨는 키워서 읽어야 잘 읽힌다


def words(image, scale: int = SCALE) -> list[dict]:
    """PIL 이미지 → [{'t': 글자, 'x','y','w','h'}] (원래 이미지 좌표). 읽지 못하면 []."""
    img = image.convert("RGB")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale))
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ocr.png"
        img.save(p)
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), str(p)],
                capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            return []
    found = []
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        try:
            w = json.loads(line)
        except json.JSONDecodeError:
            continue
        found.append({"t": str(w["t"]), "x": w["x"] / scale, "y": w["y"] / scale,
                      "w": w["w"] / scale, "h": w["h"] / scale})
    return found


# HRD-Net 숫자는 안티앨리어싱 없는 5×9 점 글꼴이라 점 모양을 그대로 맞춰 읽는다 (10/29 담당자 PC 화면에서 뽑음).
# 윈도우 OCR 은 이 글꼴의 9 를 3 으로 읽는다(10/29 진단: 회차 칸·목록 모두 19 → '13') — 그래서 숫자는 이 표가 먼저다.
GLYPHS = {
    "0": ".###.|#...#|#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "1": ".#|##|.#|.#|.#|.#|.#|.#|.#",
    "2": ".###.|#...#|#...#|....#|...#.|..#..|.#...|#....|#####",
    "3": ".###.|#...#|....#|....#|.###.|....#|....#|#...#|.###.",
    "4": "..##.|..##.|.#.#.|.#.#.|#..#.|#..#.|#####|...#.|...#.",
    "5": "#####|#....|#....|####.|#...#|....#|....#|#...#|.###.",
    "6": ".###.|#...#|#....|#....|####.|#...#|#...#|#...#|.###.",
    "7": "#####|....#|...#.|...#.|...#.|..#..|..#..|..#..|..#..",
    "8": ".###.|#...#|#...#|#...#|.###.|#...#|#...#|#...#|.###.",
    "9": ".###.|#...#|#...#|#...#|.####|....#|....#|#...#|.###.",
}
_BY_SHAPE = {v: k for k, v in GLYPHS.items()}
DARK = 110        # 글자(검정·짙은 회색)만 남긴다 — 표 줄(회색)·선택 행 배경은 이보다 밝다


def read_digits(image) -> str:
    """5×9 점 글꼴 숫자 칸 → 숫자 글자. 모르는 모양이 하나라도 있으면 ''(못 읽음 — 틀린 값보다 안전)."""
    import numpy as np

    dark = np.array(image.convert("L")) < DARK
    cols = dark.any(axis=0)
    out, x = "", 0
    while x < len(cols):
        if not cols[x]:
            x += 1
            continue
        end = x
        while end < len(cols) and cols[end]:
            end += 1
        g = dark[:, x:end]
        rows = np.where(g.any(axis=1))[0]
        g = g[rows.min():rows.max() + 1]
        digit = _BY_SHAPE.get("|".join("".join("#" if v else "." for v in r) for r in g))
        if digit is None:
            return ""
        out += digit
        x = end
    return out


def read_numbers(images: list, scale: int = 6) -> list[str]:
    """작은 칸 이미지들(회차 칸 등)의 숫자 → 칸마다 글자('' = 못 읽음).
    점 글꼴 표(GLYPHS)로 먼저 읽고, 그걸로 못 읽은 칸만 윈도우 OCR 로 읽는다."""
    out = [read_digits(im) for im in images]
    rest = [i for i, v in enumerate(out) if not v]
    if rest:
        texts = read_texts([images[i] for i in rest], scale, binarize=True)
        for i, t in zip(rest, texts):
            out[i] = "".join(ch for ch in t if ch.isdigit())
    return out


def read_texts(images: list, scale: int = 3, binarize: bool = False) -> list[str]:
    """작은 칸 이미지들 → 칸마다 읽은 글자(공백 없이). OCR 은 한 번만 부른다.
    칸들을 크게 키운 뒤 세로로 띄워 붙여 읽고, 읽힌 위치로 어느 칸인지 되돌린다."""
    from PIL import Image, ImageOps

    if not images:
        return []
    gap = 40
    parts = []
    for im in images:
        g = ImageOps.grayscale(im)
        if binarize:
            g = g.point(lambda v: 0 if v < 150 else 255)
        parts.append(g.resize((g.width * scale, g.height * scale), Image.LANCZOS))
    width = max(p.width for p in parts) + gap * 2
    height = sum(p.height + gap for p in parts) + gap
    sheet = Image.new("L", (width, height), 255)
    spans, y = [], gap
    for p in parts:
        sheet.paste(p, (gap, y))
        spans.append((y, y + p.height))
        y += p.height + gap
    out = [""] * len(images)
    for w in words(sheet, 1):
        text = w["t"].replace(" ", "")
        cy = w["y"] + w["h"] / 2
        for i, (top, bottom) in enumerate(spans):
            if top - gap / 2 <= cy <= bottom + gap / 2 and text:
                out[i] += text
                break
    return out


def rect(w: dict) -> tuple[float, float, float, float]:
    return w["x"], w["y"], w["x"] + w["w"], w["y"] + w["h"]


def round_rows(found: list[dict]) -> tuple[list, list, tuple | None]:
    """OCR 글자 → (「실시회차」 열의 숫자 칸 [(글자, rect)], [신청] 버튼 [rect], 머리글 rect).
    머리글은 두 줄(실시 / 회차)로 읽히거나 한 단어(실시회차)로 읽힌다."""
    header = None
    for w in found:
        if w["t"].replace(" ", "") in ("실시회차", "실시"):
            header = rect(w)
            break
    if header is None:
        return [], [rect(w) for w in found if w["t"] == "신청"], None
    l, _t, r, _b = header
    pad = max(6.0, (r - l) * 0.4)
    cells = [(w["t"], rect(w)) for w in found
             if w["t"].isdigit() and l - pad <= w["x"] + w["w"] / 2 <= r + pad and w["y"] > header[3]]
    buttons = [rect(w) for w in found if w["t"] == "신청"]
    return cells, buttons, header
