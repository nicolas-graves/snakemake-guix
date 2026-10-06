# Plan: publish and reuse a Guix worker image in Glance

Status: local implementation and fake-cloud coverage added, 2026-10-06. No
live image has been published by this command. The GRA11 image `guix-worker-2026-10-06`
(`5d0a9d57-1a97-48d7-b8d9-8b3744c3b36a`) has already booted and completed
the b3-8 Hello world Snakemake smoke test. Keep it as the current working
baseline. This plan does not require another instance or replace that image.

## Resource model

The qcow2 belongs in the project's regional OpenStack **Glance image service**.
It remains available after each Nova worker is deleted. It is not a persistent
file on an individual worker. `ExecutorSettings.image` already accepts an image
name or ID; `OpenStackHosts._preflight()` requires it to be `ACTIVE`, and Nova
boots new workers from its ID. Use the ID in workflow profiles to avoid name
ambiguity. The executor's normal job path must neither build nor upload images.

Glance image bytes are immutable after upload. Rebuilding the Guix System OS,
changing an authorized SSH key, or changing the controller's Guix signing key
therefore produces a *new* Glance image ID. Switch the workflow profile to that
ID after validation; do not overwrite the prior image or delete it as part of
`ensure`. Image storage and quota remain in use until an operator deletes old
images explicitly. See the [Glance image management guide](https://docs.openstack.org/glance/latest/admin/manage-images.html).

## Snakemake's view of the image

An image published by the maintenance command is an external execution
resource, not a file output of a Snakemake rule. Put its exact Glance ID in the
executor profile as `guix-openstack-image`; the executor resolves that ID and
requires the image to be `ACTIVE` before it starts a scheduled remote job. No
local stub file is needed to make the worker usable. A stub can outlive a
deleted image and cannot prove that Glance still has the expected bytes.

An executor setting is not a rule input or parameter. Changing only the image
ID does not make already-complete Snakemake outputs stale, and a run with no
scheduled remote job will not check Glance. If output provenance must change
with the worker image, read the same pinned ID from workflow configuration into
the affected rule's `params`, as well as the executor profile, and keep the
default `params` rerun trigger enabled. This makes a changed ID trigger those
rules to rerun. For a future workflow that *publishes* images as a Snakemake
step, use a validated receipt containing the Glance ID, region, and source
digest as that rule's file output, with downstream rules depending on the
receipt. A zero-byte success marker is insufficient.

## Command interface

Add a separate console entry point in `pyproject.toml`:

```text
snakemake-guix-openstack-image ensure --file /gnu/store/...-disk-image.qcow2 \
  --name-prefix guix-worker --region GRA11
```

`--file` is an existing readable qcow2 built by `guix system image`; the command
does not invoke Guix or create a VM. `--cloud NAME` selects a `clouds.yaml`
entry; otherwise openstacksdk uses the standard `OS_*` environment from the
OpenRC or an application credential. `--region` selects the SDK region and is
required when the credential or cloud entry does not already select one. Print
the resulting image ID on stdout; send progress and diagnostics to stderr.
Do not print credentials, environment variables, or signed request headers.
The command should show the resolved project and region before uploading, and
must fail if the project or region cannot be resolved unambiguously.

Keep `--guix-openstack-image` required for the executor. Publishing is a
deliberate maintenance action; a routine Snakemake run never uploads a qcow2,
changes image metadata, or silently selects a newer image.

## `ensure` algorithm

1. Validate that the file exists, is readable, and is qcow2. Compute the
   full SHA-256 of its bytes and record its size. Use an exact versioned name,
   for example `guix-worker-<first 16 SHA-256 hex digits>`. Store the full
   digest in the image property `sgo_source_sha256`, plus a property identifying
   this publisher. The digest refers to the uploaded qcow2 bytes, not to the
   14 GiB virtual disk size or a mutable filename.
2. Establish one SDK connection using the same auth conventions as the
   executor. Resolve the project ID and region. Query Glance in that scope for
   the exact versioned name and publisher property. Reuse **only** one `ACTIVE`
   private image owned by this project whose full digest, disk format, and
   container format match. Return its ID without reading/uploading the file
   again beyond the local digest pass. A conflicting name, duplicate match,
   unexpected owner, or mismatched property is an error, not a reason to reuse.
3. If absent, call the SDK image upload API with the file path, `qcow2` disk
   format, `bare` container format, private visibility, the digest metadata,
   and a bounded wait for `ACTIVE`. Pass the local digest as the SDK checksum
   input where supported and ask the SDK to validate the completed upload.
   Return the new ID only after a fresh Glance GET confirms `ACTIVE`, expected
   owner/region, expected formats, size, and digest/checksum. The SDK's
   [`create_image` API](https://docs.openstack.org/openstacksdk/latest/user/connection.html#create_image)
   supports upload from `filename` and waiting for completion.
4. A queued, uploading, importing, killed, or otherwise non-active record with
   the same name must be reported with its ID and status. Wait for a concurrent
   upload only within the command timeout; never assume success or delete a
   partially uploaded image automatically. Retrying after a lost response must
   first query Glance by the exact name and full digest so an already completed
   upload is reused rather than duplicated. Because Glance allows duplicate
   names, concurrent publishers can still race: detect duplicate candidates
   and require operator resolution instead of selecting one arbitrarily.
5. Leave the baseline image and all other images untouched. On a failed upload,
   report any newly created image ID and an explicit inspection/cleanup command.
   Never delete by name. The operator can later remove superseded images by ID
   after no profile refers to them.

The Glance identity and image roles must permit image list, create, upload,
read, and private-image metadata operations in the chosen project and region.
Check image size and storage quota before upload where the provider exposes
them, and report quota/policy errors without creating a worker. OVH's custom
image guide uses `OS_REGION_NAME` with the OpenRC, so an image published in
GRA11 must also be selected from GRA11 for the executor run. See the
[OVHcloud custom image guide](https://help.ovhcloud.com/csm/fr-public-cloud-compute-packer-openstack-builder?id=kb_article_view&sysparm_article=KB0050648).

## Code and tests

- Add `src/snakemake_executor_plugin_guix_openstack/image.py` for argument
  parsing and the `ensure` workflow. Extend `OpenStackCloud` only with the
  small Glance operations used here; keep the Nova host lifecycle unchanged.
- Keep the image lookup and checksum decision in a pure helper that accepts a
  fake cloud. Unit tests cover existing matching image, missing image/upload,
  ambiguous names, wrong project/region, metadata or checksum mismatch,
  pending and failed statuses, upload timeout, interrupted/retried upload,
  quota/policy errors, and no implicit deletion. Assert that the reuse path
  makes no upload call and the executor itself makes none.
- Add an SDK contract test for the `create_image` argument names used by the
  Guix-packaged openstacksdk version. Keep the existing b3-8 Hello world test
  as the end-to-end executor check. A separate explicitly authorized live
  check can query the existing GRA11 image read-only, then publish one newly
  built uniquely named image, rerun `ensure` to confirm the same ID, and boot
  one cheap worker from that ID. Inspect billing/quota and remove only the
  disposable test image by exact ID when authorized; do not touch the validated
  baseline.

## Guix channel and release path

1. The maintenance entry point, SDK 4.6.0 contract check, README workflow, and
   fake-cloud tests are implemented. The Guix package definition is maintained
   in the sibling `snakemake-guix` channel with the `guix-ssh` dependency.
2. The plugin is released as 0.2.0, and the sibling channel pins that exact
   source tag and checksum. Both changes are built and tested before use.
3. Keep image ID and region in the consumer profile, never credentials. A
   separate explicitly authorized live check can query the existing GRA11
   image read-only, publish one newly built uniquely named image, rerun
   `ensure` to confirm the same ID, then boot one cheap worker from that ID.
   Inspect billing/quota and remove only a disposable test image by exact ID
   when authorized; do not touch the validated baseline.

Implementation, package release, and channel packaging are complete. Real
image publication and worker boot validation remain separate follow-up work;
no live OpenStack action is performed by the release workflow.
