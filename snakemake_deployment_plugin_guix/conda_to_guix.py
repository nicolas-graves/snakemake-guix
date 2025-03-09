"""Utilities for translating Conda environment specifications to Guix manifests."""

import os
import yaml
import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any, Union

from .common import logger

# Common package name translations from Conda to Guix
# This is a starting point and would need to be expanded
CONDA_TO_GUIX_MAPPING = {
    # Programming languages
    "python": "python",
    "python2": "python-2",
    "python3": "python",
    "r-base": "r",
    "r": "r",
    "perl": "perl",
    "ruby": "ruby",
    "openjdk": "openjdk",
    "java": "openjdk",
    "nodejs": "node",
    "go": "go",
    "rust": "rust",

    # Bioinformatics
    "samtools": "samtools",
    "bedtools": "bedtools",
    "bowtie2": "bowtie",
    "bwa": "bwa",
    "fastqc": "fastqc",
    "hisat2": "hisat2",
    "snakemake": "snakemake",

    # Scientific packages
    "numpy": "python-numpy",
    "scipy": "python-scipy",
    "pandas": "python-pandas",
    "matplotlib": "python-matplotlib",
    "scikit-learn": "python-scikit-learn",
    "tensorflow": "python-tensorflow",
    "pytorch": "python-pytorch",

    # System tools
    "curl": "curl",
    "wget": "wget",
    "git": "git",
    "make": "make",
    "gcc": "gcc-toolchain",
    "cmake": "cmake",
    "autoconf": "autoconf",
    "automake": "automake",
    "pkg-config": "pkg-config",
    "hdf5": "hdf5",
    "zlib": "zlib",
    "bzip2": "bzip2",
    "xz": "xz",
    "openssl": "openssl",
    "sqlite": "sqlite",
}

def parse_conda_environment_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Parse a conda environment.yml file."""
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Conda environment file not found: {file_path}")

    with open(file_path) as f:
        if file_path.suffix.lower() in ['.yaml', '.yml']:
            env_dict = yaml.safe_load(f)
        elif file_path.suffix.lower() == '.json':
            env_dict = json.load(f)
        else:
            raise ValueError(f"Unsupported conda environment file format: {file_path}")

    return env_dict

def extract_package_name(spec: str) -> str:
    """Extract the package name from a conda package specification."""
    # Remove version specifications, build string, etc.
    match = re.match(r'^([a-zA-Z0-9_.-]+)', spec.strip())
    if match:
        return match.group(1).lower()
    return spec

def translate_conda_dependencies(dependencies: List[str]) -> List[str]:
    """Translate conda dependencies to Guix package specifications."""
    guix_packages = []

    for dep in dependencies:
        if isinstance(dep, dict):
            # Handle pip dependencies or other special cases
            if 'pip' in dep and isinstance(dep['pip'], list):
                for pip_dep in dep['pip']:
                    pkg_name = extract_package_name(pip_dep)
                    guix_name = f"python-{pkg_name.replace('_', '-')}"
                    guix_packages.append(guix_name)
            continue

        pkg_name = extract_package_name(dep)

        # Look up the package in our mapping
        if pkg_name in CONDA_TO_GUIX_MAPPING:
            guix_packages.append(CONDA_TO_GUIX_MAPPING[pkg_name])
        elif pkg_name.startswith('r-'):
            # R packages: try to preserve the name
            guix_packages.append(f"r-{pkg_name[2:]}")
        elif pkg_name.startswith('bioconductor-'):
            # BioConductor packages
            guix_packages.append(f"r-{pkg_name[13:]}")
        elif pkg_name.startswith('py') and len(pkg_name) > 2:
            # Python packages starting with 'py'
            guix_packages.append(f"python-{pkg_name[2:]}")
        else:
            # For other packages, try prefixing with python- if it seems like a Python package
            guix_packages.append(f"python-{pkg_name.replace('_', '-')}")
            logger.warning(
                f"No direct Guix mapping for Conda package '{pkg_name}'. "
                f"Using 'python-{pkg_name.replace('_', '-')}' as a guess."
            )

    return guix_packages

def conda_env_to_guix_packages(env_file: Union[str, Path]) -> List[str]:
    """Convert a conda environment file to a list of Guix packages."""
    env_dict = parse_conda_environment_file(env_file)

    dependencies = env_dict.get('dependencies', [])
    if not dependencies:
        logger.warning(f"No dependencies found in conda environment file: {env_file}")
        return []

    # Extract and translate package names
    guix_packages = translate_conda_dependencies(dependencies)

    # Add Python by default if not already present
    if 'python' not in guix_packages:
        guix_packages.append('python')

    return guix_packages

def packages_to_guix_manifest(packages: List[str]) -> str:
    """Convert a list of package names to a Guix manifest content."""
    package_strings = [f'  "{pkg}"' for pkg in packages]
    packages_str = "\n".join(package_strings)

    manifest_content = f"""(specifications->manifest (list
{packages_str}
))
"""
    return manifest_content
