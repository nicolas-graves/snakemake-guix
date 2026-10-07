from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
import sys
from typing import cast

from .contracts import list_modules, load_provides, provides, validate_repo


def _cmd_list_modules(args: argparse.Namespace) -> int:
    for module in list_modules(args.repo_root):
        print(module)
    return 0


def _cmd_list_keys(args: argparse.Namespace) -> int:
    data = load_provides(args.module, args.repo_root)
    for key in sorted(data):
        print(f"{key}\t{data[key]}")
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    print(provides(args.module, args.key, args.repo_root))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    problems = validate_repo(args.repo_root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snakemake-contracts")
    parser.add_argument("--repo-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-modules")
    p.set_defaults(func=_cmd_list_modules)

    p = sub.add_parser("list-keys")
    p.add_argument("module")
    p.set_defaults(func=_cmd_list_keys)

    p = sub.add_parser("resolve")
    p.add_argument("module")
    p.add_argument("key")
    p.set_defaults(func=_cmd_resolve)

    p = sub.add_parser("validate")
    p.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = cast(Callable[[argparse.Namespace], int], args.func)
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
