"""Guix manifest handling for the Guix deployment plugin."""

import os
import re
import hashlib
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Union, Any

from .common import logger, DEFAULT_MANIFEST_TEMPLATE, hash_string
from .conda_to_guix import conda_env_to_guix_packages, packages_to_guix_manifest

class GuixManifest:
    """Class for handling Guix manifests."""

    def __init__(
        self,
        packages: Optional[List[str]] = None,
        conda_env_file: Optional[Union[str, Path]] = None,
        manifest_file: Optional[Union[str, Path]] = None,
        manifest_template: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None
    ):
        """Initialize a GuixManifest.

        Args:
            packages: List of Guix package specifications
            conda_env_file: Path to a conda environment file to convert
            manifest_file: Path to an existing manifest file to use
            manifest_template: Path to a template manifest file to use
            output_dir: Directory to write manifest files to
        """
        self.packages = packages or []
        self.conda_env_file = conda_env_file
        self.manifest_file = manifest_file
        self.manifest_template = manifest_template
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "snakemake_guix"

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize manifest content
        self._manifest_content = None
        self._manifest_path = None

    @property
    def manifest_content(self) -> str:
        """Get the manifest content."""
        if self._manifest_content is None:
            self._manifest_content = self._generate_manifest_content()
        return self._manifest_content

    @property
    def manifest_path(self) -> Path:
        """Get the path to the manifest file."""
        if self._manifest_path is None:
            self._manifest_path = self._get_or_create_manifest_file()
        return self._manifest_path

    def _generate_manifest_content(self) -> str:
        """Generate the manifest content based on the inputs."""
        # If a manifest file is provided, use that
        if self.manifest_file:
            with open(self.manifest_file, 'r') as f:
                return f.read()

        # If a conda environment file is provided, convert it
        if self.conda_env_file:
            try:
                guix_packages = conda_env_to_guix_packages(self.conda_env_file)
                self.packages.extend(guix_packages)
            except Exception as e:
                logger.warning(f"Failed to convert conda environment to Guix packages: {e}")

        # Deduplicate packages
        self.packages = list(set(self.packages))

        # If we have packages, generate a manifest
        if self.packages:
            if self.manifest_template:
                # Use the template file and insert our packages
                with open(self.manifest_template, 'r') as f:
                    template = f.read()

                packages_str = '\n'.join([f'  "{pkg}"' for pkg in self.packages])
                return template.replace("{packages}", packages_str)
            else:
                # Use our default template
                return packages_to_guix_manifest(self.packages)

        # If we get here, we couldn't generate a manifest
        raise ValueError(
            "Unable to generate manifest content. "
            "Provide either packages, a conda environment file, or a manifest file."
        )

    def _get_or_create_manifest_file(self) -> Path:
        """Get the path to the manifest file, creating it if necessary."""
        # If a manifest file is provided and it exists, use that
        if self.manifest_file and os.path.exists(self.manifest_file):
            return Path(self.manifest_file)

        # Generate a filename based on the content
        manifest_hash = hash_string(self.manifest_content)
        manifest_path = self.output_dir / f"manifest_{manifest_hash}.scm"

        # Write the manifest file
        with open(manifest_path, 'w') as f:
            f.write(self.manifest_content)

        return manifest_path

    def __str__(self) -> str:
        """Return the path to the manifest file as a string."""
        return str(self.manifest_path)


def create_default_channels_file(output_dir: Union[str, Path]) -> Path:
    """Create a default Guix channels file."""
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    channels_content = """(list (channel
        (name 'guix)
        (url "https://git.savannah.gnu.org/git/guix.git")
        (branch "master")))
"""

    channels_file = output_dir / "channels.scm"
    with open(channels_file, 'w') as f:
        f.write(channels_content)

    return channels_file
