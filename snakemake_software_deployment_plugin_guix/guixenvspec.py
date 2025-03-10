from snakemake_interface_software_deployment_plugins import EnvSpecBase, EnvSpecSourceFile
from typing import Iterable, List, Optional
import sys

# Import common_settings directly
from snakemake_software_deployment_plugin_guix import common_settings

class GuixEnvSpec(EnvSpecBase):
    def __init__(
        self,
        conda_env_file: Optional[str] = None,
        manifest_file: Optional[str] = None,
        packages: Optional[List[str]] = None,
        # other params from your existing settings
    ):
        self.conda_env_file = EnvSpecSourceFile(conda_env_file) if conda_env_file else None
        self.manifest_file = EnvSpecSourceFile(manifest_file) if manifest_file else None
        self.packages = packages or []
        # Initialize other fields

        # Must call this at the end of init
        self.technical_init()

    def technical_init(self):
        """This has to be called by Snakemake upon initialization"""
        self.within = None
        self.fallback = None
        # Use the imported common_settings instead of trying to access via __module__
        self.kind = common_settings.provides

    @classmethod
    def identity_attributes(cls) -> Iterable[str]:
        return ["conda_env_file", "manifest_file", "packages"]

    @classmethod
    def source_path_attributes(cls) -> Iterable[str]:
        return ["conda_env_file", "manifest_file"]
