"""1 받기 — 내부 시스템 자료를 inbox 로 가져온다. 내부 시스템은 읽기(내려받기)만 한다.

watch   : 다운로드 폴더를 감시하다가 새로 생긴 엑셀·pdf 를 inbox 로 옮긴다 (기본, 설치할 것 없음)
browser : Playwright 로 수주및비용대시보드를 연다. 로그인·조회는 사람이 하고 내려받기만 잡는다
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import config

EXTS = {".xlsx", ".xls", ".csv", ".pdf"}


def _place(src: Path, d: dict) -> Path:
    """엑셀은 inbox, 증빙 pdf 는 inbox/증빙 으로. 이름이 겹치면 뒤에 번호를 붙인다."""
    to_dir = d["증빙"] if src.suffix.lower() == ".pdf" else d["inbox"]
    dst = to_dir / src.name
    n = 1
    while dst.exists():
        dst = to_dir / f"{src.stem}_{n}{src.suffix}"
        n += 1
    shutil.move(str(src), dst)
    return dst


def watch(minutes: float = 30) -> None:
    cfg = config.load()
    d = config.dirs(cfg)
    dl = Path(cfg["downloads"])
    start = time.time()
    seen = {p for p in dl.iterdir() if p.is_file()}
    print(f"다운로드 폴더 감시: {dl} → {d['inbox']}  ({minutes:g}분, 멈추려면 Ctrl+C)")
    try:
        while time.time() - start < minutes * 60:
            for p in dl.iterdir():
                if p in seen or not p.is_file() or p.suffix.lower() not in EXTS:
                    continue
                if p.stat().st_mtime < start:
                    seen.add(p)
                    continue
                time.sleep(1)  # 내려받기가 끝날 때까지 잠깐 기다린다
                seen.add(p)
                print("  받음:", _place(p, d).relative_to(d["root"]))
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    print("감시 끝")


def browser() -> None:
    cfg = config.load()
    d = config.dirs(cfg)
    if not cfg.get("dashboard_url"):
        print("local.json 의 dashboard_url 이 비어 있습니다. 수주및비용대시보드 주소를 넣어 주세요.")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 가 없습니다:  .venv\\Scripts\\pip install playwright  후  playwright install chromium")
        return
    profile = d["root"] / "_browser"  # 로그인 쿠키는 이 PC 의 이 폴더에만 남는다
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(profile), headless=False, accept_downloads=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(cfg["dashboard_url"])
        print("브라우저에서 로그인하고 비용신청 대상을 조회한 뒤 [엑셀 다운로드]를 누르세요.")
        print("받은 파일은 inbox 로 옮깁니다. 다 받았으면 브라우저 창을 닫으세요.")

        def on_download(dl):
            tmp = d["inbox"] / dl.suggested_filename
            dl.save_as(tmp)
            print("  받음:", tmp.name)

        ctx.on("page", lambda p: p.on("download", on_download))
        page.on("download", on_download)
        try:
            while ctx.pages:
                time.sleep(1)
        except Exception:  # noqa: BLE001 — 창을 닫으면 여기로 온다
            pass
