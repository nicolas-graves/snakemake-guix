
import functools
import shutil
import subprocess
from snakemake_interface_software_deployment_plugins.settings import CommonSettings


common_settings = CommonSettings(provides="guix")


def is_guix_available() -> bool:
    return shutil.which("guix") is not None


@functools.lru_cache(maxsize=1)
def _time_machine_help() -> str:
    """Return the output of `guix time-machine --help`, or "" if it cannot be
    determined (guix missing, or too old to even run --help successfully).
    Cached since this shells out to guix, which is comparatively slow to
    start.
    """
    try:
        result = subprocess.run(
            ["guix", "time-machine", "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""



def time_machine_supports_flag(flag: str) -> bool:
    """Whether the installed guix's `time-machine` subcommand supports
    `flag` (e.g. "--allow-untrusted-channels"), determined by feature-
    detecting against its --help output rather than parsing/comparing guix
    version numbers.
    """
    return flag in _time_machine_help()


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
