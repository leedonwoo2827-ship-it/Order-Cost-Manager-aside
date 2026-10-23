"""처음 한 번 설치 — setup.bat 이 부른다. 담당자가 보고 알 수 있게 단계·시간·다음 할 일을 한글로 보여 준다.

python setup_env.py <확인할 모듈…>
.venv 를 만들고(있으면 그대로), requirements.txt 를 설치하고, 모듈을 불러 보며 확인한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / "Scripts" / "python.exe"
LINE = "=" * 64


def say(msg: str = "") -> None:
    print(msg, flush=True)


def step(n: int, total: int, msg: str) -> None:
    say()
    say(f"[{n}/{total}] {msg}")
    say("-" * 64)


def done_box(ok: bool, msg: str) -> None:
    say()
    say(LINE)
    say(("  ✔ " if ok else "  ✘ ") + msg)
    say(LINE)


def main(mods: list[str]) -> int:
    t0 = time.time()
    say(LINE)
    say(f"  {ROOT.name} — 처음 한 번 설치")
    say("  ★ 다 끝날 때까지 이 창을 닫지 마세요. (처음에는 3~10분 걸릴 수 있어요)")
    say(LINE)

    step(1, 3, "프로그램 전용 공간(.venv) 준비")
    if PY.exists():
        say("이미 있어요 — 빠진 것만 채웁니다.")
    else:
        say("만드는 중… (30초쯤)")
        r = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
        if r.returncode or not PY.exists():
            done_box(False, "전용 공간을 만들지 못했어요. 이 화면을 캡처해서 보내 주세요.")
            return 1
        say("만들었어요.")

    step(2, 3, "필요한 부품 내려받기·설치 (인터넷 필요)")
    say("아래로 글자가 계속 올라가면 정상이에요. 큰 부품은 막대(━━━)가 차오릅니다.")
    say()
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1")
    subprocess.run([str(PY), "-m", "pip", "install", "--upgrade", "pip", "--progress-bar", "on"], env=env)
    r = subprocess.run([str(PY), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"),
                        "--progress-bar", "on"], env=env)
    if r.returncode:
        done_box(False, "부품 설치에 실패했어요. 인터넷 연결을 확인하고 setup.bat 을 다시 실행해 주세요.\n"
                        "     그래도 안 되면 위쪽 빨간 글자 부분을 캡처해서 보내 주세요.")
        return 1

    step(3, 3, "제대로 설치됐는지 확인")
    bad = []
    for m in mods:
        r = subprocess.run([str(PY), "-c", f"import {m}"], capture_output=True, text=True)
        say(f"  {'✔' if r.returncode == 0 else '✘'} {m}")
        if r.returncode:
            bad.append(m)
    if bad:
        done_box(False, f"확인 실패: {', '.join(bad)} — setup.bat 을 한 번 더 실행해 주세요.")
        return 1

    (VENV / "setup_ok").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")  # run.bat 이 이 표시를 본다
    mins = (time.time() - t0) / 60
    done_box(True, f"설치 완료 ({mins:.1f}분). 이 창은 닫아도 돼요.\n"
                   "     이제 run.bat 을 더블클릭하면 대시보드가 열립니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
