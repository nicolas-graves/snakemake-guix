# Snakemake Guix channel

This repository contains the Guix software deployment plugin, the SSH executor,
and a channel package for the OpenStack executor:

- [`deployment/`](deployment/) — `snakemake-software-deployment-plugin-guix`,
  which realizes immutable Guix environments and exposes them through a public
  executor-facing contract.
- [`executor/`](executor/) — `snakemake-executor-plugin-guix-ssh`, which copies
  Guix closures and job files to independent SSH workers while keeping the DAG
  and persistence metadata on the local controller.
- [`snakemake-executor-plugin-guix-openstack`](https://github.com/nicolas-graves/snakemake-executor-plugin-guix-openstack) — a separately maintained executor that provisions temporary OpenStack workers and uses guix-ssh for job execution.

The channel package `snakemake-guix-remote-execution` installs the patched
Snakemake build, the Guix deployment plugin, and both executors together.
See each package README for its API, configuration, and tests.
