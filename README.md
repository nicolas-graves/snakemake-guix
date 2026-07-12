# Guix Snakemake Software Deployment Plugin

This plugin provides [Guix](https://guix.gnu.org/) support for Snakemake workflows, allowing you to use Guix for fully reproducible environments during software deployment.  This combination tries to bring the best of both worlds: Guix is best-in-class for reproducibility and transparency; Snakemake is best-in-class for convenience and usability.

Minimal Guix knowledge is expected, but not much more than what you can find in [this video](https://10years.guix.gnu.org/video/guix-as-a-tool-for-computational-science/)

Software deployment plugins have not formally landed in Snakemake, but I plan to continue and update this repository along development progress in the [feat/software-deployment-plugins](https://github.com/snakemake/snakemake/tree/feat/software-deployment-plugins) branch.  All commits and patches are recorded in [.guix/modules/snakemake-guix/packages.scm](./.guix/modules/snakemake-guix/packages.scm).

This plugin currently only exists on Guix, which is assumed to be installed on your system. Once you have this channel pulled, install the `python-snakemake-software-deployment-plugin-guix` just like you would install any guix package.

## Features

- Use Guix environments for software deployment in Snakemake workflows
- Specify environments via one or more manifest files or package lists per rule
- Support for isolated execution with Guix containers (`--container`) out of the box
- `guix time-machine`-like reproducibility via pinned channels, or a lightweight `--url`/`--commit`/`--branch` pin
- Compatible with Snakemake 9.17+ plugin system (`--sdm guix`)

## Usage

### Activating the Plugin

Enable the Guix deployment method when running Snakemake:

```bash
snakemake --sdm guix
```

### Specifying Environments with Packages

In your `Snakefile`, use the `software:` directive with the `guix()` factory:

```make
rule all:
    input:
        "results/from_packages.txt",


rule greet_packages:
    """Specify the environment inline as a package list."""
    output: "results/from_packages.txt"
    software:
        guix(packages=["hello"])
    shell:
        "hello > {output}"

```

### Specifying Environments Using Guix Manifest Files

Create a `manifest.scm` file:

```scheme
(specifications->manifest
  (list "python"
        "python-numpy"
        "python-pandas"))
```

In your `Snakefile`, use the `software:` directive with the `guix()` factory:

```make
rule all:
    input:
        "results/from_manifest.txt",

rule greet_manifest:
    """Specify the environment via a manifest file list."""
    output: "results/from_manifest.txt"
    software:
        guix(manifest_files=["manifest.scm"])
    shell:
        "hello > {output}"
```

To combine multiple manifest files, pass them all in `manifest_files`:

```python
software:
    guix(
        manifest_files=["manifest-base.scm", "manifest-extra.scm"],
        packages=["hello"],
    )
```

`manifest_file=` is still accepted for compatibility, but it is deprecated.

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

Alternatively, pin a single channel by commit or branch without maintaining a
channels file:

```bash
snakemake --sdm guix --sdm-guix-commit <commit>
```

## Configuration

Plugin-specific settings are passed via `--sdm-guix-<option>`:

| CLI option | Description | Default |
|---|---|---|
| `--sdm-guix-channels-file` | Path to a Guix channels file for `time-machine`; overrides any per-rule `channels_file=` | None |
| `--sdm-guix-url` | Git repository URL for `time-machine`; overrides any per-rule `url=` | None |
| `--sdm-guix-commit` | Commit to use with `time-machine`; overrides any per-rule `commit=` | None |
| `--sdm-guix-branch` | Branch tip to use with `time-machine`; overrides any per-rule `branch=` | None |
| `--sdm-guix-container` | Run `guix shell` with `--container` for isolation | False |
| `--sdm-guix-time-machine` | Use `guix time-machine` for reproducibility | True |
| `--sdm-guix-additional-args` | Extra arguments forwarded to `guix shell` | None |

## Composing Environments

Guix environments can be composed with other plugins using the `within` keyword. For example, to run a Guix environment inside a container:

```python
rule my_rule:
    software:
        guix(manifest_files=["manifest.scm"], within=container("docker://ubuntu:22.04"))
    shell:
        "..."
```

## Channels File

A channels file pins the exact Guix revision used for an environment, enabling bit-for-bit reproducibility. Generate one from your current Guix installation:

```bash
guix describe -f channels > channels.scm
```

Then pass it to Snakemake to pin every rule to it:

```bash
snakemake --sdm guix --sdm-guix-channels-file channels.scm
```

It can also be set per-rule, directly in the `guix()` call:

```python
rule my_rule:
    software:
        guix(packages=["hello"], channels_file="channels.scm")
    shell:
        "..."
```

If `--sdm-guix-channels-file` is passed on the command line, it overrides any
per-rule `channels_file=` for every rule — the CLI setting is meant as a global
override for reproducing a whole workflow against one fixed revision. When the
CLI flag is absent, each rule's own `channels_file=` (if any) is used.

## Pinning by URL/Commit/Branch

For a lighter-weight pin than a full channels file, `guix time-machine` also
accepts `--url`, `--commit`, and `--branch` directly, which pin a single
channel (by default, the `guix` channel itself) without a `channels.scm`.
This can be set per-rule:

```python
rule my_rule:
    software:
        guix(packages=["hello"], commit="abc123...")
    shell:
        "..."
```

`url=`, `commit=`, and `branch=` can be combined, e.g. to pin a fork at a
given branch:

```python
guix(packages=["hello"], url="https://example.org/guix.git", branch="devel")
```

Unlike `channels_file`, each of `--sdm-guix-url` / `--sdm-guix-commit` /
`--sdm-guix-branch` independently overrides only its own per-rule
counterpart — e.g. a global `--sdm-guix-branch` combines with a rule's own
`commit=` unless that rule also sets its own `branch=`.

`channels_file` and `url`/`commit`/`branch` are mutually exclusive pinning
mechanisms — combining them (whether both are set on the same rule, or one is
set globally via `--sdm-guix-*` while a rule sets the other) raises an error,
matching `guix time-machine`'s own rejection of combining `-C` with
`--url`/`--commit`/`--branch`.

## Examples

The `examples/` directory contains a minimal workflow that captures GNU `hello` output, exercising both ways to specify an environment:

```bash
cd examples
snakemake --sdm guix --cores 1
```

This runs two rules:
- `greet_packages` — environment declared inline with `packages=["hello"]`
- `greet_manifest` — environment declared via `manifest_files=["manifest.scm"]`

Both produce a file under `results/` containing the greeting. If both succeed, the plugin is wired up correctly end-to-end.

## Limitations

- When using `packages=` directly, package existence is not validated until the job runs.
- When using `manifest_file=`, the new `manifest_files=` argument is preferred.
- Without a channels file and `time-machine`, environment reproducibility depends on your local Guix installation.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GPL3+ License — see the LICENSE file for details.
