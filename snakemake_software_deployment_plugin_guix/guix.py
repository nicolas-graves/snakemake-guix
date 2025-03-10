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

    def __del__(self):
        # Clean up temporary files
        if self._temp_manifest_file and os.path.exists(self._temp_manifest_file):
            os.unlink(self._temp_manifest_file)

    def decorate_shellcmd(self, cmd: str) -> str:
        """Run the command in a Guix environment."""
        manifest_file = self._get_manifest_path()

        guix_cmd = "guix shell"

        if self.guix_settings.container:
            guix_cmd += " --container"

        guix_cmd += f" -m {manifest_file} -- {cmd}"

        return guix_cmd

    def _get_manifest_path(self) -> str:
        """Get the path to the manifest file to use."""
        # Use specified manifest file if available
        if self.guix_spec.manifest_file:
            return str(self.guix_spec.manifest_file.path_or_uri)

        # Create a manifest file from packages list if no manifest is provided
        if not self._temp_manifest_file:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.scm') as f:
                package_str = '" "'.join(self.guix_spec.packages)
                f.write(f'(specifications->manifest (list "{package_str}"))')
                self._temp_manifest_file = f.name

        return self._temp_manifest_file

    def record_hash(self, hash_object) -> None:
        """Record a hash that changes when the environment content changes."""
        # Hash the manifest content
        manifest_path = self._get_manifest_path()
        with open(manifest_path, "rb") as f:
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

    def remove(self) -> None:
        """Remove the deployed environment."""
        if self.deployment_path.exists():
            shutil.rmtree(self.deployment_path)

    async def archive(self) -> None:
        """Archive the Guix environment.

        For Guix, we just need to archive the manifest file.
        """
        os.makedirs(self.archive_path, exist_ok=True)

        # Archive the manifest file
        manifest_path = self._get_manifest_path()
        shutil.copy(manifest_path, self.archive_path / "manifest.scm")

        # Create a metadata file
        with open(self.archive_path / "metadata.txt", "w") as f:
            f.write(f"Guix environment archived\n")
            f.write(f"Container: {self.guix_settings.container}\n")
            f.write(f"Packages: {', '.join(self.guix_spec.packages)}\n")

    def report_software(self) -> Iterable[SoftwareReport]:
        """Report the software in the environment."""
        # Return the specified packages
        for package in self.guix_spec.packages:
            yield SoftwareReport(name=package)
