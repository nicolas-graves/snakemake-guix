# Plan: snakemake-executor-plugin-guix-openstack

Status: 0.2.0 plugin release and sibling-channel package published, 2026-10-06.
Part 1 is implemented in the
local `snakemake-guix` checkout, including the source-staging compatibility
fix found during a live run; its executor suite passes (31 tests). This
repository has the executor, worker OS procedure, reaper, and fake-cloud tests
(34 pass). Acquisition cleanup is failure-tested through create timeout, boot
wait, server lookup, console access, SSH startup, and Ctrl-C. Connection-close
errors are logged without masking the original acquisition or manual-delete
error. A tiny multi-file
workflow passed on vpsdae through the static guix-ssh executor, including a
Guix environment, config/module/script/input
staging, output retrieval, and log retrieval. Guile-SSH's included SSH config
was also checked against vpsdae; the known-hosts entry must use the resolved
address. A local qcow2 worker image build and QEMU boot also succeeded. After
fixing the generated host-key program's missing textual-port import, it printed
the complete Ed25519 marker block; `ssh-keyscan` returned the same key. An
authenticated SSH check found that Snakemake could not see the Guix deployment
plugin in the system profile; the executor prefix now adds the profile's Python
site-packages to `PYTHONPATH`, and the worker accepted
`--software-deployment-method guix --help`. An authenticated local QEMU smoke
run then completed a toy Snakemake rule with `software: guix(packages=["coreutils"])`
and produced its expected output. `guix copy` also transferred the OpenStack
SDK closure to the worker over the pinned SSH connection, and the remote store
path was confirmed present. The current wheel and source archive build under
`guix shell`; their contents and the executor/reaper entry points were checked,
and Snakemake lists the plugin settings. The guest logs an early init Guile
segfault under both QEMU TCG and KVM, then continues to the login prompt and
starts sshd. The identical fault signature was described as a normal Guix boot
message in a [Guix help thread](https://www.mail-archive.com/help-guix@gnu.org/msg21757.html);
the OVH cloud boot remains unverified. No `OS_*` credentials are loaded in
this environment, and no OpenStack cloud config or OpenStack CLI is available,
so the OVH API spike is outstanding. A downloaded OpenRC file is available
outside the repository; it prompts for the password when sourced.
`scripts/openrc_to_json.py` can export its `OS_*` variables to a mode-0600 JSON
record. The downloaded OpenRC was parsed into the local, Git-ignored
`.secrets/openstack-credentials.json`; it is valid JSON containing 9 `OS_*`
fields and has mode 0600. SOPS remains deferred. Image
upload, the b3-8 end-to-end runs, and the production profile also remain
outstanding. This root checkout now has a
signed initial commit and signed
`snakemake-executor-plugin-guix-openstack-0.2.0` tag. A clean detached checkout
builds the package and passes all 34 tests when given the sibling Guix channel
path. Its `origin` points at the GitHub URL in the package definition, SSH
authentication works, and its branch and 0.2.0 tag are published. The sibling
`snakemake-guix` branch and guix-ssh 0.2.0 tag are also published. Neither
Python distribution is published on PyPI; the project currently targets the
Guix channel workflow, as requested. Both Guix channels lack authentication
introductions; the user deferred OpenPGP channel authentication.

The user deferred the live OVH steps. The OpenStack and SSH executor packages
now propagate Python, so a Guix shell smoke check shows Snakemake discovering
both plugins and listing all OpenStack settings.

The Guix package definitions now use filtered `local-file` snapshots from the
plugin and sibling channel checkouts, avoiding the self-referential Git source
hashes and bootstrap tags. On 2026-10-06, this command successfully built both
package derivations:

```sh
guix build -L .guix/modules -L ../snakemake-guix/.guix/modules -f guix.scm
```

Related repositories:

- `~/projects/src/snakemake-guix`: provides `snakemake-executor-plugin-guix-ssh`
  (the base executor) and the Guix software-deployment plugin. Part 1 below
  changes it.
- `~/spheres/work/cgdd-sevs-ecf`: the first user (its step 9 needs a 256 GB
  machine); `docs/plan-guix-compute-image.md` there documents the step-9 Guix
  image and the never-executed OpenStack scripts in
  `~/spheres/work/cgdd-sevs-ecf-step9/cloud/`, which this plugin replaces.

## Goal

Run selected Snakemake jobs on an OpenStack instance (first target: OVH Public
Cloud, flavour b3-256 or r3-256) that exists only for the duration of the run:
create it when the first job is submitted, deploy Guix closures and inputs, run,
fetch outputs, delete it. Paying for one instance per run is accepted; leaking an
instance that keeps billing is not.

```sh
snakemake <upstream targets>                            # local, as usual
snakemake --profile profiles/ovh-b3-256 <target>        # only stale jobs go remote
```

```yaml
# profiles/ovh-b3-256/config.yaml
executor: guix-openstack
jobs: 1
guix-openstack-rules: [<the big rule>]
guix-openstack-flavor: b3-256
guix-openstack-image: guix-worker-2026-10-05
guix-openstack-max-hours: 6
guix-openstack-identity-file: ~/.ssh/id_guix_worker
software-deployment-method: [guix]
sdm-guix-profile-cache: .snakemake/guix/profiles
shared-fs-usage: none
```

Credentials never appear in settings: openstacksdk reads `OS_*` (an OVH openrc
or an application credential) or `clouds.yaml`.

## Prior art (2026-10-05)

No catalogued executor targets OpenStack. Two community executors rent a cloud
machine per job and are the model for the safeguards:

- `snakemake-executor-plugin-vastai`: one Vast.ai instance per job, destroyed
  afterwards; boot timeout, hard max runtime, max price.
- `snakemake-executor-plugin-spawn`: one EC2 instance per job, sized from the
  rule's resources, with a TTL and terminate-on-complete.

Both are container/pip based. Here the expensive part is the Guix closure copy,
so the unit is **one instance per run**, shared by every remote job of the run.

## Shape

Two changes, in order, in two repositories:

1. **guix-ssh gains a host-source seam** (in `snakemake-guix`; small, useful
   on its own).
2. **This repository** provides the `guix-openstack` executor: a subclass of
   the guix-ssh `Executor` whose host source creates and deletes an instance.

Snakemake has no provisioner plugin type and runs one executor per invocation,
so provisioning must be an executor. Subclassing keeps closure transfer,
staging, launch, polling and retrieval in one place.

## Part 1: guix-ssh changes (in snakemake-guix)

Current state (`snakemake-guix/executor/src/snakemake_executor_plugin_guix_ssh/`): hosts are
parsed eagerly in `Executor.__post_init__` from `settings.hosts` (required);
`run_job` round-robins over `self.hosts`; `shutdown()`/`cancel_jobs()` know
nothing about hosts. The interface already calls `cancel()` → `cancel_jobs()` +
`shutdown()` on interrupt and `shutdown()` at the end of every run
(`snakemake_interface_executor_plugins/executors/remote.py:106`,
`snakemake/scheduling/job_scheduler.py:252,267,398-407`).

1. **`HostSource` protocol** (`hosts.py`, ~40 lines):

   ```python
   class HostSource(Protocol):
       def acquire(self) -> list[Host]: ...
       def release(self, hosts: list[Host], *, failed: bool) -> None: ...

   class StaticHosts:          # today's behaviour
       def __init__(self, hosts): self.hosts = hosts
       def acquire(self): return self.hosts
       def release(self, hosts, *, failed): pass
   ```

   `Executor.make_host_source(settings) -> HostSource` is the override point.

2. **Lazy acquire.** `run_job` calls `self._hosts()`, which acquires once under
   a lock. A run where every target is up to date acquires nothing. Validate
   hosts (non-empty, unique keys) after acquire instead of in `__post_init__`.

3. **Release in `shutdown()`**, idempotent (cancel calls shutdown; shutdown can
   run twice), after `super().shutdown()` has joined the wait thread. `failed`
   is true if any job was reported as an error or cancelled. Release errors are
   logged at error level with enough detail to act on, then re-raised.

4. **Settings split.** `hosts` is `required: True`, so a subclass cannot inherit
   `ExecutorSettings` as is. Move the SSH fields (`identity_file`, `ssh_args`,
   `remove_failed`, `transfer_concurrency`, `retries`, the new timeout) into a
   `SshSettings` base dataclass; guix-ssh's `ExecutorSettings(SshSettings)` adds
   `hosts`. The CLI of guix-ssh is unchanged.

5. **Unreachable timeout.** `check_active_jobs` treats `UNREACHABLE` as
   running forever. Add `unreachable_timeout` (default 600 s): record the first
   unreachable time per job, report an error past the limit, reset on success.
   This matters for static hosts too, and is critical when the host bills.

6. **Fetch logs and benchmarks.** `retrieve_outputs` only fetches
   `job.output`; `job.log` and `job.benchmark` stay remote. With an ephemeral
   host they are lost at deletion. Fetch them after success and, best effort,
   after failure (before `remove_failed` cleanup).

7. **`guix copy` and the identity file.** `Commands.guix_copy` passes only
   `--to=HOSTNAME`; `identity_file` and `ssh_args` are ignored by it, and the
   port must come from `~/.ssh/config`. Part 2 solves this with a generated SSH
   config (see "SSH trust"); document the limitation in the README meanwhile.

Tests (fakes only, in `snakemake-guix/executor/tests/`): lazy acquire, nothing
acquired when no job runs, release once after cancel + shutdown, `failed` flag,
unreachable timeout, log retrieval, static source equals today's behaviour.

## Part 2: this repository

Layout (repository root):

```text
pyproject.toml     # snakemake-executor-plugin-guix-openstack; deps: guix-ssh, openstacksdk
README.md
LICENSE            # GPL-3.0-or-later, as snakemake-guix
.guix-channel      # channel; depends on the snakemake-guix channel
guix.scm -> .guix/modules/guix-openstack/packages.scm
.guix/modules/guix-openstack/
  packages.scm     # python-snakemake-executor-plugin-guix-openstack
  worker.scm       # guix-openstack-worker-os + host-key console service
src/snakemake_executor_plugin_guix_openstack/
  __init__.py      # ExecutorSettings, common_settings (re-exported), Executor subclass
  cloud.py         # thin wrapper over openstack.connection.Connection (the fake's seam)
  instance.py      # OpenStackHosts: the HostSource
  sshconfig.py     # generated ssh_config + known_hosts
  reap.py          # console script: delete expired tagged instances
tests/
docs/plan.md       # this file
```

Development/testing uses the local sibling sources and the explicit Guix shell
documented in the README. `guix.scm` builds against the local sibling channel
checkout; in a pulled channel, its dependency channel supplies the base
executor package. The package source snapshots are selected from each channel
checkout, so neither package recipe needs a bootstrap source hash.

### Settings (`--guix-openstack-*`)

| Setting | Default | Notes |
|---|---|---|
| `flavor` | required | Checked against the region before anything is created. |
| `image` | required | Glance name or ID of a Guix worker image (see "Worker image"). |
| `max-hours` | required | Hard cap. No default on purpose. |
| `rules` | required | Allowlist of rule names that may go remote. |
| `network` | `Ext-Net` | OVH public network. |
| `cloud` | unset | `clouds.yaml` entry; unset means `OS_*` env. |
| `workdir` | `/var/tmp` | Existing writable remote job root; run and job IDs isolate each job. |
| `boot-timeout` | 900 s | From create to host key on console + ssh up. |
| `on-existing` | `fail` | `fail`, `adopt` or `delete` a live instance of the same workflow. |
| `keep` | `never` | `never`, `on-failure`, `always`. The expiry still applies. |
| `name-prefix` | `snakemake` | Server name `<prefix>-<run id[:8]>`. |
| inherited | | `identity-file` (required here), `ssh-args`, `retries`, `transfer-concurrency`, `remove-failed`, `unreachable-timeout`. |

### Job admission (in `run_job`, before any acquire)

The executor sees one job at a time, never the DAG, so checks are per job:

1. **Rule allowlist** (`rules`, required). A job whose rule isn't listed fails
   immediately. Without it, the two-invocation flow is a cost trap: every
   cgdd-sevs-ecf rule has a Guix env, so any stale upstream job (changed code,
   params or config) would silently go to the expensive instance. Also
   document `snakemake -n` first and `--allowed-rules`.
2. **Fits the flavour:** threads ≤ vCPUs and `mem_mb` ≤ RAM via the existing
   `Capacity`, with the flavour read once (free API call, no instance yet).

### Instance lifecycle (`OpenStackHosts`)

`acquire()`:

1. **Preflight, free of charge:** connect; flavour exists in the region; image
   is active; `on-existing` policy against servers tagged with this workflow
   (see metadata). Absolute limits
   (`compute.get_limits()`) leave room for one more instance of this flavour;
   otherwise fail with the OVH quota hint.
2. **Create** with metadata:
   - `sgo` = `1` (the only tag the reaper trusts),
   - `sgo-run` = run id,
   - `sgo-workflow` = sha256 of controller hostname + absolute workdir,
   - `sgo-expires` = UTC ISO time, now + `max-hours` + 15 min.
3. **Wait** until ACTIVE, read the IPv4 on the network, then poll the console
   log for the host key block (see "SSH trust"), then `ssh true`.
4. Write the SSH config entry; return `[Host("sgo-<run8>", 22, workdir)]`.

**Invariant:** once `create_server` has been *called*, every path out of
`acquire()` either returns a host or deletes the server (and waits for
deletion) before propagating. Concretely:

- The run id and server name are fixed before the call. If `create_server`
  raises (timeout, 5xx), look the server up by `sgo-run` metadata / name and
  delete it if it exists.
- The cleanup lives in `try/finally` (or `except BaseException`), not
  `except Exception`: Ctrl-C during the boot wait raises `KeyboardInterrupt`.
- The host source records server IDs as soon as they are known; `release()`
  deletes by those IDs, not by its `hosts` argument, since `acquire()` may never
  have returned.

Tested by failure injection at each step, including `KeyboardInterrupt` during
the wait and "create raised but the server exists".

`release(hosts, failed)`: unless `keep` says otherwise, `delete_server`, wait
until it is gone (bounded), confirm by listing, and remove the SSH config
entry. If the server still exists, raise with its ID and the
`openstack server delete <id>` command; this is the one error that must never
be swallowed.

**Wall-clock cap:** the executor checks `max-hours` in `check_active_jobs`;
past it, it cancels remote jobs, reports them failed and lets shutdown release.

### SSH trust

The worker image has no cloud-init, so neither key injection nor
cloud-init's host-key printout exists.

- **Client key:** baked into the image (`identity-file` is its private half).
- **Host key:** a boot service in the worker OS prints
  `/etc/ssh/ssh_host_ed25519_key.pub` to the serial console between
  `SGO-HOSTKEY-BEGIN`/`-END` lines. The controller reads it through the
  compute API (`get_server_console_output`) and pins it. No
  `StrictHostKeyChecking=accept-new`, no private host key in the image.
- **Making `guix copy` use it:** the plugin writes
  `$XDG_CACHE_HOME/snakemake-guix-openstack/ssh_config` with one
  `Host sgo-<run8>` block (`HostName`, `User root`, `IdentityFile`,
  `IdentitiesOnly yes`, `UserKnownHostsFile` → a sibling `known_hosts`,
  `StrictHostKeyChecking yes`). The user adds once, at the top of
  `~/.ssh/config`:

  ```text
  Include ~/.cache/snakemake-guix-openstack/ssh_config
  ```

  OpenSSH (ssh, rsync) and Guile-SSH (`guix copy`) were validated against
  vpsdae with the included config and a pinned key. Guile-SSH honored
  `HostName`, `User`, and `IdentityFile`; its `UserKnownHostsFile` lookup used
  the resolved IP, so the plugin keys that file by IP. OVH behavior remains
  unverified until the cloud spike.

### Leak protection

1. `release()` on normal end, error and Ctrl-C (Part 1, item 3).
2. The executor's own `max-hours` cap.
3. **Reaper** for what neither covers (SIGKILL, power loss, laptop asleep):
`snakemake-guix-openstack-reap [--dry-run]` lists servers with `sgo=1` and
deletes those past `sgo-expires`. Run every 10 minutes from an always-on host
with its own credentials (vpsdae via an mcron job). The README now includes a
dedicated-account Guix mcron example; it was evaluated with `guix repl`. It
never touches servers without `sgo=1`.

Rejected: in-instance self-destruct. Halting doesn't stop OVH billing, and
deleting from inside needs OpenStack credentials on the worker.

### Worker image

The API-based, one-time Glance publication and immutable image reuse work is
specified in [plan-glance-image-publication.md](plan-glance-image-publication.md).

A Guix System image with: sshd (key-only root, the controller's key), the host
key console service, guix-daemon authorising the controller's signing key (for
`guix copy`), `bash`, `coreutils`, `rsync`, serial console on ttyS0, DHCP.
Preloading the controller's snakemake and the heavy rule profiles avoids most of
the `guix copy` at each run.

Provide it as `(guix-openstack-worker-os #:authorized-keys … #:signing-keys …)`
in `.guix/modules/guix-openstack/worker.scm`, plus a README section on
`guix system image --image-type=qcow2` and `openstack image create`. A local
14 GiB qcow2 image was built and booted under QEMU. The host-key console service
printed the complete Ed25519 marker block, and sshd served the matching key on
a forwarded port. Both TCG and KVM logged the early init Guile segfault, but
boot continued; a [Guix help thread](https://www.mail-archive.com/help-guix@gnu.org/msg21757.html)
describes the same signature as normal. The OVH cloud boot remains unverified.
The latest image contains the controller's public SSH key and authenticated
successfully from the controller; it has not been uploaded. Uploading stays
manual (one-time, rare). The cgdd-sevs-ecf step-9 image
(`step9-vm.scm`) is the starting point; it lacks only the console service.

## Step 0: plain guix-ssh against vpsdae (free, no OVH credentials)

**Complete (2026-10-06):** a temporary two-rule workflow with an included
module, config file, tracked script, input, output, and log completed on
vpsdae. The first attempts exposed and fixed three issues: Snakemake 9.27's
source enumerator can fail on unset Guix environment fields; remote Snakemake
must start in the staged job directory; and the worker profile must be sourced
so its Guix deployment plugin is discoverable. A Guix closure transfer through
the included SSH config succeeded with a pinned key and no agent. Guile-SSH
honored `HostName`, `User`, and `IdentityFile`; its `UserKnownHostsFile` lookup
used the resolved IP, so the plugin keys that file by IP.

## Spike (manual, with OVH credentials; cloud validation pending)

Smallest flavour (b3-8), one instance, deleted at the end:

1. OVH returns console output through the compute API, and the console service
   output appears there.
2. Boot time to ssh, and `guix copy` throughput controller → instance (laptop
   vs vpsdae as controller).
3. OVH billing granularity for an hourly instance, and whether b3-256/r3-256
   need a quota increase on the project.
4. Server metadata round-trips (keys/values) through OVH's Nova.

The SDK calls the plan relies on exist in openstacksdk 4.6.0
(`compute/v2/_proxy.py`: `create_server`, `delete_server`, `wait_for_delete`,
`servers`, `get_limits`, `get_server_console_output`; `Server` has metadata).
Whether OVH serves each of them is what the spike checks.

## Packaging and release

- `python-snakemake-executor-plugin-guix-openstack` in this repository's
  `.guix/modules/guix-openstack/packages.scm`, using a filtered `local-file`
  snapshot from the channel checkout, and propagating Python, the
  `snakemake-guix` channel's SSH executor, and `python-openstacksdk` (in Guix,
  4.6.0). The source tree no longer needs a self-referential fixed hash.
- Release guix-ssh 0.2.0 (settings split, host source) first; this package
  requires `snakemake-executor-plugin-guix-ssh>=0.2.0,<0.3`.
- cgdd-sevs-ecf adds this channel to `channels.scm` and the package to the
  manifest that provides its controller snakemake.

Release check (2026-10-06): the upstream remote now has the executor-specific
`snakemake-executor-plugin-guix-ssh-0.2.0` tag at commit `1d799bf`; its Guix
package builds from a fresh detached tagged checkout and runs all 31 executor
tests. The separate repository tag named `0.2.0` only changes the root project
version and does not contain the executor subtree. The root OpenStack package
builds against the tagged sibling source, including from a clean tagged
checkout, and passes all 34 tests. The source tags are published to GitHub;
neither project has a PyPI distribution, which remains outside the Guix-only
package workflow.

## Order of work

0. **Complete:** static guix-ssh workflow and pinned `guix copy` on vpsdae.
1. **Complete:** Part 1 and tests in `snakemake-guix`; the signed guix-ssh
   0.2.0 tag is published on GitHub.
2. **Deferred by user:** OVH b3-8 API and boot spike; adjust "SSH trust" from
   the results.
3. **Local implementation complete; upload pending:** package skeleton and
   worker OS procedure; build and boot one image locally, then upload it.
4. **Complete locally:** Part 2 and fake-cloud failure tests.
5. **Pending OVH credentials:** b3-8 toy workflow, then kill the controller
   and verify the reaper deletes its instance.
6. **Pending first OVH run:** cgdd-sevs-ecf profile for the big rule.

## Size estimate

- guix-ssh: +120 / −20 lines (seam, settings split, timeout, logs), +100 test lines.
- New package: ~450 lines (instance ~200, sshconfig ~60, reap ~60, settings and
  glue ~80, cloud wrapper ~50), ~300 test lines.
- Worker OS procedure: ~80 lines of Scheme.

## Alternatives considered

The cloud "batch" executors (aws-batch, googlebatch, azure-batch) are thin
because the provider runs the batch service: it owns the queue and scales VMs,
and Terraform only declares that setup once. OpenStack has no standard batch
service, and OVH's nearest one (AI Training) caps jobs at 12 CPUs with memory
tied to CPUs, too small for a 256 GB job. Getting the batch pattern therefore
means operating one:

| | A. OVH Managed Kubernetes + kubernetes executor | B. Slurm on vpsdae + slurm executor | C. This plan |
|---|---|---|---|
| VM lifecycle | cluster autoscaler, b3-256 pool with `minNodes: 0` | Slurm power saving, resume/suspend scripts create/delete instances | this executor + reaper |
| Survives controller crash | yes | yes | via the reaper |
| Plugin code | none | none | ~450 lines + tests |
| Environments | container images (`guix pack -f docker` + registry), replacing `software: guix(...)` for the remote rule | Guix on nodes, substitutes from vpsdae via `guix publish` | unchanged, closures copied by guix-ssh |
| Data | S3 (OVH Object Storage) | shared FS (NFS over vRack) | rsync from the controller |
| Always-on cost | probably one small node for system pods | slurmctld on vpsdae (already paid) | reaper on vpsdae (already paid) |
| New infrastructure | cluster, registry, bucket | slurmctld, munge, slurm.conf cloud nodes, NFS, vRack, slurmd in image | one image |

Choice: C, for one big rule run occasionally by one user with Guix
environments and data on the controller. **Revisit** if remote jobs grow to
several rules, concurrent machines or other users: then A (first test how
cgdd-sevs-ecf's Guix environments fare as packed images) or B replace this
plugin with standard tools. Keeping C behind the host-source seam makes that a
drop-in change for the workflow (another profile), not a pipeline rewrite.

## Open questions

- `on-existing` default: `fail` is safest; `adopt` saves a boot and a closure
  copy when re-running after a failure. Revisit after the first real uses.
- Several remote jobs at once on one instance: today `jobs:` and `--resources`
  in the profile must match the flavour by hand. Deriving them from the flavour
  needs scheduler access the executor doesn't have.
- More than one instance per run (for example, one per seed): the host source
  returns a list, so it fits later without changing Part 1.
