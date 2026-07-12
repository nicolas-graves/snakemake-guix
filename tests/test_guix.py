"""Tests for the Guix software deployment plugin."""

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Type

import pytest

from snakemake_interface_common.exceptions import WorkflowError
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

        self.sample_url = "https://git.savannah.gnu.org/git/guix.git"
        self.sample_commit = "abc123def456"
        self.sample_branch = "master"

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

    def test_decorated_command_cleans_generated_manifest(self) -> None:
        spec = EnvSpec(packages=["hello"])
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

        command = env.decorate_shellcmd("hello")
        manifest_path = Path(command.split(" -m ", 1)[1].split(" -- ", 1)[0])

        assert manifest_path.exists()
        assert command.startswith("trap ")
        assert f"rm -f {manifest_path}" in command

    def test_decorated_commands_use_separate_generated_manifests(self) -> None:
        spec = EnvSpec(packages=["hello"])
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

        first_command = env.decorate_shellcmd("hello")
        second_command = env.decorate_shellcmd("hello")
        first_manifest_path = Path(
            first_command.split(" -m ", 1)[1].split(" -- ", 1)[0]
        )
        second_manifest_path = Path(
            second_command.split(" -m ", 1)[1].split(" -- ", 1)[0]
        )

        assert first_manifest_path != second_manifest_path
        assert first_manifest_path.exists()
        assert second_manifest_path.exists()

    def test_decorated_command_keeps_user_manifest(self) -> None:
        spec = EnvSpec(manifest_files=[EnvSpecSourceFile(self.manifest_path)])
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

        command = env.decorate_shellcmd("hello")

        assert command == f"guix shell -m {self.manifest_path} -- bash -c hello"
        assert "rm -f" not in command

    def test_report_software_exposes_names_only(self) -> None:
        spec = EnvSpec(
            manifest_files=[EnvSpecSourceFile(self.manifest_path)],
            packages=[
                "python-wrapper",
                {"name": "python-pandas", "version": "2.2.0", "is_secondary": False},
            ],
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

        assert [rec.name for rec in env.report_software()] == [
            str(self.manifest_path),
            "python-wrapper",
            "python-pandas",
        ]

    def test_manifest_file_deprecated_alias_still_works(self) -> None:
        with pytest.warns(FutureWarning):
            spec = EnvSpec(manifest_file=EnvSpecSourceFile(self.manifest_path))

        assert spec.manifest_files == (EnvSpecSourceFile(self.manifest_path),)

    def test_channels_file_str_is_coerced_to_source_file(self) -> None:
        spec = EnvSpec(packages=["hello"], channels_file=str(self.channels_path))
        assert isinstance(spec.channels_file, EnvSpecSourceFile)
        assert str(spec.channels_file.path_or_uri) == str(self.channels_path)

    def test_channels_file_is_rewritten_as_source_path(self) -> None:
        spec = EnvSpec(
            packages=["hello"],
            channels_file=EnvSpecSourceFile(Path("relative-channels.scm")),
        )
        spec.technical_init()

        rewritten = spec.modify_source_paths(
            lambda source_file: EnvSpecSourceFile(
                self.temp_dir / Path(source_file.path_or_uri).name
            )
        )

        assert str(rewritten.channels_file.path_or_uri) == str(
            self.temp_dir / "relative-channels.scm"
        )

    def test_channels_file_affects_identity(self) -> None:
        base = EnvSpec(packages=["hello"])
        with_channels = EnvSpec(
            packages=["hello"], channels_file=EnvSpecSourceFile(self.channels_path)
        )
        base.technical_init()
        with_channels.technical_init()

        assert base != with_channels
        assert hash(base) != hash(with_channels)

    def test_decorate_shellcmd_uses_per_rule_channels_file(self) -> None:
        spec = EnvSpec(
            manifest_files=[EnvSpecSourceFile(self.manifest_path)],
            channels_file=EnvSpecSourceFile(self.channels_path),
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

        command = env.decorate_shellcmd("hello")

        assert command.startswith(
            f"guix time-machine -C {self.channels_path} -- guix shell"
        )

    def test_decorate_shellcmd_global_channels_file_overrides_per_rule(self) -> None:
        other_channels_path = self.temp_dir / "other-channels.scm"
        other_channels_path.write_text(get_default_channels())

        spec = EnvSpec(
            manifest_files=[EnvSpecSourceFile(self.manifest_path)],
            channels_file=EnvSpecSourceFile(self.channels_path),
        )
        env = Env(
            spec=spec,
            within=None,
            settings=Settings(channels_file=other_channels_path),
            shell_executable=ShellExecutable(executable="/bin/sh", command_arg="-c"),
            mountpoints=[],
            tempdir=self.temp_dir,
            cache_prefix=self.temp_dir,
            deployment_prefix=self.temp_dir,
            pinfile_prefix=self.temp_dir,
        )

        command = env.decorate_shellcmd("hello")

        assert command.startswith(
            f"guix time-machine -C {other_channels_path} -- guix shell"
        )

    def test_record_hash_excludes_channels_when_no_time_machine(self) -> None:
        spec = EnvSpec(
            packages=["hello"], channels_file=EnvSpecSourceFile(self.channels_path)
        )

        def make_env(no_time_machine: bool) -> Env:
            return Env(
                spec=spec,
                within=None,
                settings=Settings(no_time_machine=no_time_machine),
                shell_executable=ShellExecutable(
                    executable="/bin/sh", command_arg="-c"
                ),
                mountpoints=[],
                tempdir=self.temp_dir,
                cache_prefix=self.temp_dir,
                deployment_prefix=self.temp_dir,
                pinfile_prefix=self.temp_dir,
            )

        enabled_hash = hashlib.md5(usedforsecurity=False)
        make_env(no_time_machine=False).record_hash(enabled_hash)

        disabled_hash = hashlib.md5(usedforsecurity=False)
        make_env(no_time_machine=True).record_hash(disabled_hash)

        assert enabled_hash.hexdigest() != disabled_hash.hexdigest()

    def test_url_commit_branch_default_to_none(self) -> None:
        spec = EnvSpec(packages=["hello"])
        assert spec.url is None
        assert spec.commit is None
        assert spec.branch is None

    def test_url_commit_branch_affect_identity(self) -> None:
        base = EnvSpec(packages=["hello"])
        with_commit = EnvSpec(packages=["hello"], commit=self.sample_commit)
        base.technical_init()
        with_commit.technical_init()

        assert base != with_commit
        assert hash(base) != hash(with_commit)

    def _make_env(
        self,
        spec: EnvSpec,
        settings: Optional[Settings] = None,
    ) -> Env:
        return Env(
            spec=spec,
            within=None,
            settings=settings,
            shell_executable=ShellExecutable(executable="/bin/sh", command_arg="-c"),
            mountpoints=[],
            tempdir=self.temp_dir,
            cache_prefix=self.temp_dir,
            deployment_prefix=self.temp_dir,
            pinfile_prefix=self.temp_dir,
        )

    def test_decorate_shellcmd_uses_per_rule_commit(self) -> None:
        spec = EnvSpec(
            manifest_files=[EnvSpecSourceFile(self.manifest_path)],
            commit=self.sample_commit,
        )
        env = self._make_env(spec)

        command = env.decorate_shellcmd("hello")

        assert command.startswith(
            f"guix time-machine --commit={self.sample_commit} -- guix shell"
        )

    def test_decorate_shellcmd_combines_url_and_branch(self) -> None:
        spec = EnvSpec(
            manifest_files=[EnvSpecSourceFile(self.manifest_path)],
            url=self.sample_url,
            branch=self.sample_branch,
        )
        env = self._make_env(spec)

        command = env.decorate_shellcmd("hello")

        assert command.startswith(
            f"guix time-machine --url={self.sample_url} "
            f"--branch={self.sample_branch} -- guix shell"
        )

    def test_decorate_shellcmd_per_field_settings_override(self) -> None:
        spec = EnvSpec(
            manifest_files=[EnvSpecSourceFile(self.manifest_path)],
            commit=self.sample_commit,
        )
        env = self._make_env(spec, settings=Settings(branch="devel"))

        command = env.decorate_shellcmd("hello")

        assert f"--commit={self.sample_commit}" in command
        assert "--branch=devel" in command

    def test_no_time_machine_suppresses_conflict(self) -> None:
        spec = EnvSpec(
            packages=["hello"],
            channels_file=EnvSpecSourceFile(self.channels_path),
            commit=self.sample_commit,
        )
        env = self._make_env(spec, settings=Settings(no_time_machine=True))

        command = env.decorate_shellcmd("hello")

        assert "time-machine" not in command
        assert "guix shell" in command

    def test_channels_file_and_refs_conflict_raises(self) -> None:
        spec = EnvSpec(packages=["hello"], commit=self.sample_commit)
        env = self._make_env(spec, settings=Settings(channels_file=self.channels_path))

        with pytest.raises(WorkflowError):
            env.decorate_shellcmd("hello")

    def test_record_hash_reflects_commit_value(self) -> None:
        def make_env(commit: str) -> Env:
            spec = EnvSpec(packages=["hello"], commit=commit)
            return self._make_env(spec)

        first_hash = hashlib.md5(usedforsecurity=False)
        make_env(commit=self.sample_commit).record_hash(first_hash)

        second_hash = hashlib.md5(usedforsecurity=False)
        make_env(commit="other-commit").record_hash(second_hash)

        assert first_hash.hexdigest() != second_hash.hexdigest()
