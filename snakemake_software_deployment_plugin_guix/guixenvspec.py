from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

from snakemake_interface_software_deployment_plugins import EnvSpecBase, EnvSpecSourceFile
from snakemake_software_deployment_plugin_guix.common import common_settings  # noqa: F401


@dataclass(eq=False)
class EnvSpec(EnvSpecBase):
    manifest_file: Optional[EnvSpecSourceFile] = None
    packages: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if isinstance(self.manifest_file, (str, Path)):
            self.manifest_file = EnvSpecSourceFile(self.manifest_file)
        if isinstance(self.packages, list):
            self.packages = tuple(self.packages)

    @classmethod
    def env_cls(cls):
        from snakemake_software_deployment_plugin_guix.guixenv import Env
        return Env

    @classmethod
    def identity_attributes(cls) -> Iterable[str]:
        yield "manifest_file"
        yield "packages"

    @classmethod
    def source_path_attributes(cls) -> Iterable[str]:
        # manifest_file is handled manually in __post_init__ to stay optional
        return ()

    def __str__(self) -> str:
        if self.manifest_file is not None:
            return str(self.manifest_file.path_or_uri)
        if self.packages:
            return " ".join(self.packages)
        return "guix"
