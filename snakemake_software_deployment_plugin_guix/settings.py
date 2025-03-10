from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

from snakemake_interface_software_deployment_plugins.settings import (
    SoftwareDeploymentSettingsBase,
)
from snakemake_software_deployment_plugin_guix.common import get_default_channels_file


@dataclass
class GuixSettings(SoftwareDeploymentSettingsBase):
    """Settings for the Guix software deployment plugin."""

    container: bool = field(
        default=False,
        metadata={"help": "Run Guix with --container option for better isolation"}
    )

    time_machine: bool = field(
        default=True,
        metadata={"help": "Use guix time-machine for reproducibility"}
    )

    channels_file: Optional[Path] = field(
        default=None,
        metadata={"help": "Path to a Guix channels file"}
    )

    additional_args: Optional[List[str]] = field(
        default=None,
        metadata={"help": "Additional arguments for guix shell"}
    )

    auto_create_manifest: bool = field(
        default=True,
        metadata={"help": "Convert conda env files to Guix manifests"}
    )

    manifest_template: Optional[Path] = field(
        default=None,
        metadata={"help": "Path to a template manifest file"}
    )

    def __post_init__(self):
        # If no channels file is provided, create a default one
        if self.channels_file is None and self.time_machine:
            self.channels_file = get_default_channels_file()
