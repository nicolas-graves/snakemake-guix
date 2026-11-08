import os
import shlex
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any, Protocol, TypeAlias, TYPE_CHECKING

from snakemake.shell import shell  # type: ignore[import-not-found,import-untyped]
from snakemake_contracts_wrapper import render_shell

PathValue: TypeAlias = str | PathLike[str]


class _Snakemake(Protocol):
    input: Any
    output: Any
    log: Any
    params: Any
    config: Mapping[str, Any]
    threads: int


if TYPE_CHECKING:
    snakemake: _Snakemake


def _require_path_like(value: object, name: str) -> PathValue:
    if (
        value is None
        or isinstance(value, (bool, list, tuple, dict, set))
        or str(value) == ""
    ):
        raise ValueError(f"snakemake-contracts wrapper requires {name} to be a path")
    if not isinstance(value, (str, PathLike)):
        raise ValueError(f"snakemake-contracts wrapper requires {name} to be a path")
    return value


try:
    _script = snakemake.input["script"]
except (KeyError, TypeError) as error:
    raise ValueError(
        "snakemake-contracts wrapper requires a named input 'script'"
    ) from error
_script = _require_path_like(_script, "input 'script'")

_log = snakemake.log
if (
    not _log
    and snakemake.config.get("scripts_accept_log_arg") is True
    and (cache := snakemake.config.get("cache"))
):
    cache = _require_path_like(cache, "config 'cache'")
    _default_log = Path(cache) / "logs" / (Path(_script).stem + ".log")
    _default_log.parent.mkdir(parents=True, exist_ok=True)
    _log = {"log": str(_default_log)}

# Files another module exports (ctx.python) arrive as the `python` input: their directories go on
# PYTHONPATH, inside the job's own software environment, and they are not passed as arguments.
try:
    _exports = snakemake.input["python"] or []
except (KeyError, AttributeError, TypeError):
    _exports = []
if isinstance(_exports, (str, PathLike)):
    _exports = [_exports]
_dirs = list(dict.fromkeys(str(Path(path).resolve().parent) for path in _exports))
_pythonpath = (f"PYTHONPATH={shlex.quote(os.pathsep.join(_dirs))}${{PYTHONPATH:+{os.pathsep}$PYTHONPATH}} "
               if _dirs else "")

_threads = str(snakemake.threads)
shell(_pythonpath + render_shell(
    script=_script,
    input=snakemake.input,
    output=snakemake.output,
    log=_log,
    params=snakemake.params,
    exclude_input=("script", "python"),
), additional_envvars={
    "OMP_NUM_THREADS": _threads,
    "GOTO_NUM_THREADS": _threads,
    "OPENBLAS_NUM_THREADS": _threads,
    "MKL_NUM_THREADS": _threads,
    "VECLIB_MAXIMUM_THREADS": _threads,
    "NUMEXPR_NUM_THREADS": _threads,
})
