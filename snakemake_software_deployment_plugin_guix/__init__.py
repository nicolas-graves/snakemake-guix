"""Snakemake deployment plugin for GNU Guix."""

__version__ = "0.1.0"

from snakemake_interface_software_deployment_plugins.settings import (
    CommonSettings, SoftwareDeploymentSettingsBase
)

common_settings = CommonSettings(
    provides="guix"
)

# Import these *after* defining common_settings
from .guixenv import GuixEnv as Env
from .guixenvspec import GuixEnvSpec as EnvSpec
from .settings import GuixSettings as SoftwareDeploymentSettings

# These aliases are what the plugin system expects to find
EnvBase = Env
EnvSpecBase = EnvSpec

# Make plugin API available
__all__ = ["common_settings", "EnvBase", "EnvSpecBase", "SoftwareDeploymentSettings"]
