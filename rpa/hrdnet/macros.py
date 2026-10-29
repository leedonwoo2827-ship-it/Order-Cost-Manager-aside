"""매크로 — rpa/macros/<id>/ 하나가 자동화 하나다.

  macro.yaml          id, 표시명, 설명, 원본, 생성일, 상태(사용|시험중)
  steps.yaml          단계 순서와 화면 요소(target)
  templates/learned/  학습 녹화로 잡은 버튼 이미지
  learned_actions.json

새 매크로는 기본 매크로를 복사해서 시작한다(clone). 시험중인 매크로는 [신청]을 막고,
[학습 미리채워 보기]로 사람 단계를 줄여 사람 단계가 0이 되면 사용으로 올린다(promote).
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from . import config

DEFAULT_ID = "hrd-wituk-claim-v1"
DIR = config.ROOT / "macros"

# 모드는 모든 매크로에 공통 — 대시보드·패널·엔진 대시보드가 /api/macros 로 받아 쓴다
MODES = [
    {"id": "simulate", "label": "모의 실행", "hint": "HRD-Net 없이 순서만 훑기", "flag": "--simulate"},
    {"id": "dry-run", "label": "점검", "hint": "화면에서 버튼을 찾기만 하고 누르지 않기", "flag": "--dry-run"},
    {"id": "fill", "label": "미리 채워 보기", "hint": "최종 신청 직전까지 채우고 멈추기", "flag": "--fill"},
    {"id": "live", "label": "신청", "hint": "실제 신청. 회차마다 패널에서 사람이 최종 확인", "flag": ""},
]


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_-]", "-", value.strip()).strip("-")[:60]


def path(macro_id: str | None = None) -> Path:
    # 실행 중에는 __main__ 이 --macro 값을 HRD_MACRO 로 넘긴다 (학습 녹화도 같은 매크로 폴더에 저장)
    mid = _safe_id(macro_id or os.environ.get("HRD_MACRO") or config.load().get("macro") or DEFAULT_ID)
    p = DIR / mid
    if not (p / "steps.yaml").exists():
        raise FileNotFoundError(f"매크로를 찾지 못했습니다: {mid}")
    return p


def meta(p: Path) -> dict:
    m = {"id": p.name, "표시명": p.name, "설명": "", "원본": "", "생성일": "", "상태": "사용"}
    f = p / "macro.yaml"
    if f.exists():
        m.update(yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    m["id"] = p.name
    return m


def spec(macro_id: str | None = None) -> dict:
    return yaml.safe_load((path(macro_id) / "steps.yaml").read_text(encoding="utf-8")) or {}


def window_pattern(macro_id: str | None = None) -> str:
    try:
        return spec(macro_id).get("window", ".*HRD.*")
    except (OSError, FileNotFoundError):
        return ".*HRD.*"


def listing() -> list[dict]:
    out = [meta(p) for p in sorted(DIR.iterdir()) if (p / "steps.yaml").exists()] if DIR.exists() else []
    out.sort(key=lambda m: (m["id"] != DEFAULT_ID, m.get("생성일", "")))
    return out


def _write_meta(p: Path, m: dict) -> None:
    (p / "macro.yaml").write_text(yaml.safe_dump(m, allow_unicode=True, sort_keys=False), encoding="utf-8")


def clone(name: str, source: str = DEFAULT_ID) -> dict:
    """기본(또는 지정한) 매크로를 복사해 시험중 매크로를 만든다."""
    src = path(source)
    mid = _safe_id(name)
    if not mid:
        raise ValueError("매크로 이름을 적어 주세요")
    dest = DIR / mid
    if dest.exists():
        raise ValueError(f"같은 이름의 매크로가 이미 있습니다: {mid}")
    shutil.copytree(src, dest)
    m = {"id": mid, "표시명": name.strip(), "설명": f"{meta(src)['표시명']} 에서 복사", "원본": src.name,
         "생성일": datetime.now().strftime("%Y-%m-%d %H:%M"), "상태": "시험중"}
    _write_meta(dest, m)
    return m


def promote(macro_id: str) -> dict:
    p = path(macro_id)
    m = meta(p)
    m["상태"] = "사용"
    m["승격일"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _write_meta(p, m)
    return m
