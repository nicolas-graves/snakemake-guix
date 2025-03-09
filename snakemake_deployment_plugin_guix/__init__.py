"""Snakemake deployment plugin for GNU Guix."""

__version__ = "0.1.0"

from snakemake_interface_software_deployment_plugins.settings import (
    CommonSettings, SoftwareDeploymentSettingsBase
)

from .guixenv import GuixEnv
from .guixenvspec import GuixEnvSpec

common_settings = CommonSettings(
    provides="guix"
)
