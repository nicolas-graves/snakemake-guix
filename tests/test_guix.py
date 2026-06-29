"""Tests for the Guix software deployment plugin."""

import shutil
import tempfile
from pathlib import Path
from typing import Optional, Type

import pytest

from snakemake_interface_software_deployment_plugins import (
    EnvSpecSourceFile,
    ShellExecutable,
)
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

        self.extra_manifest_path = self.temp_dir / "extra-manifest.scm"
        self.extra_manifest_path.write_text(
            '(specifications->manifest (list "hello"))\n'
        )

        self.channels_path = self.temp_dir / "channels.scm"
        self.channels_path.write_text(get_default_channels())

    def teardown_method(self, method):
        shutil.rmtree(self.temp_dir)

    def get_env_spec(self) -> EnvSpec:
        return EnvSpec(manifest_files=[EnvSpecSourceFile(self.manifest_path)])

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

    def test_manifest_files_are_rewritten_as_source_paths(self) -> None:
        spec = EnvSpec(
            manifest_files=[
                EnvSpecSourceFile(Path("relative-a.scm")),
                EnvSpecSourceFile(Path("relative-b.scm")),
            ]
        )
        spec.technical_init()

        rewritten = spec.modify_source_paths(
            lambda source_file: EnvSpecSourceFile(
                self.temp_dir / Path(source_file.path_or_uri).name
            )
        )

        assert [
            str(source_file.path_or_uri) for source_file in rewritten.manifest_files
        ] == [
            str(self.temp_dir / "relative-a.scm"),
            str(self.temp_dir / "relative-b.scm"),
        ]
        assert rewritten.manifest_file == rewritten.manifest_files[0]

    def test_aggregate_manifest_combines_files_and_packages(self) -> None:
        spec = EnvSpec(
            manifest_files=[
                EnvSpecSourceFile(self.manifest_path),
                EnvSpecSourceFile(self.extra_manifest_path),
            ],
            packages=["bash-minimal"],
        )
        env = Env(
            spec=spec,
            within=None,
            settings=None,
            shell_executable=ShellExecutable(executable="/bin/sh", command_arg="-c"),
            mountpoints=[],
            tempdir=self.temp_dir,
            cache_prefix=self.temp_dir,
            deployment_prefix=self.temp_dir,
            pinfile_prefix=self.temp_dir,
        )

        manifest_path = Path(env._manifest_path())
        content = manifest_path.read_text()

        assert "(use-modules (guix profiles) (gnu))" in content
        assert "(concatenate-manifests (list" in content
        assert str(self.manifest_path) in content
        assert str(self.extra_manifest_path) in content
        assert '(specifications->manifest (list "bash-minimal"))' in content

    def test_manifest_file_deprecated_alias_still_works(self) -> None:
        with pytest.warns(FutureWarning):
            spec = EnvSpec(manifest_file=EnvSpecSourceFile(self.manifest_path))

        assert spec.manifest_files == (EnvSpecSourceFile(self.manifest_path),)
