import shutil
import subprocess
from snakemake_interface_software_deployment_plugins.settings import CommonSettings


common_settings = CommonSettings(provides="guix")


def is_guix_available() -> bool:
    return shutil.which("guix") is not None


def get_default_channels() -> str:
    """Return current Guix channels as a string, falling back to a minimal stub."""
    try:
        result = subprocess.run(
            ["guix", "describe", "-f", "channels"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return (
            '(list (channel\n'
            "  (name 'guix)\n"
            '  (url "https://git.savannah.gnu.org/git/guix.git")))\n'
        )
