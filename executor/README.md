# Snakemake Guix SSH executor plugin

This package executes jobs on independent SSH workers using immutable Guix
profiles supplied by `snakemake-software-deployment-plugin-guix`.

```yaml
executor: guix-ssh
jobs: 1
guix-ssh-hosts:
  - worker.example:22:/var/tmp/snakemake-guix
guix-ssh-remove-failed: false
software-deployment-method:
  - guix
sdm-guix-profile-cache: .snakemake/guix/profiles
shared-fs-usage: none
```

The controller transfers closures with `guix copy`, stages files through
`rsync`, launches detached process groups, polls durable status files, and
publishes outputs locally only after successful transfer. Workers require
Guix, SSH, and rsync; the plugin never bootstraps packages through PyPI.
