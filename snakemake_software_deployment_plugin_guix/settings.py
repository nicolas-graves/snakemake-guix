import warnings
from dataclasses import dataclass, field
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
    channels: Optional[str] = field(
        default=None,
        metadata={
            "help": "Guix channels file-or-uri for use with time-machine "
            "(local path, http(s) URL, or Software Heritage SWHID); "
            "overrides any per-rule channels=."
        },
    )
    channels_file: Optional[str] = field(
        default=None,
        metadata={"help": "Deprecated; use --sdm-guix-channels instead."},
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
    allow_untrusted_channels: bool = field(
        default=False,
        metadata={
            "help": "Pass --allow-untrusted-channels to guix time-machine, "
            "bypassing commit-signature verification. Security-relevant: only "
            "enable if you trust the channel source."
        },
    )
    unsafe_channel_evaluation: bool = field(
        default=False,
        metadata={
            "help": "Pass --unsafe-channel-evaluation to guix time-machine, "
            "allowing arbitrary code execution from channels files. "
            "Security-relevant: only enable if you trust the channels file "
            "content."
        },
    )

    def __post_init__(self) -> None:
        if self.channels_file is not None:
            warnings.warn(
                "--sdm-guix-channels-file is deprecated; use "
                "--sdm-guix-channels instead.",
                FutureWarning,
                stacklevel=2,
            )
            if self.channels is None:
                self.channels = self.channels_file
