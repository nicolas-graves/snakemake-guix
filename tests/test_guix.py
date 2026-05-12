"""Tests for the Guix software deployment plugin."""

import shutil
import tempfile
from pathlib import Path
from typing import Optional, Type

import pytest

from snakemake_interface_software_deployment_plugins import EnvSpecSourceFile
from snakemake_interface_software_deployment_plugins.settings import (
    SoftwareDeploymentSettingsBase,
)
from snakemake_interface_software_deployment_plugins.tests import (
    TestSoftwareDeploymentBase,
)

from snakemake_software_deployment_plugin_guix import EnvSpec, Env, Settings
from snakemake_software_deployment_plugin_guix.common import (
    get_default_channels,
    is_guix_available,
)


pytestmark = pytest.mark.skipif(
    not is_guix_available(),
    reason="Guix is not available on this system",
)


class TestGuixDeployment(TestSoftwareDeploymentBase):
    __test__ = True

    def setup_method(self, method):
        self.temp_dir = Path(tempfile.mkdtemp())

        self.manifest_path = self.temp_dir / "manifest.scm"
        self.manifest_path.write_text(
            '(specifications->manifest (list "python" "python-numpy"))\n'
        )

        self.channels_path = self.temp_dir / "channels.scm"
        self.channels_path.write_text(get_default_channels())

    def teardown_method(self, method):
        shutil.rmtree(self.temp_dir)

    def get_env_spec(self) -> EnvSpec:
        return EnvSpec(manifest_file=EnvSpecSourceFile(self.manifest_path))

    def get_env_cls(self) -> Type[Env]:
        return Env

    def get_test_cmd(self) -> str:
        return "python -c 'import numpy; print(numpy.__version__)'"

    def get_settings(self) -> Optional[Settings]:
        return Settings(
            container=False,
            no_time_machine=True,
        )

    def get_settings_cls(self) -> Optional[Type[SoftwareDeploymentSettingsBase]]:
        return Settings

    def get_contained_executable(self) -> str:
        return "python"

    def test_contains_executable(self, tmp_path) -> None:
        # Override: guix shell activates on-the-fly, no deployment step needed.
        env = self._get_env(tmp_path)
        assert env.contains_executable(self.get_contained_executable())
