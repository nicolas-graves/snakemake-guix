import asyncio
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from snakemake_interface_software_deployment_plugins import (
    DeployableEnvBase,
    ArchiveableEnvBase,
    EnvBase,
    SoftwareReport
)
from snakemake_software_deployment_plugin_guix.guixenvspec import GuixEnvSpec
from snakemake_software_deployment_plugin_guix.settings import GuixSettings


class GuixEnv(EnvBase, DeployableEnvBase, ArchiveableEnvBase):
    """Guix environment implementation."""

    def __init__(
        self,
        spec: GuixEnvSpec,
        within: Optional["EnvBase"],
        settings: Optional[GuixSettings],
        shell_executable: str,
        deployment_prefix: Optional[Path] = None,
        archive_prefix: Optional[Path] = None,
    ):
        super().__init__(
            spec=spec,
            within=within,
            settings=settings,
            shell_executable=shell_executable,
            deployment_prefix=deployment_prefix,
            archive_prefix=archive_prefix,
        )
        self.guix_spec = spec
        self.guix_settings = settings or GuixSettings()

        # Create temp file for manifest if needed
        self._temp_manifest_file = None
        self._temp_files = []

    def __del__(self):
        # Clean up temporary files
        for temp_file in self._temp_files:
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass

    def decorate_shellcmd(self, cmd: str) -> str:
        """Run the command in a Guix environment."""
        manifest_file = self._get_manifest_path()

        if self.guix_settings.time_machine and self.guix_settings.channels_file:
            # Use time-machine for reproducibility
            guix_cmd = f"guix time-machine -C {self.guix_settings.channels_file} -- shell"
        else:
            guix_cmd = "guix shell"

        if self.guix_settings.container:
            guix_cmd += " --container"

        # Add any additional arguments
        if self.guix_settings.additional_args:
            guix_cmd += " " + " ".join(self.guix_settings.additional_args)

        guix_cmd += f" -m {manifest_file} -- {cmd}"

        return guix_cmd

    def _get_manifest_path(self) -> str:
        """Get the path to the manifest file to use."""
        # Use specified manifest file if available
        if self.guix_spec.manifest_file:
            return str(self.guix_spec.manifest_file.path_or_uri)

        # Use conda environment file if available and auto-create is enabled
        if self.guix_spec.conda_env_file and self.guix_settings.auto_create_manifest:
            # This would require parsing the conda env file and converting to a Guix manifest
            # For now, we'll just create a manifest from the packages list
            pass

        # Create a manifest file from packages list if no manifest is provided
        if not self._temp_manifest_file:
            fd, path = tempfile.mkstemp(suffix='.scm', prefix='guix-manifest-')
            with os.fdopen(fd, 'w') as f:
                package_str = '" "'.join(self.guix_spec.packages)
                f.write(f'(specifications->manifest (list "{package_str}"))')
                self._temp_manifest_file = path
                self._temp_files.append(path)

        return self._temp_manifest_file

    def record_hash(self, hash_object) -> None:
        """Record a hash that changes when the environment content changes."""
        # Hash the manifest content
        manifest_path = self._get_manifest_path()
        with open(manifest_path, "rb") as f:
            hash_object.update(f.read())

        # Hash the channels file if using time-machine
        if self.guix_settings.time_machine and self.guix_settings.channels_file:
            with open(self.guix_settings.channels_file, "rb") as f:
                hash_object.update(f.read())

        # Also hash the settings
        hash_object.update(str(self.guix_settings.container).encode())
        hash_object.update(str(self.guix_settings.time_machine).encode())

        # Hash the packages list
        for package in sorted(self.guix_spec.packages):
            hash_object.update(package.encode())

    def is_deployment_path_portable(self) -> bool:
        """Guix deployments are generally portable."""
        return True

    async def deploy(self) -> None:
        """Deploy the Guix environment."""
        # Guix environments are based on manifests and are created on-the-fly
        # No need for actual deployment since Guix handles this
        manifest_path = self._get_manifest_path()

        # Create a marker file to indicate deployment was attempted
        os.makedirs(self.deployment_path, exist_ok=True)
        with open(self.deployment_path / "deployed", "w") as f:
            f.write("Guix environment deployed\n")

        # Also copy the manifest file to the deployment path for reference
        shutil.copy(manifest_path, self.deployment_path / "manifest.scm")

        # Copy the channels file if applicable
        if self.guix_settings.time_machine and self.guix_settings.channels_file:
            shutil.copy(self.guix_settings.channels_file, self.deployment_path / "channels.scm")

    def remove(self) -> None:
        """Remove the deployed environment."""
        if self.deployment_path.exists():
            shutil.rmtree(self.deployment_path)

    async def archive(self) -> None:
        """Archive the Guix environment.

        For Guix, we just need to archive the manifest file and channels file.
        """
        os.makedirs(self.archive_path, exist_ok=True)

        # Archive the manifest file
        manifest_path = self._get_manifest_path()
        shutil.copy(manifest_path, self.archive_path / "manifest.scm")

        # Archive the channels file if applicable
        if self.guix_settings.time_machine and self.guix_settings.channels_file:
            shutil.copy(self.guix_settings.channels_file, self.archive_path / "channels.scm")

        # Create a metadata file
        with open(self.archive_path / "metadata.txt", "w") as f:
            f.write(f"Guix environment archived\n")
            f.write(f"Container: {self.guix_settings.container}\n")
            f.write(f"Time Machine: {self.guix_settings.time_machine}\n")
            f.write(f"Packages: {', '.join(self.guix_spec.packages)}\n")

    def report_software(self) -> Iterable[SoftwareReport]:
        """Report the software in the environment."""
        # Return the specified packages
        for package in self.guix_spec.packages:
            yield SoftwareReport(name=package)
