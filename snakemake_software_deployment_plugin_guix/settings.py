from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from snakemake_interface_software_deployment_plugins.settings import (
    SoftwareDeploymentSettingsBase,
)


@dataclass
class Settings(SoftwareDeploymentSettingsBase):
    container: bool = field(
        default=False,
        metadata={"help": "Run guix shell with --container for better isolation."},
    )
    # Named no_time_machine with default=False rather than time_machine with default=True
    # to work around a bug in argparse_dataclass: _handle_bool_type replaces the flag
    # name with --no-{field.name} (unprefixed) when default=True, so the argument ends
    # up registered as --no-time-machine with dest="time_machine" instead of the
    # expected --sdm-guix-no-time-machine / sdm_guix_time_machine.
    no_time_machine: bool = field(
        default=False,
        metadata={"help": "Disable guix time-machine (skips reproducibility pin)."},
    )
    channels_file: Optional[Path] = field(
        default=None,
        metadata={"help": "Path to a Guix channels file for use with time-machine."},
    )
    url: Optional[str] = field(
        default=None,
        metadata={
            "help": "Git repository URL to use with guix time-machine "
            "(overrides any per-rule url=)."
        },
    )
    commit: Optional[str] = field(
        default=None,
        metadata={
            "help": "Commit to use with guix time-machine "
            "(overrides any per-rule commit=)."
        },
    )
    branch: Optional[str] = field(
        default=None,
        metadata={
            "help": "Branch tip to use with guix time-machine "
            "(overrides any per-rule branch=)."
        },
    )
    additional_args: Optional[List[str]] = field(
        default=None,
        metadata={"help": "Additional arguments forwarded to guix shell."},
    )
