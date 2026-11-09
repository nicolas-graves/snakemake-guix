# snakemake-contracts

> The source lives in the [snakemake-guix repository](https://github.com/nicolas-graves/snakemake-guix/tree/master/contracts) under `contracts/`. The old standalone `snakemake-contracts` repository stopped at 0.5.0 and is no longer maintained.

A small helper library for Snakemake workflows that use
`provides` / `requires`-style contracts between modules.

## Motivation

A lot of hidden complexities can stem from splitting a snakemake-based
project into multiple independent submodules: how do you handle
changing independent submodule outputs ?

This package exists for workflows that are split into many Snakemake submodules
and need a disciplined way to connect them.

In practice, the goal is not just to reuse code. It is to make module boundaries
explicit and stable:

- each module should declare what it consumes and what it exposes;
- each module should keep its own outputs defined in one place;
- the root workflow should not become the only place that knows where every
  generated file lives.

That matters once a workflow grows beyond a single Snakefile. At that point the
top-level repo tends to accumulate accidental knowledge about other modules:
hard-coded file paths, config overrides for foreign outputs, and ad hoc
assumptions about directory layouts. Those shortcuts make the graph harder to
reason about and much easier to break when a module changes shape.

The contract model used here is intentionally close to the `requires` /
`provides` style found in systems like nREPL middleware chains: producers
declare the interface they offer, consumers ask for a named capability, and the
resolver stays small and mechanical. The point is to treat the dependency
boundary as a contract, not as an implicit convention spread across the whole
repository.

Using `provides.yaml` as the source of truth also has a practical benefit: the
module itself remains the authoritative owner of its exported outputs. The repo
root can still orchestrate modules, but it does not need to mirror every output
name or path in a central registry. That reduces duplication and keeps the
dependency metadata next to the module that owns it.

## Scope

- resolve declared outputs by logical key
- locate module output directories
- validate `provides.yaml` files
- optionally compare declared contracts against a repo layout

## Library Usage

The core API lives in `snakemake_contracts.contracts` and expects a repo layout
like:

```text
repo/
  modules/
    my_module/
      Snakefile
      provides.yaml
      out/
```

Typical usage:

```python
from snakemake_contracts.contracts import load_provides, provides, validate_repo

mapping = load_provides("my_module", repo_root="/path/to/repo")
report = provides("my_module", "report", repo_root="/path/to/repo")
problems = validate_repo("/path/to/repo")
```

`provides.yaml` is the source of truth for logical output names, and `provides()`
resolves them relative to the module's `out/` directory.

### Module context

Module Snakefiles can use `module_context()` to share their standalone setup and
contract resolution:

```python
from snakemake_contracts.contracts import module_context

ctx = module_context(workflow, config)

OUTDIR = ctx.out_dir
DATADIR = ctx.data_dir
CACHEDIR = ctx.cache_dir
out = ctx.out
require = ctx.require
```

The default `required-config` mode asks Snakemake to load the module-local
`config.yaml` when `config` is empty. A missing file is therefore reported by
Snakemake, and each directory property requires its corresponding `out`,
`data`, or `cache` config key. Properties are lazy, so a module that only reads
`ctx.cache_dir` does not need the other directory keys.

Modules designed to work without a config file can opt into absolute,
module-local defaults:

```python
ctx = module_context(workflow, config, standalone="local-defaults")

# Defaults to <module>/out, <module>/data, and <module>/.cache.
OUTDIR = ctx.out_dir
```

In `local-defaults` mode an existing module-local `config.yaml` is loaded, but
a missing one is allowed. Configured directory values take precedence over the
defaults. Both modes accept a different module-local filename through the
`configfile=` argument.

When a root workflow supplies a nonempty inherited `config`, the module config
file is not loaded in either mode. Dependencies retain the existing truthy
override convention:

```python
# Uses config["reads"] when truthy, otherwise resolves modules/qc/provides.yaml.
reads = ctx.require("qc", "reads")
```

`ctx.out()` lazily reads the current module's `provides.yaml`; constructing a
context does not require that file. Wrapper discovery remains the responsibility
of the separate `snakemake_contracts_wrapper` package.

`ctx.downloads` is the module's `downloads.yaml`, read on first use.
`ctx.public_http(workflow, policy=...)` and `ctx.public_browser(workflow,
policy=...)` return the settings of a storage for anonymous public responses,
to unpack in a storage directive:

```python
storage public_alpha:
    **ctx.public_http(workflow, policy="checked")

storage public_alpha_browser:
    **ctx.public_browser(workflow, policy="immutable")
```

Both share the `cached-http` cache (`SNAKEMAKE_STORAGE_CACHED_HTTP_CACHE`, else
the provider setting). `policy` applies while
`SNAKEMAKE_STORAGE_CACHED_HTTP_POLICY` is unset or `auto`. `public_http` also
takes `headers=` and `check_remote=False` (an immutable source, no remote
checks); `public_browser` serves the `browser: true` entries of
`ctx.downloads` (`lien_primaire`, `lien_secondaire`, `format`).

## Python Exports

A module makes some of its scripts importable by listing them under the
reserved `python:` key of its `provides.yaml` (module name -> path relative to
the module directory):

```yaml
python:
  dimension_lookups: scripts/dimension_lookups.py
```

A consumer declares the file as its rule's `python` input; the contracts
wrapper puts the file's directory on `PYTHONPATH` inside the job (not on the
command line), and the script does a plain `import dimension_lookups`:

```python
rule x:
    input:
        script=SCRIPTS / "x.py",
        python=[ctx.python("_nomenclatures", "dimension_lookups")],
    wrapper: f"file:{_CONTRACTS_WRAPPER}"
```

A shell rule prefixes its command with `PYTHONPATH={params.pythonpath:q}`,
`pythonpath=ctx.pythonpath(*exports)`. The `snakemake_contracts.pytest_exports`
plugin appends every module's exported directories to `sys.path` in tests.

## Publication Metrics Plugin

Installing the package registers a pytest plugin
(`snakemake_contracts.publication_metrics`). Every `publication_metrics.json`
that pytest's collection reaches becomes one test per metric: an
`{"sql": ...}` entry is checked for its shape only (the module tests its
expression), an `{"aggregate": "MAX"|"MIN"|"SUM"|"AVG"|"COUNT", "column": ...}`
entry is run in DuckDB over selected, grouped, null, signed and repeated rows.
DuckDB is needed only by those aggregate tests.

## Wrapper Layer

The repository also includes a separate package, `snakemake_contracts_wrapper`
(in `wrapper/`), for Snakemake-facing command construction: it turns the named
`input`/`output`/`log`/`params` objects on a rule into script CLI arguments.
See [`wrapper/README.md`](wrapper/README.md) for usage and its surface.

## Current Surface

- `load_provides(module, repo_root=None)`
- `provides(module, key, repo_root=None)`
- `out_dir(module, repo_root=None)`
- `module_context(workflow, config, configfile="config.yaml", standalone="required-config")`
- `ModuleContext`
- `list_modules(repo_root=None)`
- `mangle(name)`
- `validate_repo(repo_root=None)`

## Tests

- `tests/test_contracts.py` exercises the library directly against a temporary
  repo layout.
- `tests/test_wrapper.py` covers the wrapper command helpers (see
  [`wrapper/README.md`](wrapper/README.md) for the wrapper package itself).

## Status

This is a small utility package, not a general Snakemake extension. It is meant
to support workflows that already use `provides.yaml`-style contracts and want a
single place to validate and resolve them.
