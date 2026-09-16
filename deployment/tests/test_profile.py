"""Tests for the snakemake profile configuration."""

import tempfile
from pathlib import Path

from snakemake.profiles import ProfileConfigFileParser


def test_default_profile_config_yaml():
    """config.yaml format for snakemake profile parses correctly."""
    config_content = "cores: all\nsoftware-deployment-method:\n  - guix\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(config_content)

        parser = ProfileConfigFileParser()
        with open(config_file) as f:
            result = parser.parse(f)

    assert result["cores"] == "all"
    assert result["software-deployment-method"] == ["guix"]
