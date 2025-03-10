"""Guix environment implementation for Snakemake."""

import os
import sys
import subprocess
import tempfile
import shutil
import hashlib
from pathlib import Path
import re
from typing import List, Dict, Optional, Union, Any, Tuple, Iterable

from snakemake_interface_common.exceptions import WorkflowError
from snakemake_interface_software_deployment_plugins import (
    EnvBase,
    EnvSpecBase,
    DeployableEnvBase,
    SoftwareReport
)

from .common import (
    logger,
    get_environment_hash,
    run_command,
    ensure_directory,
    is_guix_available,
)
from .manifest import GuixManifest, create_default_channels_file


class GuixDeploymentHelper:
    """Helper class for Guix deployment."""

    @staticmethod
    def execute_command(
        manifest_path: Path,
        cmd: str,
        channels_file: Optional[Path] = None,
        container: bool = False,
        time_machine: bool = True,
        additional_args: Optional[str] = None,
        shell_executable: str = 'bash',
    ) -> subprocess.CompletedProcess:
        """Execute a command in a Guix environment.

        Args:
            manifest_path: Path to the manifest file
            cmd: Command to execute
            channels_file: Path to the channels file
            container: Whether to use container isolation
            time_machine: Whether to use guix time-machine
            additional_args: Additional arguments to pass to guix
            shell_executable: Shell to use for execution

        Returns:
            CompletedProcess instance with return code, stdout, and stderr
        """
        # Build the Guix command
        guix_cmd = []

        if time_machine and channels_file:
            guix_cmd = ["guix", "time-machine", "-C", str(channels_file), "--", "shell"]
        else:
            guix_cmd = ["guix", "shell"]

        if container:
            guix_cmd.append("--container")

        if additional_args:
            guix_cmd.extend(additional_args.split())

        guix_cmd.extend(["-m", str(manifest_path), "--"])

        # Split the command if it's a string
        if isinstance(cmd, str):
            full_cmd = " ".join(guix_cmd) + " " + cmd
            # Run the command with shell=True
            logger.debug(f"Executing: {full_cmd}")
            result = subprocess.run(
                full_cmd,
                shell=True,
                executable=shell_executable,
                check=False,
                capture_output=True,
                text=True
            )
        else:
            # Combine the commands
            full_cmd = guix_cmd + cmd
            # Run the command without shell
            logger.debug(f"Executing: {' '.join(full_cmd)}")
            result = subprocess.run(
                full_cmd,
                check=False,
                capture_output=True,
                text=True
            )

        if result.returncode != 0:
            logger.error(f"Command failed with exit code {result.returncode}")
            logger.error(f"Standard error: {result.stderr}")

        return result
