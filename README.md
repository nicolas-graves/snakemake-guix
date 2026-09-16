# Snakemake Guix channel

This repository contains two independent Snakemake plugin packages and the
Guix channel that composes them:

- [`deployment/`](deployment/) — `snakemake-software-deployment-plugin-guix`,
  which realizes immutable Guix environments and exposes them through a public
  executor-facing contract.
- [`executor/`](executor/) — `snakemake-executor-plugin-guix-ssh`, which copies
  Guix closures and job files to independent SSH workers while keeping the DAG
  and persistence metadata on the local controller.

The channel package `snakemake-guix-remote-execution` installs the patched
Snakemake build and both plugins together. See each package README for its API,
configuration, and tests.
