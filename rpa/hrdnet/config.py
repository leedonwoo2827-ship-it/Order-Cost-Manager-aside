"""설정 — local.json(없으면 기본값으로 만든다).

★ 데이터는 data_root(D:\\00data_edu\\비용신청) 아래에만 쓴다. 02 허브가 같은 곳을 읽는다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "local.json"

DEFAULT = {
    "data_root": r"D:\00data_edu\비용신청",
    # 수동 다운로드를 감시할 폴더 — 여기 새로 생긴 엑셀·pdf 를 inbox 로 옮긴다
    "downloads": str(Path.home() / "Downloads"),
    # 수주및비용대시보드 주소 — 웹이면 Playwright 로 연다 (확인 후 채운다)
    "dashboard_url": "",
    # 지금 쓰는 자동화(매크로) — rpa/macros/<id>/ (대시보드에서 바꿀 수 있다)
    "macro": "hrd-wituk-claim-v1",
    # 단계 사이 쉬는 시간(초) — 설치 프로그램 화면이 늦게 그려질 때 늘린다
    "step_delay": 0.8,
    "image_confidence": 0.85,
    # HRD-Net 행정지원시스템 실행 파일(또는 바로가기 .lnk) — 담당자 PC 에서 채운다
    "hrdnet_exe": "",
    # 대시보드
    "port": 8820,
    "panel_width": 520,      # 오른쪽 사이드 패널 폭 — 나머지 왼쪽이 HRD-Net 창
    # 창 배치: auto(모니터 수로 판단) | single(한 화면에 3개) | dual(대시보드는 다른 모니터)
    "layout": "auto",
    "work_display": "",      # HRD-Net·패널을 둘 모니터 번호(0부터). 비우면 주 모니터
    "browser": "",           # 사이드 패널을 띄울 Chrome/Edge — 비우면 찾아서 쓴다
    "viewer_password": "",
}

# 비용신청대상 엑셀의 열 — 왼쪽은 코드에서 쓰는 이름, 오른쪽은 엑셀에 있을 수 있는 이름들
# ★ 가정값. 수주및비용대시보드 실물 엑셀을 받으면 맞춘다.
COLUMNS = {
    "과정명": ["과정명", "훈련과정명", "과정"],
    "회차": ["회차", "실시회차", "훈련회차"],
    "검색시작": ["시작일", "훈련시작일", "검색시작"],
    "검색종료": ["종료일", "훈련종료일", "검색종료"],
    "사업장명": ["사업장명", "참여업체", "참여업체명", "업체명"],
    "사업장관리번호": ["사업장관리번호", "관리번호"],
    "사업자번호": ["사업자번호", "사업자등록번호"],   # 관리번호가 없으면 사업자번호+0 으로 추정 (status.resolve_number)
    "훈련인원": ["훈련인원", "인원", "수료인원"],
    "신청금액": ["신청금액", "신청액", "청구금액"],
    "전자계산서": ["전자계산서", "계산서파일"],
    "수납확인서": ["수납확인서", "수납확인서파일"],
    # 대시보드가 같은 회차의 입금 미확인·부분입금·비용신청 완료 행에 붙인 이유 — 있으면 '불가'로만 보이고 돌리지 않는다
    "제외사유": ["제외사유"],
}
REQUIRED = ["과정명", "회차"]   # 사업장관리번호는 대시보드 엑셀에 없을 수 있어 필수에서 뺐다(없으면 사업장명으로 사람 안내)

# 증빙 파일 이름으로 종류를 알아보는 말
EVIDENCE = {"전자계산서": ["전자계산서", "계산서"], "수납확인서": ["수납확인서", "수납"]}


def load() -> dict:
    cfg = dict(DEFAULT)
    if LOCAL.exists():
        cfg.update(json.loads(LOCAL.read_text(encoding="utf-8")))
    else:
        LOCAL.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


def dirs(cfg: dict | None = None) -> dict[str, Path]:
    root = Path((cfg or load())["data_root"])
    d = {k: root / k for k in ("inbox", "outbox", "logs", "결과", "_archive")}
    d["증빙"] = d["inbox"] / "증빙"
    d["shots"] = d["logs"] / "shots"
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    d["root"] = root
    return d
