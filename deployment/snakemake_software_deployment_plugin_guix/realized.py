"""Public, executor-facing description of a realized Guix environment."""

from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Optional, Tuple


@dataclass(frozen=True)
class GuixPin:
    """The effective Guix time-machine pin used to realize a profile."""

    kind: str
    value: object


@dataclass(frozen=True)
class RealizedEnvironment:
    """Immutable runtime contract shared with remote executors.

    ``profile_store_path`` is deliberately the resolved store item rather than
    the mutable profile link in Snakemake's cache.
    """

    digest: str
    profile_store_path: Path
    manifest_digest: str
    guix_pin: Optional[GuixPin]
    container: bool
    additional_args: Tuple[str, ...]

    def decorate(self, command: str) -> str:
        """Run *command* from the immutable profile represented by this object."""
        prefix = "guix shell"
        if self.container:
            prefix += " --container"
        if self.additional_args:
            prefix += " " + " ".join(shlex.quote(arg) for arg in self.additional_args)
        return (
            f"{prefix} -p {shlex.quote(str(self.profile_store_path))} -- "
            f"bash -c {shlex.quote(command)}"
        )
