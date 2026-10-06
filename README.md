# Snakemake Guix channel

This repository contains the Guix software deployment plugin and two executors:

- [`deployment/`](deployment/) — `snakemake-software-deployment-plugin-guix`,
  which realizes immutable Guix environments and exposes them through a public
  executor-facing contract.
- [`executor/`](executor/) — `snakemake-executor-plugin-guix-ssh`, which copies
  Guix closures and job files to independent SSH workers while keeping the DAG
  and persistence metadata on the local controller.
- [`openstack/`](openstack/) — `snakemake-executor-plugin-guix-openstack`,
  which provisions temporary OpenStack workers and uses guix-ssh for job execution.

The channel package `snakemake-guix-remote-execution` installs the patched
Snakemake build, the Guix deployment plugin, and both executors together.
See each package README for its API, configuration, and tests.
