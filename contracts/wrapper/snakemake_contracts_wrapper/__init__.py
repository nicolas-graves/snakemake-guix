from pathlib import Path
from .command import build_argv, namespace_flag, render_shell, snake_to_kebab

WRAPPER_DIR = Path(__file__).parent / "snakemake_wrapper"

__all__ = [
    "WRAPPER_DIR",
    "build_argv",
    "namespace_flag",
    "render_shell",
    "snake_to_kebab",
]
