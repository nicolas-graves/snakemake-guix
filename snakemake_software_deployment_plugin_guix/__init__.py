"""
Snakemake software deployment plugin for GNU Guix.

This plugin provides support for using GNU Guix as a software deployment
provider in Snakemake workflows.
"""

from snakemake_software_deployment_plugin_guix.guixenvspec import GuixEnvSpec
from snakemake_software_deployment_plugin_guix.guixenv import GuixEnv
from snakemake_software_deployment_plugin_guix.settings import GuixSettings
from snakemake_software_deployment_plugin_guix.common import common_settings, is_guix_available

# These class references need to be at the module level for the plugin registry to find them
EnvSpec = GuixEnvSpec
Env = GuixEnv
