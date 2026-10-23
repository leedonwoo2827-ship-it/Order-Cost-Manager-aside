"""백업·정리 — 끝난 회차의 파일을 지우지 않고 백업 폴더로 옮긴다.

기본: 신청 '성공'한 회차만. --include-test 면 모의완료·점검완료·채움완료 회차도(시험 데이터 정리용).
옮기는 것: outbox/<회차>, inbox/증빙/<회차>, logs 의 그 회차 기록·캡처, 7일 지난 logs 전부.
보관 기간: local.json 의 backup_keep_days (기본 90일). 이 기간이 지난 백업 폴더는 실행할 때 자동으로 삭제한다.
장기 보관: local.json 의 archive_root (클라우드 동기화 폴더·내부 보안 PC 공유 폴더 등)를 정하면, 백업할 때 그곳으로 복사하고
  복사가 끝난 백업(.archived 표식)만 보관 기간 뒤에 삭제한다. 복사 못 한 백업은 기간이 지나도 지우지 않는다.
  삭제는 backup_root 바로 아래의 "YYYYMMDD_HHMM" 이름이면서 이 프로그램이 만든 README.txt 가 있는 폴더만 대상이다.
남기는 것: 결과/(결과표), _archive/(정리된 원본 CSV), 아직 안 끝난 회차.
백업 위치: local.json 의 backup_root (비우면 <data_root>/_백업/<날짜_시각>/). 다른 드라이브로 정해도 된다.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import config

TEST_STATES = ("모의완료", "점검완료", "채움완료")
LOG_KEEP_DAYS = 7
DEFAULT_KEEP_DAYS = 90
ARCHIVED = ".archived"         # 장기 보관처로 복사가 끝났다는 표식
MARK = "README.txt"          # 우리가 만든 백업 폴더 표식 — 이게 없으면 지우지 않는다


def backup_root(cfg: dict | None = None) -> Path:
    cfg = cfg or config.load()
    return Path(cfg.get("backup_root") or (Path(cfg["data_root"]) / "_백업"))


def _move(src: Path, dst: Path, moved: list[str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    target = dst
    n = 1
    while target.exists():           # 같은 이름이 있으면 덮어쓰지 않고 번호를 붙인다
        n += 1
        target = dst.with_name(f"{dst.stem}({n}){dst.suffix}")
    shutil.move(str(src), str(target))
    moved.append(str(src))


def list_backups(cfg: dict | None = None) -> list[dict]:
    """탭에서 보여 줄 백업 목록 (최신순). 안에 든 회차와 상태, 장기 보관 여부, 삭제 예정일."""
    cfg = cfg or config.load()
    root = backup_root(cfg)
    days = int(cfg.get("backup_keep_days", DEFAULT_KEEP_DAYS) or 0)
    out: list[dict] = []
    if not root.is_dir():
        return out
    for sub in sorted(root.iterdir(), reverse=True):
        if not (sub.is_dir() and re.fullmatch(r"\d{8}_\d{4}", sub.name) and (sub / MARK).is_file()):
            continue
        rounds = []
        for m in sorted((sub / "outbox").glob("*/manifest.json")):
            try:
                j = json.loads(m.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rounds.append({"folder": m.parent.name, "과정명": j.get("과정명"), "회차": j.get("회차"),
                           "사업장": len(j.get("사업장", [])), "신청금액": j.get("신청금액", 0),
                           "상태": (j.get("올리기") or {}).get("상태", ""), "끝": (j.get("올리기") or {}).get("끝", "")})
        files = [f for f in sub.rglob("*") if f.is_file()]
        when = datetime.strptime(sub.name, "%Y%m%d_%H%M")
        out.append({"name": sub.name, "path": str(sub), "시각": when.strftime("%Y-%m-%d %H:%M"), "회차": rounds,
                    "파일": len(files), "MB": round(sum(f.stat().st_size for f in files) / 1e6, 1),
                    "장기보관": (sub / ARCHIVED).exists(),
                    "삭제예정": (when.timestamp() + days * 86400 and datetime.fromtimestamp(when.timestamp() + days * 86400).strftime("%Y-%m-%d")) if days > 0 else ""})
    return out


def archive(cfg: dict) -> list[str]:
    """archive_root 가 정해져 있으면 아직 복사 안 한 백업을 그곳으로 복사한다(원본은 그대로)."""
    dst_root = cfg.get("archive_root")
    copied: list[str] = []
    if not dst_root:
        return copied
    root = backup_root(cfg)
    if not root.is_dir():
        return copied
    for sub in sorted(root.iterdir()):
        if not (sub.is_dir() and re.fullmatch(r"\d{8}_\d{4}", sub.name) and (sub / MARK).is_file()) or (sub / ARCHIVED).exists():
            continue
        try:
            shutil.copytree(sub, Path(dst_root) / sub.name, dirs_exist_ok=True)
            (sub / ARCHIVED).write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
            copied.append(sub.name)
        except OSError as e:
            print(f"  ! 장기 보관처로 복사 실패 ({sub.name}): {e}", flush=True)
    return copied


def purge(cfg: dict) -> list[str]:
    """보관 기간(backup_keep_days)이 지난 백업 폴더를 삭제. 0 이하면 아무것도 지우지 않는다."""
    days = int(cfg.get("backup_keep_days", DEFAULT_KEEP_DAYS) or 0)
    root = backup_root(cfg)
    gone: list[str] = []
    if days <= 0 or not root.is_dir():
        return gone
    cutoff = datetime.now().timestamp() - days * 86400
    for sub in sorted(root.iterdir()):
        if not (sub.is_dir() and re.fullmatch(r"\d{8}_\d{4}", sub.name) and (sub / MARK).is_file()):
            continue
        try:
            when = datetime.strptime(sub.name, "%Y%m%d_%H%M").timestamp()
        except ValueError:
            continue
        if cfg.get("archive_root") and not (sub / ARCHIVED).exists():
            continue                  # 장기 보관처로 복사 못 한 백업은 기간이 지나도 지우지 않는다
        if when < cutoff:
            shutil.rmtree(sub, ignore_errors=True)
            gone.append(sub.name)
    return gone


def run(include_test: bool = False) -> dict:
    cfg = config.load()
    d = config.dirs(cfg)
    dest = backup_root(cfg) / datetime.now().strftime("%Y%m%d_%H%M")
    ok_states = ("성공",) + (TEST_STATES if include_test else ())
    moved: list[str] = []

    done = []
    for m in sorted(d["outbox"].glob("*/manifest.json")):
        try:
            j = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (j.get("올리기") or {}).get("상태") in ok_states:
            done.append(m.parent)

    for folder in done:
        _move(folder, dest / "outbox" / folder.name, moved)
        ev = d["증빙"] / folder.name
        if ev.exists():
            _move(ev, dest / "증빙" / folder.name, moved)
        for f in list(d["logs"].glob(f"*{folder.name}*")) + list(d["shots"].glob(f"*{folder.name}*")):
            if f.is_file():
                _move(f, dest / "logs" / f.relative_to(d["logs"]), moved)

    cutoff = time.time() - LOG_KEEP_DAYS * 86400
    for f in list(d["logs"].glob("*")) + list(d["shots"].glob("*")):
        if f.is_file() and not f.name.startswith("_") and f.stat().st_mtime < cutoff:
            _move(f, dest / "logs" / f.relative_to(d["logs"]), moved)

    if moved:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README.txt").write_text(
            f"백업 시각: {datetime.now():%Y-%m-%d %H:%M:%S}\n회차 {len(done)}개 · 파일/폴더 {len(moved)}개를 옮김 (지우지 않음)\n"
            "되돌리려면 outbox/증빙/logs 안의 항목을 원래 data_root 의 같은 이름 폴더로 옮기면 된다.\n", encoding="utf-8")
    print(f"백업 대상 회차 {len(done)}개 ({'/'.join(ok_states)})", flush=True)
    for f in done:
        print(f"  · {f.name}", flush=True)
    print(f"옮긴 파일·폴더 {len(moved)}개 → {dest if moved else '(옮길 것이 없었어요)'}", flush=True)
    copied = archive(cfg)
    if cfg.get("archive_root"):
        print(f"장기 보관처로 복사 {len(copied)}개 → {cfg['archive_root']}", flush=True)
    gone = purge(cfg)
    days = int(cfg.get("backup_keep_days", DEFAULT_KEEP_DAYS) or 0)
    if days > 0:
        print(f"보관 {days}일이 지난 백업 {len(gone)}개 삭제" + (": " + ", ".join(gone) if gone else ""), flush=True)
    else:
        print("자동 삭제 꺼짐 (backup_keep_days = 0)", flush=True)
    return {"회차": len(done), "옮김": len(moved), "위치": str(dest), "삭제": gone}
