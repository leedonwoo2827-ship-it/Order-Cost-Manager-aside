"""4 결과 — logs/*.summary.json → 결과/결과_YYYYMMDD.xlsx + 완료처리대상_YYYYMMDD.csv

결과표 시트 (v2.2.8)
  업체   업체 1곳 = 1줄. 저장완료 / 불가 / 중단 · 멈춘 단계 · 이유 — 오늘 실행한 업체(status companies.json 기준)
  결과   실행 1번 = 1줄 (업체별 실행이면 업체마다 한 줄)
  집계   상태별 개수
올리기(upload-all)가 끝나면 자동으로 만든다. [4 결과표]로 다시 만들어도 된다.

수주대시보드 완료처리는 자동으로 하지 않는다. 성공건 목록을 만들어 사람이 반영한다(대시보드는 건드리지 않음).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime

from . import config, status

COLS = ["과정명", "회차", "업체", "모드", "상태", "시작", "끝", "단계수", "완료", "자동", "사람", "신청금액", "오류"]
COMPANY_COLS = ["과정명", "회차", "업체", "사업장관리번호", "신청금액", "상태", "결과", "멈춘·마지막 단계", "단계 설명",
                "이유", "실행 시작", "끝·저장 시각", "모드"]


def _company_rows(day: str, runs: list[dict]) -> list[list]:
    """오늘 돌린 업체 — 상태(저장완료·불가·신청가능)와 마지막 실행 결과(f08)·멈춘 단계(f06)·이유."""
    stamp = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    out = []
    for key, rec in status.load().items():
        if not str(rec.get("f04", "")).startswith(stamp):
            continue
        course, rnd, no = (key.split("|") + ["", "", ""])[:3]
        company = rec.get("업체", "")
        out.append([course, rnd, company, rec.get("관리번호") or ("" if no.startswith("#") else no), "",
                    rec.get("상태", ""), rec.get("f08", ""), rec.get("f06", ""), rec.get("f07", ""),
                    rec.get("f09") or rec.get("사유", ""), rec.get("f04", ""), rec.get("f05", ""), rec.get("f03", "")])
    # 업체명은 실행 기록에서 (status 키에는 관리번호만 있을 수 있다)
    by_run = {}
    for r in runs:
        names = r.get("업체") or []
        if len(names) == 1:
            by_run[(r.get("과정명"), str(r.get("회차")), r.get("시작", ""))] = (names[0], r.get("신청금액", ""))
    for row in out:
        hit = by_run.get((row[0], row[1], row[10]))
        if hit:
            row[2] = row[2] or hit[0]
            row[4] = hit[1]
    out.sort(key=lambda r: (r[0], str(r[1]).zfill(4), r[10]))
    return out


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
        ws.append([", ".join(r.get(c) or []) if c == "업체" else r.get(c, "") for c in COLS] + [r["못찾음"]])
    wc = wb.create_sheet("업체", 0)       # 맨 앞 — 업체마다 저장됐는지, 어디서 왜 멈췄는지
    wc.append(COMPANY_COLS)
    for row in _company_rows(day, rows):
        wc.append(row)
    for col, width in zip("ABCDEFGHIJKLM", (34, 6, 22, 14, 11, 9, 9, 10, 40, 60, 19, 19, 8)):
        wc.column_dimensions[col].width = width
    ws2 = wb.create_sheet("집계")
    for st in ("성공", "저장완료", "신청불가", "채움완료", "실패", "오류", "중단", "점검완료", "모의완료"):
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
