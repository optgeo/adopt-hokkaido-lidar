"""CLI entry point: `python -m adopt_hokkaido_lidar <verb>`.

Runnable directly without `just`; the justfile is a thin wrapper around this.
Only the verbs implemented so far are wired in -- unimplemented verbs from
the startup spec's full command surface will be added as their underlying
modules land.
"""

from __future__ import annotations

import argparse
import sys

from . import db


def cmd_init_db(args: argparse.Namespace) -> int:
    conn = db.connect(args.db_path)
    conn.close()
    print(f"initialized schema at {args.db_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adopt-hokkaido-lidar")
    sub = parser.add_subparsers(dest="verb", required=True)

    p_init_db = sub.add_parser("init-db", help="Create/upgrade the local SQLite state database.")
    p_init_db.add_argument("--db-path", default="state.sqlite3")
    p_init_db.set_defaults(func=cmd_init_db)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
