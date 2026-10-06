# Snakemake Guix SSH executor plugin

This package executes jobs on independent SSH workers using immutable Guix
profiles supplied by `snakemake-software-deployment-plugin-guix`.

```yaml
executor: guix-ssh
jobs: 1
guix-ssh-hosts:
  - worker.example:22:/var/tmp/snakemake-guix
guix-ssh-remove-failed: false
guix-ssh-remote-profile: /opt/profiles/dev
software-deployment-method:
  - guix
sdm-guix-profile-cache: .snakemake/guix/profiles
shared-fs-usage: none
```

The controller transfers closures with `guix copy`, stages files through
`rsync`, launches detached process groups, polls durable status files, and
publishes outputs locally only after successful transfer. Workers require
Guix, SSH, and rsync; the plugin never bootstraps packages through PyPI.

`identity-file` and `ssh-args` configure OpenSSH and rsync. `guix copy` is a
separate Guile-SSH client and currently receives only the host name, so those
executor settings do not configure its identity or port. Put the host alias,
identity, and non-default port in `~/.ssh/config` for `guix copy` to use them.
Set `guix-ssh-remote-profile` when the worker's Snakemake plugins live in a
non-default Guix profile. The executor sources that profile's
`etc/profile` before starting the remote Snakemake process. It also starts the
child workflow in the staged job directory, so relative includes, config files,
and inputs resolve on the worker.

The controller's `--directory` selects the working directory used as the
transfer root. Absolute input and output paths are accepted only when they
resolve inside that root. The executor stages workflow sources and declared
inputs, and retrieves declared outputs, logs, and benchmarks. A preparation
rule should declare a small archive and manifest, or a receipt created only
after it verifies an external artifact. Large undeclared intermediates stay
on the worker for the duration of that job. A separate remote job does not
inherit them.

Before submission, the executor checks the worker's Guix and rsync commands
and writable work directory. The host alias in SSH configuration must specify
the port and identity used by the executor because `guix copy` resolves that
alias independently. The transferred Guix closure belongs to the outer job;
additional environments requested by nested Snakemake rules must be prepared
by the calling workflow. Each remote job has a `sources.json` inventory of
staged paths and SHA-256 hashes for diagnosis.
