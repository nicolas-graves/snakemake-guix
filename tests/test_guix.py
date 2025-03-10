"""Tests for the Guix software deployment plugin."""

import os
import sys
import tempfile
import pytest
import shutil
from pathlib import Path
from copy import deepcopy

from snakemake_interface_software_deployment_plugins import EnvSpecSourceFile, SoftwareReport
from snakemake_interface_software_deployment_plugins.tests import TestSoftwareDeploymentBase

from snakemake_software_deployment_plugin_guix.guixenvspec import GuixEnvSpec
from snakemake_software_deployment_plugin_guix.guixenv import GuixEnv
from snakemake_software_deployment_plugin_guix.settings import GuixSettings
from snakemake_software_deployment_plugin_guix.common import is_guix_available, get_default_channels


# Skip all tests if Guix is not available
pytestmark = pytest.mark.skipif(
    not is_guix_available(),
    reason="GNU Guix is not available on this system"
)


class TestGuixDeployment(TestSoftwareDeploymentBase):
    """Test the Guix software deployment plugin."""

    __test__ = True  # Mark this as a test class

    def setup_method(self, method):
        """Set up temporary files for testing."""
        self.temp_dir = tempfile.mkdtemp()

        # Create a manifest file
        self.manifest_path = Path(self.temp_dir) / "manifest.scm"
        with open(self.manifest_path, "w") as f:
            f.write('(specifications->manifest (list "python" "python-numpy"))')

        # Create a channels file
        self.channels_path = Path(self.temp_dir) / "channels.scm"
        with open(self.channels_path, "w") as f:
            f.write(get_default_channels())

    def teardown_method(self, method):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)

    def get_env_spec(self) -> GuixEnvSpec:
        """Get a test environment specification."""
        return GuixEnvSpec(
            packages=["python", "python-numpy"],
            manifest_file=self.manifest_path,  # We're only including this in source_path_attributes
        )

    # Override the problematic method to handle None values properly
    def _get_cached_env_spec(self):
        """Override to handle None values properly."""
        spec = deepcopy(self.get_env_spec())
        for attr in spec.source_path_attributes():
            source_file = getattr(spec, attr)
            if source_file is not None:  # Only set cached if not None
                source_file.cached = source_file.path_or_uri
        return spec

    def get_env_cls(self):
        """Get the environment class."""
        return GuixEnv

    def get_test_cmd(self) -> str:
        """Get a test command that should work in the environment."""
        return "python -c 'import numpy; print(numpy.__version__)'"

    def get_software_deployment_provider_settings(self):
        """Get settings for the deployment provider."""
        return GuixSettings(
            container=False,
            time_machine=False,
            channels_file=self.channels_path,
            auto_create_manifest=True
        )

    def test_source_path_attributes(self):
        """Override to properly check for None values."""
        spec = self.get_env_spec()
        for attr in spec.source_path_attributes():
            assert isinstance(attr, str), f"Attribute name {attr} is not a string"
            assert hasattr(spec, attr), f"Spec does not have attribute {attr}"
            value = getattr(spec, attr)
            assert value is None or isinstance(value, EnvSpecSourceFile), \
                f"Attribute {attr} must be None or EnvSpecSourceFile, got {type(value)}"
