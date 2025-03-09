"""Tests for the Guix software deployment plugin."""

import os
import sys
import tempfile
import pytest
from pathlib import Path

from snakemake_interface_software_deployment_plugins import EnvSpecSourceFile, SoftwareReport
from snakemake_interface_software_deployment_plugins.tests import TestSoftwareDeploymentBase

from snakemake_deployment_plugin_guix.guixenvspec import GuixEnvSpec
from snakemake_deployment_plugin_guix.guixenv import GuixEnv
from snakemake_deployment_plugin_guix.settings import GuixSettings
from snakemake_deployment_plugin_guix.common import is_guix_available


# Skip all tests if Guix is not available
pytestmark = pytest.mark.skipif(
    not is_guix_available(),
    reason="GNU Guix is not available on this system"
)


class TestGuixDeployment(TestSoftwareDeploymentBase):
    """Test the Guix software deployment plugin."""

    __test__ = True  # Mark this as a test class

    def get_env_spec(self) -> GuixEnvSpec:
        """Get a test environment specification."""
        # Create a basic environment spec with Python
        return GuixEnvSpec(
            packages=["python", "python-numpy"],
            conda_env_file=None,
            manifest_file=None
        )

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
            time_machine=True,
            auto_create_manifest=True
        )
