"""Command-line entry point for the HRD-Net cost-claim engine."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from . import config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hrdnet")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("ui", help="start the local RPA dashboard")
    sub.add_parser("sample", help="create sample input files")

    fetch = sub.add_parser("fetch", help="watch Downloads or open the source dashboard")
    fetch.add_argument("mode", nargs="?", default="30", help="watch minutes or 'browser'")

    sub.add_parser("organize", help="organize inbox files by course and round")
    sub.add_parser("inspect", help="inspect the open HRD-Net window")
    sub.add_parser("hrdnet-open", help="open or position the HRD-Net window")

    upload_all = sub.add_parser("upload-all", help="process all selected round folders")
    mode = upload_all.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="find controls without clicking")
    mode.add_argument("--simulate", action="store_true", help="simulate without controlling HRD-Net")
    mode.add_argument("--fill", action="store_true", help="fill fields but stop before final submission")
    upload_all.add_argument("--only", default="", help="comma-separated outbox folder names")

    result = sub.add_parser("result", help="create the result table")
    result.add_argument("day", nargs="?", default="", help="result date (optional)")

    backup = sub.add_parser("backup", help="back up completed rounds")
    backup.add_argument("--include-test", action="store_true", help="also back up test/fill results")

    sub.add_parser("has-viewer-password", help="check whether LAN viewer access is configured")
    password = sub.add_parser("viewer-password", help="set the LAN viewer password")
    password.add_argument("password")
    return parser


def _set_viewer_password(password: str) -> None:
    cfg = config.load()
    cfg["viewer_password"] = password
    config.LOCAL.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command in (None, "ui"):
        from .web.server import serve

        serve()
    elif args.command == "sample":
        from .sample import run

        run()
    elif args.command == "fetch":
        from . import fetch

        if args.mode.lower() == "browser":
            fetch.browser()
        else:
            try:
                minutes = float(args.mode)
            except ValueError:
                parser.error("fetch 인수는 감시 시간(분) 또는 'browser'여야 합니다")
            fetch.watch(minutes)
    elif args.command == "organize":
        from .organize import run

        run()
    elif args.command == "inspect":
        from .inspect_hrdnet import run

        run()
    elif args.command == "hrdnet-open":
        from .winpos import open_hrdnet

        open_hrdnet()
    elif args.command == "upload-all":
        from .upload import run_all

        only = [name for name in args.only.split(",") if name] if args.only else None
        run_all(dry=args.dry_run, simulate=args.simulate, fill=args.fill, only=only)
    elif args.command == "result":
        from .result import run

        run(args.day)
    elif args.command == "backup":
        from .backup import run

        run(include_test=args.include_test)
    elif args.command == "has-viewer-password":
        return 0 if config.load().get("viewer_password") else 1
    elif args.command == "viewer-password":
        _set_viewer_password(args.password)
    else:
        parser.error(f"지원하지 않는 명령: {args.command}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
