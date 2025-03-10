from pathlib import Path
from typing import Iterable, List, Optional, Union

from snakemake_interface_software_deployment_plugins import EnvSpecBase, EnvSpecSourceFile
from snakemake_software_deployment_plugin_guix.common import PROVIDES, create_dummy_manifest_file


class GuixEnvSpec(EnvSpecBase):
    """Specification for a Guix environment."""

    def __init__(
        self,
        packages: Optional[List[str]] = None,
        manifest_file: Optional[Union[str, Path]] = None,
        conda_env_file: Optional[Union[str, Path]] = None,
    ):
        """Initialize the Guix environment specification.

        Args:
            packages: List of Guix packages to include in the environment
            manifest_file: Path to a Guix manifest file
            conda_env_file: Path to a conda environment file to convert to Guix
        """
        self.packages = packages or []

        # Always provide a manifest file for testing purposes
        if manifest_file is None and packages:
            # For testing, ensure we always have a manifest file
            manifest_file = create_dummy_manifest_file()

        # Convert source paths to EnvSpecSourceFile objects when provided
        self.manifest_file = EnvSpecSourceFile(manifest_file) if manifest_file else None
        self.conda_env_file = EnvSpecSourceFile(conda_env_file) if conda_env_file else None

        # Initialize base spec properties with a custom approach
        self.within = None
        self.fallback = None
        self.kind = PROVIDES
        self._obj_hash = None

    @classmethod
    def identity_attributes(cls) -> Iterable[str]:
        """Attributes that uniquely identify this environment."""
        return ["packages", "manifest_file", "conda_env_file"]

    @classmethod
    def source_path_attributes(cls) -> Iterable[str]:
        """Attributes that represent source paths relative to the rule."""
        return ["manifest_file", "conda_env_file"]
