# Snakemake Guix OpenStack executor

The repository-relative commands below run from the `snakemake-guix` checkout
root, which contains the `openstack/` module and `.guix/modules/` channel
definitions.

This executor runs an allowlisted set of Snakemake jobs on one temporary
OpenStack worker for the whole invocation. It uses `guix-ssh` for Guix closure
transfer, staging, execution, and output retrieval. The worker is created only
when a remote job is submitted and is deleted during executor shutdown.

## Use from Guix

The Guix package is maintained in the `snakemake-guix` channel alongside its
`guix-ssh` dependency. Add that channel to `channels.scm`:

```scheme
(cons (channel
       (name 'snakemake-guix)
       (url "https://github.com/nicolas-graves/snakemake-guix"))
      %default-channels)
```

The channel currently has no Guix authentication introduction, so Guix warns
that it cannot authenticate channel commits. Channel authentication is
deferred.

Pull the channel, then run Snakemake in a shell containing the package:

```sh
guix pull --channels=channels.scm
guix shell python-snakemake-executor-plugin-guix-openstack -- \
  snakemake --executor guix-openstack --help
```

The package provides Snakemake, the executor, and its OpenStack SDK dependency.
Use the workflow profile below when submitting jobs.

```yaml
# profiles/ovh-b3-256/config.yaml
executor: guix-openstack
jobs: 1
guix-openstack-rules: [the_big_rule]
guix-openstack-flavor: b3-256
guix-openstack-image: guix-worker-2026-10-05
guix-openstack-max-hours: 6
guix-openstack-identity-file: ~/.ssh/id_guix_worker
software-deployment-method: [guix]
sdm-guix-profile-cache: .snakemake/guix/profiles
shared-fs-usage: none
```

Run `snakemake -n --profile profiles/ovh-b3-256` first and inspect the jobs
that would run. Use Snakemake's `--allowed-rules` as an additional DAG-level
guard when appropriate. This executor has its own required
`guix-openstack-rules` allowlist because the executor sees jobs after they have
been scheduled and a stale upstream job can otherwise incur cloud charges.

OpenStack credentials stay outside the profile. Use the usual `OS_*` variables
from an OpenStack `openrc`, an application credential, or an entry in
`clouds.yaml` selected with `guix-openstack-cloud`.

To turn a trusted OpenRC file into a JSON record (also valid YAML), run the
included parser. It loads the script in a child Bash process, so the OpenRC
password prompt still works, and writes the record with mode `0600` to the
project-local, Git-ignored `.secrets/` directory:

```sh
guix shell python -- python3 openstack/scripts/openrc_to_json.py \
  ~/.local/share/downloads/openrc.sh --output .secrets/openstack-credentials.json
```

The record contains plaintext credentials. Keep it out of version control and
remove it when it is no longer needed. The executor does not load this JSON
file; configure OpenStack credentials through the `OS_*` environment or
`clouds.yaml` as described above.

The worker image must contain Guix, Snakemake, the Guix software deployment
plugin, key-only root SSH, rsync, bash, coreutils, the host-key console service,
and the controller's Guix signing public key. The provided OS procedure installs
Snakemake and the Guix deployment plugin in the system profile. Remote jobs
source that profile before starting Snakemake.
Create a small OS definition that calls the exported procedure with the
controller's public keys:

```scheme
(use-modules (guix-openstack worker))

(guix-openstack-worker-os
 #:authorized-keys (list "ssh-ed25519 AAAA... controller")
 #:signing-keys (list "/path/to/controller-signing-key.pub"))
```

Save it as `worker-os.scm`, then build and publish a private, content-versioned
Glance image. The image remains available after each temporary worker is
deleted. Rebuilding the qcow2 produces a different image name and ID; update
the executor profile to the returned ID after validation.

```sh
image=$(guix system image \
  -L .guix/modules \
  --image-type=qcow2 --image-size=14G worker-os.scm)
guix shell python-snakemake-executor-plugin-guix-openstack -- \
  snakemake-guix-openstack-image ensure --file "$image" \
    --name-prefix guix-worker --region GRA11
```

The command prints the Glance image ID on stdout. Put that exact ID in
`guix-openstack-image`; keep the selected OpenStack region aligned with the
image's region (for example, `OS_REGION_NAME=GRA11`). The executor never
uploads an image during a workflow run.
The `ensure` command has fake-cloud test coverage; a live upload through this
command has not yet been verified.

See [`worker.scm`](../.guix/modules/guix-openstack/worker.scm) for the OS
procedure.

## SSH trust

The worker prints its Ed25519 host public key between marker lines on the
serial console. The executor pins that key and writes a per-run SSH config in
`$XDG_CACHE_HOME/snakemake-guix-openstack`. Add this line once at the top of
`~/.ssh/config` so `ssh`, `rsync`, and `guix copy` can use the same alias:

```text
Include ~/.cache/snakemake-guix-openstack/ssh_config
```

`guix copy` was checked against vpsdae: Guile-SSH honors `Include`,
`HostName`, `User`, and `IdentityFile`. Its `UserKnownHostsFile` lookup
uses the resolved host address, so the generated known-hosts file pins the
server IP. Strict host-key checking stays enabled; the plugin never accepts an
unknown key automatically.

## Reaper

Run `snakemake-guix-openstack-reap --dry-run` first on an always-on host with
OpenStack credentials. Run it periodically without `--dry-run` to delete
servers carrying `sgo=1` whose `sgo-expires` time has passed. It ignores every
other server. On a Guix System host, mcron can run it every ten minutes as a
dedicated account. Keep that account's `clouds.yaml` outside the Guix store,
readable only by the account, and verify it with `--dry-run` before enabling
deletion. For example, add this service extension to the host's existing
`services` list after providing the `sgo-reaper` account and OpenStack config:

```scheme
(use-modules (guix)
             (gnu services)
             (gnu services mcron)
             (snakemake-guix packages))

(simple-service
 'sgo-reaper-jobs
 mcron-service-type
 (list
  #~(job '(next-minute (range 0 60 10))
         (lambda ()
           (execl #$(file-append
                     python-snakemake-executor-plugin-guix-openstack
                     "/bin/snakemake-guix-openstack-reap")
                  "snakemake-guix-openstack-reap" "--cloud" "ovh"))
         "reap expired Guix OpenStack workers"
         #:user "sgo-reaper")))
```

The service account's `~/.config/openstack/clouds.yaml` supplies the `ovh`
entry; no secret belongs in the system configuration or job expression.

## Development

From the repository root, build the channel package with:

```sh
guix build -L .guix/modules -f guix.scm
```

The channel package builds both executors from this checkout. To confirm
Snakemake discovers the package-built executor, run:

```sh
guix shell -L .guix/modules \
  -f guix.scm -- snakemake --executor guix-openstack --help
```

Run the fake-cloud tests in a Guix shell with:

```sh
guix shell -L .guix/modules \
  python python-pytest python-openstacksdk \
  python-snakemake-interface-common \
  python-snakemake-interface-executor-plugins \
  python-snakemake-software-deployment-plugin-guix -- \
  env PYTHONPATH=openstack/src:executor/src:deployment/src \
  pytest -q openstack/tests
```
