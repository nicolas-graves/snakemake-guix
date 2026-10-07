# snakemake-contracts-wrapper

Snakemake rule wrapper that expands named `input`, `output`, `log`, and
`params` objects into script CLI arguments.

## Motivation

Snakemake rules commonly repeat the same wiring: `--flag {input.foo}
--other-flag {output.bar}` for every rule that calls a script. This package
removes that repetition. It reads the named objects already present on a
rule and turns them into ordinary command-line arguments, so the script
itself stays unaware of Snakemake and only ever sees CLI flags.

This package is the wrapper layer for
[`snakemake-contracts`](https://pypi.org/project/snakemake-contracts/), but
it does not depend on it and can be used on its own.

## Usage

As a Python helper:

```python
from snakemake_contracts_wrapper import build_argv, render_shell

argv = build_argv(
    script="scripts/train.py",
    input={"data": "data.csv"},
    output={"model": "model.pkl"},
    params={"epochs": 10},
)
# ["scripts/train.py", "--data", "data.csv", "--output-model", "model.pkl", "--epochs", "10"]

render_shell(
    script="scripts/train.py",
    input={"data": "data.csv"},
    output={"model": "model.pkl"},
)
# "scripts/train.py --data data.csv --output-model model.pkl"
```

As a Snakemake wrapper, point a rule's `wrapper:` directive at
`snakemake_contracts_wrapper.WRAPPER_DIR`:

```python
from snakemake_contracts_wrapper import WRAPPER_DIR

rule train:
    input:
        script="scripts/train.py",
        data="data.csv",
    output:
        model="model.pkl",
    params:
        epochs=10,
    wrapper:
        f"file:{WRAPPER_DIR}"
```

The wrapper requires a named input called `script`, which is excluded from
the generated argument list by default.

## Log argument

The Snakemake wrapper does not pass `--log` unless the rule declares a
`log:` output itself, or the workflow config explicitly opts in with
`scripts_accept_log_arg: true` and a `cache` path is configured. When both
are set and no `log:` is declared, a default log path is synthesized under
`{cache}/logs/{script_stem}.log`. This opt-in is required because a
`cache` config alone does not prove that every wrapped script accepts a
`--log` CLI argument.

## Surface

- `build_argv(command, script=None, input=None, output=None, log=None, params=None, exclude_input=("script",), output_prefix="output-")`
- `render_shell(command, script=None, input=None, output=None, log=None, params=None, exclude_input=("script",), output_prefix="output-")`
- `namespace_flag(namespace, name, output_prefix="output-")`
- `snake_to_kebab(name)`
- `WRAPPER_DIR`
