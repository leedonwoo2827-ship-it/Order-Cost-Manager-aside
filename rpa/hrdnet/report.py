"""보낼 파일 만들기 — 문제가 생겼을 때 개발 쪽에 보낼 것을 zip 하나로 묶는다.

묶는 것: 최근 실행 기록(회차별 .jsonl·.summary.json, 기본 3회차), 그 실행의 화면 사진(logs/shots — 찾기실패·채움·확인전),
가장 최근 [화면 진단] 결과(txt·png), 지금 매크로의 steps.yaml, local.json(비밀번호 칸은 뺀다).
결과: logs/보낼파일_<시각>.zip — 끝나면 logs 폴더를 연다.
화면 사진에는 훈련생 이름 등이 보일 수 있으니 사내 메일로만 보낸다.
"""
from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime

from . import config, macros


def run(rounds: int = 3) -> None:
    cfg = config.load()
    d = config.dirs(cfg)
    logs = d["logs"]
    out = logs / f"보낼파일_{datetime.now():%Y%m%d_%H%M%S}.zip"
    runs = sorted(logs.glob("*.summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:rounds]
    names = [p.name[: -len(".summary.json")] for p in runs]
    inspects = sorted(logs.glob("inspect_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:1]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            for p in (logs / f"{n}.jsonl", logs / f"{n}.summary.json"):
                if p.exists():
                    z.write(p, f"기록/{p.name}")
            for p in d["shots"].glob(f"{n}_*.png"):
                z.write(p, f"화면/{p.name}")
        for p in inspects:
            z.write(p, f"화면진단/{p.name}")
            png = p.with_suffix(".png")
            if png.exists():
                z.write(png, f"화면진단/{png.name}")
        mdir = macros.path()
        if (mdir / "steps.yaml").exists():
            z.write(mdir / "steps.yaml", f"매크로/{mdir.name}_steps.yaml")
        safe = {k: v for k, v in cfg.items() if "password" not in k}
        z.writestr("local.json", json.dumps(safe, ensure_ascii=False, indent=1))
    print(f"보낼 파일: {out}  (실행 기록 {len(names)}회차, 화면 진단 {len(inspects)}개)", flush=True)
    for n in names:
        print(f"  · {n}", flush=True)
    try:
        os.startfile(logs)  # noqa: S606 — 담당자가 바로 메일에 첨부하게 폴더를 연다
    except OSError:
        pass
