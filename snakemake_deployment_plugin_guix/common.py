"""Common utilities for the Guix deployment plugin."""

import os
import hashlib
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union, Any

# Configure logging
logger = logging.getLogger("snakemake.deployment.guix")

# Constants
DEFAULT_CHANNELS_CONTENT = """(list (channel
        (name 'guix)
        (url "https://git.savannah.gnu.org/git/guix.git")
        (branch "master")))
"""

DEFAULT_MANIFEST_TEMPLATE = """(specifications->manifest (list
{packages}
))
"""

def hash_string(s: str) -> str:
    """Generate a hash for a string."""
    return hashlib.md5(s.encode()).hexdigest()

def get_environment_hash(packages: List[str], name: Optional[str] = None) -> str:
    """Generate a unique hash for an environment."""
    env_string = ",".join(sorted(packages))
    if name:
        env_string = f"{name}:{env_string}"
    return hash_string(env_string)

def run_command(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command."""
    logger.debug(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check, capture_output=True, text=True)
    return result

def create_channels_file(channels_content: str, output_path: Path) -> Path:
    """Create a Guix channels file."""
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(channels_content)
    return output_path

def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure a directory exists and return its Path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def is_guix_available() -> bool:
    """Check if Guix is available in the system."""
    try:
        subprocess.run(
            ["guix", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
