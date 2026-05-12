# Guix Snakemake Software Deployment Plugin

This plugin provides [Guix](https://guix.gnu.org/) support for Snakemake workflows, allowing you to use Guix for software deployment. Guix offers fully reproducible environments through functional package management. This combination is the best of both worlds: Guix is best-in-class for reproducibility and transparency; Snakemake is best-in-class for convenience and usability.

Software deployment plugins have not formally landed in Snakemake, but I plan to continue and update this repository along development progress in the `feat/software-deployment-plugins` branch.  All commits and patches are recorded in `.guix/modules/snakemake-guix.scm`.

Minimal guix knowledge is expected, but not much more than what you can find in this video https://10years.guix.gnu.org/video/guix-as-a-tool-for-computational-science/

This plugin currently only exists on Guix, which is assumed to be installed on your system. Once you have this channel pulled, install the `python-snakemake-software-deployment-plugin-guix` just like you would install any guix package.

## Features

- Use Guix environments for software deployment in Snakemake workflows
- Specify environments via manifest files or package lists per rule
- Support for isolated execution with Guix containers (`--container`) out of the box
- `guix time-machine`-like reproducibility via with pinned channels
- Compatible with Snakemake 9.17+ plugin system (`--sdm guix`)

## Usage

### Activating the Plugin

Enable the Guix deployment method when running Snakemake:

```bash
snakemake --sdm guix
```

### Specifying Environments in Rules

In your `Snakefile`, use the `software:` directive with the `guix()` factory:

```python
rule all:
    input:
        "results/plot.png"

rule analyze:
    input:
        "data/samples.csv"
    output:
        "results/analysis.txt"
    software:
        guix(manifest_file="envs/analysis.scm")
    shell:
        "python scripts/analyze.py {input} {output}"

rule plot:
    input:
        "results/analysis.txt"
    output:
        "results/plot.png"
    software:
        guix(packages=["python", "python-matplotlib"])
    shell:
        "python scripts/plot.py {input} {output}"
```

Run with:

```bash
snakemake --sdm guix
```

### Using a Guix Manifest File

Create a `manifest.scm` file:

```scheme
(specifications->manifest
  (list "python"
        "python-numpy"
        "python-pandas"))
```

Reference it in your rule:

```python
rule my_rule:
    software:
        guix(manifest_file="manifest.scm")
    shell:
        "python my_script.py"
```

### Specifying Packages Directly

For simple cases, list packages inline:

```python
rule my_rule:
    software:
        guix(packages=["python", "r", "samtools"])
    shell:
        "..."
```

### Running in Containers

For better isolation, enable container mode:

```bash
snakemake --sdm guix --sdm-guix-container
```

### Using Time Machine for Reproducibility

By default, the plugin uses `guix time-machine` for reproducibility. Provide a channels file:

```bash
snakemake --sdm guix --sdm-guix-channels-file channels.scm
```

To disable time machine and use the current Guix version:

```bash
snakemake --sdm guix --sdm-guix-time-machine false
```

## Configuration

Plugin-specific settings are passed via `--sdm-guix-<option>`:

| CLI option | Description | Default |
|---|---|---|
| `--sdm-guix-channels-file` | Path to a Guix channels file for `time-machine` | None |
| `--sdm-guix-container` | Run `guix shell` with `--container` for isolation | False |
| `--sdm-guix-time-machine` | Use `guix time-machine` for reproducibility | True |
| `--sdm-guix-additional-args` | Extra arguments forwarded to `guix shell` | None |

## Composing Environments

Guix environments can be composed with other plugins using the `within` keyword. For example, to run a Guix environment inside a container:

```python
rule my_rule:
    software:
        guix(manifest_file="manifest.scm", within=container("docker://ubuntu:22.04"))
    shell:
        "..."
```

## Channels File

A channels file pins the exact Guix revision used for all environments, enabling bit-for-bit reproducibility. Generate one from your current Guix installation:

```bash
guix describe -f channels > channels.scm
```

Then pass it to Snakemake:

```bash
snakemake --sdm guix --sdm-guix-channels-file channels.scm
```

## Examples

The `examples/` directory contains a minimal workflow that captures GNU `hello` output, exercising both ways to specify an environment:

```bash
cd examples
snakemake --sdm guix --cores 1
```

This runs two rules:
- `greet_packages` — environment declared inline with `packages=["hello"]`
- `greet_manifest` — environment declared via `manifest.scm`

Both produce a file under `results/` containing the greeting. If both succeed, the plugin is wired up correctly end-to-end.

## Limitations

- When using `packages=` directly, package existence is not validated until the job runs.
- Without a channels file and `time-machine`, environment reproducibility depends on your local Guix installation.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GPL3+ License — see the LICENSE file for details.
