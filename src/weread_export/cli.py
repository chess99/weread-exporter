from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .browser import ProfileInUseError, clean_profile_locks
from .checkpoint import CheckpointStore
from .exporter import WeReadExporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weread-export")
    parser.add_argument("--profile", default="data/browser-profile", help="Playwright persistent profile path")
    parser.add_argument("--output", default="output", help="Output root directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headful", action="store_true", default=True, help="Run browser visibly")
    mode.add_argument("--headless", action="store_true", help="Run browser headless")

    sub = parser.add_subparsers(dest="command", required=True)
    export_cmd = sub.add_parser("export", help="Export a WeRead reader URL or book id")
    export_cmd.add_argument("target")
    export_cmd.add_argument("--max-pages", type=int)
    export_cmd.add_argument("--overwrite", action="store_true")

    resume_cmd = sub.add_parser("resume", help="Resume an existing book export")
    resume_cmd.add_argument("book_id")
    resume_cmd.add_argument("--max-pages", type=int)

    inspect_cmd = sub.add_parser("inspect", help="Inspect export manifest")
    inspect_cmd.add_argument("book_id")

    sub.add_parser("clean-locks", help="Stop Chromium processes using this profile")
    return parser


async def run_async(args: argparse.Namespace) -> int:
    output = Path(args.output)
    profile = Path(args.profile)
    headless = bool(args.headless)
    exporter = WeReadExporter(output, profile, headless=headless)

    try:
        if args.command == "export":
            manifest = await exporter.export(args.target, max_pages=args.max_pages, overwrite=args.overwrite)
            print(json.dumps(manifest.to_json_dict(), ensure_ascii=False, indent=2))
            return 0 if manifest.status != "failed" else 1
        if args.command == "resume":
            manifest = await exporter.resume(args.book_id, max_pages=args.max_pages)
            print(json.dumps(manifest.to_json_dict(), ensure_ascii=False, indent=2))
            return 0 if manifest.status != "failed" else 1
    except ProfileInUseError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    return 1


def inspect_manifest(output: Path, book_id: str) -> int:
    store = CheckpointStore(output, book_id)
    if not store.manifest_path.exists():
        print(f"No manifest found for {book_id}", file=sys.stderr)
        return 2
    print(store.manifest_path.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = Path(args.output)
    profile = Path(args.profile)
    if args.command == "inspect":
        return inspect_manifest(output, args.book_id)
    if args.command == "clean-locks":
        count = clean_profile_locks(profile)
        print(f"Stopped {count} Chromium process(es) for profile {profile}")
        return 0
    return asyncio.run(run_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

