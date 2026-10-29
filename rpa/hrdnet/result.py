"""4 결과 — logs/*.summary.json → 결과/결과_YYYYMMDD.xlsx + 완료처리대상_YYYYMMDD.csv

수주대시보드 완료처리는 자동으로 하지 않는다. 성공건 목록을 만들어 사람이 반영한다(대시보드는 건드리지 않음).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime

from . import config

COLS = ["과정명", "회차", "모드", "상태", "시작", "끝", "단계수", "완료", "자동", "사람", "신청금액", "오류"]


def run(day: str = "") -> None:
    d = config.dirs()
    day = day or datetime.now().strftime("%Y%m%d")
    rows = []
    for p in sorted(d["logs"].glob(f"{day}_*.summary.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        s["못찾음"] = len(s.get("못찾음", []))
        rows.append(s)
    if not rows:
        print(f"{day} 기록이 없습니다 ({d['logs']})")
        return
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "결과"
    ws.append(COLS + ["못찾음"])
    for r in rows:
        ws.append([r.get(c, "") for c in COLS] + [r["못찾음"]])
    ws2 = wb.create_sheet("집계")
    for st in ("성공", "실패", "오류", "중단", "점검완료", "모의완료"):
        ws2.append([st, sum(1 for r in rows if r["상태"] == st)])
    xlsx = d["결과"] / f"결과_{day}.xlsx"
    wb.save(xlsx)

    ok = [r for r in rows if r["상태"] == "성공"]
    done = d["결과"] / f"완료처리대상_{day}.csv"
    with open(done, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        # 업체 단위 — 대시보드 [완료 반영]이 이 업체 행만 체크한다. 사업장명이 빈 줄(예전 기록)은 회차 전체로 반영된다
        w.writerow(["과정명", "회차", "신청금액", "신청일시", "사업장명"])
        for r in ok:
            for company in r.get("신청업체") or [""]:
                w.writerow([r["과정명"], r["회차"], r.get("신청금액", ""), r.get("끝", ""), company])
    by = {}
    for r in rows:
        by[r["상태"]] = by.get(r["상태"], 0) + 1
    print("결과:", ", ".join(f"{k} {v}" for k, v in by.items()))
    print("  ", xlsx)
    print("  ", done, f"(완료처리 대상 {len(ok)}건)")
