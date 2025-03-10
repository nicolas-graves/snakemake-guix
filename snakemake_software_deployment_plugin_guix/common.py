import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from snakemake_interface_software_deployment_plugins.settings import CommonSettings


# Define common settings for the plugin - this is used by the registry
common_settings = CommonSettings(
    provides="guix"
)

# This will be accessed by our classes directly
PROVIDES = "guix"


def is_guix_available() -> bool:
    """Check if GNU Guix is available on the system."""
    return shutil.which("guix") is not None


def get_default_channels() -> str:
    """Get the default Guix channels by running 'guix describe -f channels'.

    Returns:
        str: The content of the default channels file
    """
    try:
        result = subprocess.run(
            ["guix", "describe", "-f", "channels"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        # Fallback to a basic channels definition if the command fails
        return """(list (channel
        (name 'guix)
        (url "https://git.savannah.gnu.org/git/guix.git")
        (branch "master")))"""


def get_default_channels_file() -> Path:
    """Create a temporary file with the default channels and return its path.

    Returns:
        Path: Path to the temporary channels file
    """
    channels_content = get_default_channels()
    fd, path = tempfile.mkstemp(suffix='.scm', prefix='guix-channels-')
    with os.fdopen(fd, 'w') as f:
        f.write(channels_content)
    return Path(path)


def create_dummy_manifest_file() -> Path:
    """Create a dummy manifest file for testing purposes.

    Returns:
        Path: Path to the temporary manifest file
    """
    content = '(specifications->manifest (list "python" "python-numpy"))'
    fd, path = tempfile.mkstemp(suffix='.scm', prefix='guix-manifest-')
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    return Path(path)

def conda_to_guix_package_mapping() -> Dict[str, str]:
    """Mapping of common conda package names to their Guix equivalents."""
    return {
        "python": "python",
        "python2": "python-2",
        "python3": "python",
        "numpy": "python-numpy",
        "scipy": "python-scipy",
        "pandas": "python-pandas",
        "matplotlib": "python-matplotlib",
        "tensorflow": "python-tensorflow",
        "pytorch": "python-pytorch",
        "r-base": "r",
        "r": "r",
        # Add more mappings as needed
    }


def convert_conda_to_guix_packages(conda_packages: List[str]) -> List[str]:
    """Convert conda package specifications to Guix package specifications."""
    mapping = conda_to_guix_package_mapping()
    guix_packages = []

    for package in conda_packages:
        # Remove version constraints
        package_name = package.split("=")[0].split("<")[0].split(">")[0].strip()

        # Map to Guix package name if in mapping
        if package_name in mapping:
            guix_packages.append(mapping[package_name])
        else:
            # Try to use a standard naming convention for Python packages
            if package_name.startswith("python-"):
                guix_packages.append(package_name)
            else:
                # Assume it's a Python package
                guix_packages.append(f"python-{package_name}")

    return guix_packages
