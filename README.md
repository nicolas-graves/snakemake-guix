# Snakemake Deployment Plugin: GNU Guix

This plugin provides [GNU Guix](https://guix.gnu.org/) support for Snakemake workflows, allowing you to use Guix for software deployment instead of Conda. Guix offers reproducible environments with functional package management.

## Features

- Use Guix environments for software deployment in Snakemake workflows
- Convert Conda environment files to Guix manifests automatically
- Full integration with Snakemake's CLI and configuration system
- Support for isolated execution with Guix containers
- Compatible with Snakemake 8.0+ plugin system

## Installation

```bash
pip install snakemake-deployment-plugin-guix
```

Make sure you have GNU Guix installed on your system. Installation instructions can be found in the [Guix manual](https://guix.gnu.org/manual/en/html_node/Installation.html).

## Usage

### Basic Usage

Enable the Guix deployment method in your Snakemake workflow:

```bash
snakemake --deployment-method guix
```

### With Existing Conda Environment Files

You can use your existing Conda environment files with Guix:

```bash
snakemake --deployment-method guix --guix-auto-create-manifest
```

The plugin will attempt to convert Conda package specifications to Guix package specifications automatically.

### Using Custom Guix Manifests

You can provide your own Guix manifest file:

```bash
snakemake --deployment-method guix --guix-manifest-file path/to/manifest.scm
```

### Running in Containers

For better isolation, you can run your workflow in Guix containers:

```bash
snakemake --deployment-method guix --guix-container
```

### Using Time Machine for Reproducibility

By default, the plugin uses `guix time-machine` to ensure reproducible environments:

```bash
snakemake --deployment-method guix --guix-channels-file path/to/channels.scm
```

To disable time machine and use the current Guix version:

```bash
snakemake --deployment-method guix --guix-time-machine False
```

## Configuration

The plugin can be configured through Snakemake's CLI, configuration file, or profile:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--guix-channels-file` | Path to Guix channels file | Auto-generated |
| `--guix-manifest-file` | Path to an existing Guix manifest file | None |
| `--guix-container` | Run Guix with --container option | False |
| `--guix-gc-root-dir` | Directory for Guix garbage collection roots | None |
| `--guix-time-machine` | Use guix time-machine for reproducibility | True |
| `--guix-additional-args` | Additional arguments for guix shell | None |
| `--guix-auto-create-manifest` | Convert conda env files to Guix manifests | True |
| `--guix-manifest-template` | Path to a template manifest file | None |

## Example Workflow

Here's an example of a Snakemake workflow using Guix:

```python
# Snakefile
rule all:
    input:
        "results/plot.png"

rule analyze:
    input:
        "data/samples.csv"
    output:
        "results/analysis.txt"
    conda:
        "envs/analysis.yaml"  # Will be converted to Guix manifest
    shell:
        "python scripts/analyze.py {input} {output}"

rule plot:
    input:
        "results/analysis.txt"
    output:
        "results/plot.png"
    conda:
        "envs/visualization.yaml"  # Will be converted to Guix manifest
    shell:
        "python scripts/plot.py {input} {output}"
```

Run with:

```bash
snakemake --deployment-method guix
```

## Conda to Guix Translation

The plugin includes a basic translation layer from Conda to Guix packages. Common packages are automatically mapped to their Guix equivalents. For Python packages not in the mapping, the plugin tries to use a naming convention of `python-<package-name>`.

You can also create custom Guix manifests for more complex requirements.

## Limitations

- Not all Conda packages have direct equivalents in Guix
- Version constraints in Conda environment files are not enforced in Guix
- Some complex Conda environment features may not translate perfectly

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
