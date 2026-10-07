from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from os import PathLike
from pathlib import Path
import shlex
from typing import Any, TypeAlias

PathValue: TypeAlias = str | PathLike[str]


def snake_to_kebab(name: str) -> str:
    return name.replace("_", "-")


def namespace_flag(namespace: str, name: str, *, output_prefix: str = "output-") -> str:
    flag = snake_to_kebab(name)
    if namespace == "output" and flag != namespace:
        flag = f"{output_prefix}{flag}"
    return f"--{flag}"


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, bytes, PathLike, Path)) or not isinstance(value, Iterable)


def _iter_items(namespace: Any) -> list[tuple[str, Any]]:
    if namespace is None:
        return []
    if isinstance(namespace, Mapping):
        return list(namespace.items())
    items = getattr(namespace, "items", None)
    if callable(items):
        return list(items())
    keys = getattr(namespace, "keys", None)
    if callable(keys):
        return [(key, namespace[key]) for key in keys()]
    raise TypeError(f"Unsupported namespace object: {type(namespace)!r}")


def _extend_namespace(
    argv: list[str],
    *,
    namespace: str,
    values: Any,
    exclude: set[str] | None = None,
    output_prefix: str = "output-",
) -> None:
    excluded = exclude or set()
    for name, value in _iter_items(values):
        if name in excluded:
            continue
        flag = namespace_flag(namespace, name, output_prefix=output_prefix)
        if _is_scalar(value):
            argv.extend([flag, str(value)])
            continue
        for item in value:
            argv.extend([flag, str(item)])


def build_argv(
    command: str | Sequence[Any] | None = None,
    *,
    script: PathValue | None = None,
    input: Any = None,
    output: Any = None,
    log: Any = None,
    params: Any = None,
    exclude_input: Iterable[str] = ("script",),
    output_prefix: str = "output-",
) -> list[str]:
    if script is not None and command is not None:
        raise ValueError("specify either command or script, not both")
    if script is not None:
        command = [str(script)]
    if command is None:
        raise ValueError("either command or script must be specified")

    argv: list[str] = []
    if isinstance(command, str):
        argv.append(command)
    else:
        argv.extend(str(item) for item in command)

    _extend_namespace(
        argv,
        namespace="input",
        values=input,
        exclude=set(exclude_input),
        output_prefix=output_prefix,
    )
    _extend_namespace(
        argv,
        namespace="output",
        values=output,
        output_prefix=output_prefix,
    )
    _extend_namespace(
        argv,
        namespace="log",
        values=log,
        output_prefix=output_prefix,
    )
    _extend_namespace(
        argv,
        namespace="params",
        values=params,
        output_prefix=output_prefix,
    )
    return argv


def render_shell(
    command: str | Sequence[Any] | None = None,
    *,
    script: PathValue | None = None,
    input: Any = None,
    output: Any = None,
    log: Any = None,
    params: Any = None,
    exclude_input: Iterable[str] = ("script",),
    output_prefix: str = "output-",
) -> str:
    return " ".join(
        shlex.quote(arg)
        for arg in build_argv(
            command,
            script=script,
            input=input,
            output=output,
            log=log,
            params=params,
            exclude_input=exclude_input,
            output_prefix=output_prefix,
        )
    )
