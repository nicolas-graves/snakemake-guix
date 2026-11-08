from pathlib import Path
from .command import build_argv, namespace_flag, render_shell, snake_to_kebab

WRAPPER_DIR = Path(__file__).parent / "snakemake_wrapper"
# The value of a rule's ``wrapper:`` directive.
WRAPPER = f"file:{WRAPPER_DIR}"

__all__ = [
    "WRAPPER",
    "WRAPPER_DIR",
    "build_argv",
    "namespace_flag",
    "render_shell",
    "snake_to_kebab",
]
