#!/usr/bin/env python3
"""Export the OS_* environment set from a trusted OpenRC file as JSON."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("openrc", type=Path, help="OpenRC shell file to load")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="record path (created with mode 0600; JSON is also valid YAML)",
    )
    args = parser.parse_args()

    if not args.openrc.is_file():
        parser.error(f"OpenRC file not found: {args.openrc}")
    if args.output.exists() and args.output.resolve() == args.openrc.resolve():
        parser.error("output must not overwrite the OpenRC source file")

    # OpenRC files are shell programs. Load the trusted file in a child Bash,
    # leaving stdin attached so its password prompt can be answered normally.
    command = 'source "$1" >/dev/null && env -0'
    source_env = os.environ.copy()
    for name in tuple(source_env):
        if name.startswith("OS_"):
            del source_env[name]
    try:
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", command, "openrc-to-json", str(args.openrc)],
            stdout=subprocess.PIPE,
            check=True,
            env=source_env,
        )
    except (OSError, subprocess.CalledProcessError):
        print("Could not load the OpenRC file.", file=sys.stderr)
        return 1

    values: dict[str, str] = {}
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        key, separator, value = entry.partition(b"=")
        if separator and key.startswith(b"OS_"):
            values[key.decode("utf-8")] = value.decode("utf-8")
    if not values:
        print("The OpenRC file did not set any OS_* variables.", file=sys.stderr)
        return 1

    output = args.output
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(values, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temp_name, output)
            os.chmod(output, 0o600)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(temp_name).unlink(missing_ok=True)
            raise
    except OSError:
        print(f"Could not write record: {output}", file=sys.stderr)
        return 1

    print(f"Wrote {len(values)} OS_* variables to {output} (mode 0600).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
