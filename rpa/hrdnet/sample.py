"""가짜 샘플 — inbox 에 비용신청대상 엑셀과 빈 증빙 pdf 를 만든다. 실제 개인정보·업체 정보 없음."""
from __future__ import annotations

from . import config

ROWS = [
    # 과정명, 회차, 시작일, 종료일, 사업장명, 사업장관리번호, 훈련인원, 신청금액
    ("아카이브", 21, "2026-03-01", "2026-12-31", "가나다상사(샘플)", "10000000001", 78, 9828000),
    ("아카이브", 22, "2026-03-01", "2026-12-31", "라마바산업(샘플)", "10000000002", 12, 1512000),
    ("아카이브", 22, "2026-03-01", "2026-12-31", "사아자물류(샘플)", "10000000003", 5, 630000),
    ("리더십기초", 7, "2026-09-01", "2026-10-31", "차카타전자(샘플)", "10000000004", 30, 2100000),
]

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def run() -> None:
    from openpyxl import Workbook
    d = config.dirs()
    wb = Workbook()
    ws = wb.active
    ws.append(["과정명", "회차", "시작일", "종료일", "사업장명", "사업장관리번호", "훈련인원", "신청금액"])
    for r in ROWS:
        ws.append(list(r))
    x = d["inbox"] / "비용신청대상_샘플.xlsx"
    wb.save(x)
    # 21회차: 계산서+수납 / 22회차: 계산서만 / 리더십기초 7회차: 증빙 없음(누락 리포트 확인용)
    for rel in ["아카이브/21회차/전자계산서_sample.pdf", "아카이브/21회차/수납확인서_sample.pdf",
                "아카이브_22회차_전자계산서.pdf"]:
        p = d["증빙"] / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(PDF)
    print("샘플을 만들었습니다:", x, "+ 증빙 3개")
