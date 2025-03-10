"""Settings for the Guix software deployment plugin."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict

from snakemake_interface_software_deployment_plugins.settings import (
    SoftwareDeploymentSettingsBase,
)


@dataclass
class GuixSettings(SoftwareDeploymentSettingsBase):
    """Settings for the Guix software deployment method."""

    channels_file: Optional[str] = field(
        default=None,
        metadata={
            "help": "Path to Guix channels file (channels.scm)",
            "required": False,
        },
    )

    manifest_file: Optional[str] = field(
        default=None,
        metadata={
            "help": "Path to an existing Guix manifest file (manifest.scm)",
            "required": False,
        },
    )

    container: bool = field(
        default=False,
        metadata={
            "help": "Run Guix with --container option for isolation",
            "required": False,
        },
    )

    gc_root_dir: Optional[str] = field(
        default=None,
        metadata={
            "help": "Directory for storing Guix garbage collection roots",
            "required": False,
        },
    )

    time_machine: bool = field(
        default=True,
        metadata={
            "help": "Use guix time-machine for reproducible environments",
            "required": False,
        },
    )

    additional_args: Optional[str] = field(
        default=None,
        metadata={
            "help": "Additional arguments to pass to guix shell or guix time-machine",
            "required": False,
        },
    )

    auto_create_manifest: bool = field(
        default=True,
        metadata={
            "help": "Automatically create manifest files from conda environment files",
            "required": False,
        },
    )

    manifest_template: Optional[str] = field(
        default=None,
        metadata={
            "help": "Path to a template manifest file to use as a base",
            "required": False,
        },
    )
