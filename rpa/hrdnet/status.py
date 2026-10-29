"""업체(사업장) 단위 상태 — <data_root>/status/companies.json.

manifest 와 따로 둔다. [정리]를 다시 해도 사람이 고른 상태·사유·실행 기록이 지워지지 않게.

키      과정명|회차|사업장관리번호  (관리번호가 없으면 과정명|회차|#정규화한 업체명)
상태    신청가능 | 신청완료 | 불가     ← 대시보드 콤보. 신청가능인 업체만 체크해서 돌릴 수 있다
사유    사람이 적거나 엔진이 남긴 이유 (예: 수납 미납 → 다음 신청)
f01~f30 여분 필드 — 어떤 자동화(매크로)로 어디까지 갔는지. 슬롯 뜻은 SLOTS.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from . import config

STATES = ("신청가능", "신청완료", "불가")
SLOTS = {
    "f01": "매크로 ID", "f02": "매크로 이름", "f03": "모드", "f04": "실행 시작", "f05": "실행 끝",
    "f06": "마지막 단계", "f07": "마지막 단계 설명", "f08": "결과", "f09": "오류 요약",
    "f10": "금액 확인(산출=신청=대시보드)", "f11": "업체명 확인", "f12": "등록인원",
}
STEP_SLOTS = [f"f{i:02d}" for i in range(13, 31)]   # f13~f30 = 단계 기록 "단계:결과"
for _s in STEP_SLOTS:
    SLOTS[_s] = "단계 기록"
FIELDS = [f"f{i:02d}" for i in range(1, 31)]

_lock = threading.Lock()


def company_key(value: str) -> str:
    from .organize import _company_key
    return _company_key(value)


def key(course: str, rnd: str, business: dict) -> str:
    no = str(business.get("사업장관리번호", "") or "").strip()
    return f"{course}|{rnd}|{no or '#' + company_key(business.get('사업장명', ''))}"


def _file() -> Path:
    p = config.dirs()["root"] / "status"
    p.mkdir(parents=True, exist_ok=True)
    return p / "companies.json"


def load() -> dict[str, dict]:
    f = _file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    f = _file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _blank() -> dict:
    return {"상태": "", "사유": "", "자동사유": "", "수정": "", **{k: "" for k in FIELDS}}


# ── 사업장관리번호 ────────────────────────────────────────────────────
# 대시보드에는 관리번호가 없고 사업자번호만 있다. 일반 업체는 관리번호 = 사업자번호 + "0" (계산서발행내역 9곳 중 8곳 확인),
# 유한회사는 전혀 다른 번호라 추정하지 않는다. HRD-Net 목록에서 확인한 번호는 업체별로 저장해 다음부터 그대로 쓴다.
LIMITED = ("유한회사", "(유)", "(유한)", "㈲")


def is_limited(name: str) -> bool:
    return any(t in str(name or "") for t in LIMITED)


def _numbers_file() -> Path:
    return _file().parent / "관리번호.json"


def known_numbers() -> dict[str, dict]:
    f = _numbers_file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def learn_number(company: str, number: str, how: str) -> None:
    """HRD-Net 목록에서 확인된 관리번호를 업체별로 저장 (키 = 정규화한 업체명)."""
    number = "".join(ch for ch in str(number) if ch.isdigit())
    if not number:
        return
    with _lock:
        data = known_numbers()
        data[company_key(company)] = {"업체명": company, "관리번호": number, "확인": how,
                                      "일시": datetime.now().strftime("%Y-%m-%d %H:%M")}
        tmp = _numbers_file().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(_numbers_file())


def resolve_number(business: dict, known: dict | None = None) -> tuple[str, str]:
    """→ (관리번호, 출처). 출처: 엑셀 | 확인됨 | 추정 | 확인필요(유한회사) | 확인필요(사업자번호 없음)"""
    given = "".join(ch for ch in str(business.get("사업장관리번호", "") or "") if ch.isdigit())
    if given:
        return given, "엑셀"
    name = str(business.get("사업장명", "") or "")
    hit = (known_numbers() if known is None else known).get(company_key(name))
    if hit and hit.get("관리번호"):
        return hit["관리번호"], "확인됨"
    if is_limited(name):
        return "", "확인필요(유한회사)"
    biz = "".join(ch for ch in str(business.get("사업자번호", "") or "") if ch.isdigit())
    if len(biz) == 10:
        return biz + "0", "추정"
    return "", "확인필요(사업자번호 없음)"


def default_state(business: dict, has_invoice: bool, has_receipt: bool) -> tuple[str, str]:
    """사람이 아직 안 고른 업체의 기본값. 필수가 비면 불가 + 이유(막지 않고 표시만)."""
    if business.get("제외사유"):
        # 기본값일 뿐 — 사람이 콤보로 고른 상태가 늘 우선한다(merged)
        why = f"대시보드: {business['제외사유']}"
        return ("신청완료" if business["제외사유"] == "비용신청 완료" else "불가"), why
    why = []
    if not has_invoice:
        why.append("전자계산서 없음")
    if not has_receipt:
        why.append("수납확인서 없음")
    if why:
        return "불가", "증빙 대기: " + ", ".join(why)
    _no, source = resolve_number(business)
    if source.startswith("확인필요"):
        # 막지 않는다 — 실행 때 HRD-Net 목록에서 업체명으로 찾고, 못 찾으면 사람에게 알린다
        return "신청가능", f"관리번호 {source} — 실행 때 목록에서 업체명으로 찾음"
    return "신청가능", ""


def merged(course: str, rnd: str, business: dict, has_invoice: bool, has_receipt: bool,
           data: dict | None = None) -> dict:
    """화면용: 저장된 값 + 기본값. 사람이 고른 상태가 있으면 그것이 우선."""
    data = load() if data is None else data
    k = key(course, rnd, business)
    rec = dict(_blank(), **data.get(k, {}))
    auto_state, auto_why = default_state(business, has_invoice, has_receipt)
    if not rec["상태"]:
        rec["상태"] = auto_state
    rec["자동사유"] = auto_why
    rec["key"] = k
    return rec


def update(items: list[dict]) -> int:
    """화면에서 바꾼 상태·사유 (일괄 가능). items: [{key, 상태?, 사유?}]"""
    with _lock:
        data = load()
        n = 0
        for it in items:
            k = str(it.get("key", ""))
            if not k:
                continue
            rec = dict(_blank(), **data.get(k, {}))
            if it.get("상태") in STATES:
                rec["상태"] = it["상태"]
            if "사유" in it:
                rec["사유"] = str(it["사유"])[:300]
            rec["수정"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data[k] = rec
            n += 1
        _save(data)
        return n


def record(keys: str | list[str], **fields) -> None:
    """엔진이 실행 중에 쓰는 기록 (업체 하나 또는 여럿). step=(단계ID, 결과) 를 주면 f13~f30 에 차례로 쌓는다."""
    keys = [keys] if isinstance(keys, str) else list(keys)
    if not keys:
        return
    step = fields.pop("step", None)
    reset = fields.pop("reset_steps", False)
    with _lock:
        data = load()
        for k in keys:
            rec = dict(_blank(), **data.get(k, {}))
            if reset:
                for s in STEP_SLOTS:
                    rec[s] = ""
            for name, value in fields.items():
                if name in rec:
                    rec[name] = "" if value is None else str(value)[:300]
            if step:
                empty = [s for s in STEP_SLOTS if not rec[s]]
                if empty:
                    rec[empty[0]] = f"{step[0]}:{step[1]}"
                else:   # 다 찼으면 마지막 칸에 '…외 n'
                    last = rec[STEP_SLOTS[-1]]
                    n = int(last.rsplit("외 ", 1)[1]) + 1 if last.startswith("…외 ") else 1
                    rec[STEP_SLOTS[-1]] = f"…외 {n}"
            data[k] = rec
        _save(data)


def ask_later(course: str, rnd: str, company: str, message: str) -> None:
    """실행을 멈추지 않고 담당자께 여쭐 것을 모아 둔다 → status/질문목록.md"""
    f = _file().parent / "질문목록.md"
    head = "" if f.exists() else ("# 확인 부탁드립니다\n\n"
                                  "자동 신청 중 대시보드에 없거나 맞지 않는 값이 있어 해당 업체는 건너뛰었습니다.\n"
                                  "아래 항목을 확인해 주시면 다음 실행에 반영하겠습니다. 감사합니다.\n\n")
    line = f"- [{datetime.now():%m-%d %H:%M}] {course} {rnd}회차 · {company or '(업체명 없음)'}: {message}\n"
    with open(f, "a", encoding="utf-8") as fp:
        fp.write(head + line)
