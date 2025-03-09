import os
import subprocess
import hashlib
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional, Iterable, Union

from snakemake_interface_software_deployment_plugins import (
    EnvBase, EnvSpecBase, DeployableEnvBase, SoftwareReport
)

from .common import logger, get_environment_hash, run_command, ensure_directory
from .manifest import GuixManifest


class GuixEnv(EnvBase, DeployableEnvBase):
    """Guix environment for Snakemake."""

    def __post_init__(self):
        """Initialize after the parent constructor."""
        # Access the settings from the spec
        self.channels_file = self.settings.channels_file if self.settings else None
        self.container = self.settings.container if self.settings else False
        self.time_machine = self.settings.time_machine if self.settings else True
        self.additional_args = self.settings.additional_args if self.settings else None

        # Initialize manifest handler
        self.manifest = self._initialize_manifest()

        # Create a temporary directory for any environment-specific files
        self.env_dir = tempfile.mkdtemp(prefix="snakemake_guix_")

    def _initialize_manifest(self) -> GuixManifest:
        """Initialize the Guix manifest from the spec."""
        # Extract relevant information from the spec
        packages = self.spec.packages if hasattr(self.spec, "packages") else []
        conda_env_file = self.spec.conda_env_file.path_or_uri if hasattr(self.spec, "conda_env_file") and self.spec.conda_env_file else None
        manifest_file = self.spec.manifest_file.path_or_uri if hasattr(self.spec, "manifest_file") and self.spec.manifest_file else None

        # Get settings
        auto_create_manifest = self.settings.auto_create_manifest if self.settings and hasattr(self.settings, "auto_create_manifest") else True
        manifest_template = self.settings.manifest_template if self.settings and hasattr(self.settings, "manifest_template") else None

        # Create the manifest
        return GuixManifest(
            packages=packages,
            conda_env_file=conda_env_file if auto_create_manifest else None,
            manifest_file=manifest_file,
            manifest_template=manifest_template,
            output_dir=self.env_dir
        )

    def decorate_shellcmd(self, cmd: str) -> str:
        """Decorate a shell command to run in the Guix environment."""
        manifest_path = str(self.manifest.manifest_path)
        channels_option = f"-C {self.channels_file}" if self.channels_file else ""
        container_option = "--container" if self.container else ""
        additional_args = self.additional_args or ""

        # Construct the guix command
        if self.time_machine and self.channels_file:
            guix_prefix = f"guix time-machine {channels_option} -- shell"
        else:
            guix_prefix = "guix shell"

        # Build the full command
        decorated_cmd = (
            f"{guix_prefix} {container_option} {additional_args} "
            f"-m {manifest_path} -- {cmd}"
        )

        return decorated_cmd

    def record_hash(self, hash_object) -> None:
        """Update the hash object with environment-specific information."""
        # Hash the manifest content
        hash_object.update(self.manifest.manifest_content.encode())

        # Hash relevant settings
        hash_object.update(str(self.container).encode())
        hash_object.update(str(self.time_machine).encode())

        if self.channels_file:
            try:
                with open(self.channels_file, 'rb') as f:
                    hash_object.update(f.read())
            except Exception as e:
                logger.warning(f"Failed to read channels file for hashing: {e}")
                hash_object.update(str(self.channels_file).encode())

    def report_software(self) -> Iterable[SoftwareReport]:
        """Report the software in the environment."""
        reports = []

        try:
            # Try to extract package information from the manifest
            package_regex = r'"([^"]+)"'
            manifest_content = self.manifest.manifest_content
            import re

            # Find all package specifications in the manifest
            packages = re.findall(package_regex, manifest_content)

            # Create a report for each package
            for package in packages:
                # Try to extract version if present
                if "@" in package:
                    name, version = package.split("@", 1)
                else:
                    name, version = package, None

                reports.append(SoftwareReport(name=name, version=version))

        except Exception as e:
            logger.warning(f"Failed to extract software information: {e}")
            # Fallback: at least report that we're using Guix
            reports.append(SoftwareReport(name="guix", version=None))

        return reports

    def is_deployment_path_portable(self) -> bool:
        """Check if the deployment path is portable."""
        # Guix environments are generally portable
        return True

    async def deploy(self) -> None:
        """Deploy the Guix environment."""
        # For Guix, there's not much to "deploy" ahead of time
        # We mainly ensure the manifest file exists
        logger.info(f"Preparing Guix environment with manifest: {self.manifest.manifest_path}")

        # Ensure the deployment directory exists
        os.makedirs(self.deployment_path, exist_ok=True)

        # Create a symlink to the manifest in the deployment directory
        manifest_link = self.deployment_path / "manifest.scm"
        if not manifest_link.exists():
            try:
                os.symlink(self.manifest.manifest_path, manifest_link)
            except Exception as e:
                logger.warning(f"Failed to create symlink to manifest: {e}")
                # Copy the manifest instead
                shutil.copy2(self.manifest.manifest_path, manifest_link)

        # Create a record of the command for debugging
        with open(self.deployment_path / "environment.txt", "w") as f:
            example_cmd = self.decorate_shellcmd("echo 'Guix environment is working'")
            f.write(f"Guix environment command:\n{example_cmd}\n")

    def remove(self) -> None:
        """Remove the deployed environment."""
        if os.path.exists(self.deployment_path):
            try:
                shutil.rmtree(self.deployment_path)
            except Exception as e:
                logger.warning(f"Failed to remove deployment directory: {e}")

        # Clean up temporary files
        if hasattr(self, 'env_dir') and os.path.exists(self.env_dir):
            try:
                shutil.rmtree(self.env_dir)
            except Exception as e:
                logger.warning(f"Failed to remove temporary directory: {e}")
