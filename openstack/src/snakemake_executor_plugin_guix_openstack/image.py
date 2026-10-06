"""Maintenance command for immutable private worker images in Glance."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

from .cloud import OpenStackCloud

LOG = logging.getLogger("snakemake_executor_plugin_guix_openstack.image")
PUBLISHER = "snakemake-executor-plugin-guix-openstack"
PUBLISHER_PROPERTY = "sgo_publisher"
DIGEST_PROPERTY = "sgo_source_sha256"
DEFAULT_TIMEOUT = 3600
POLL_INTERVAL = 2


class ImageEnsureError(RuntimeError):
    """The requested image could not be safely reused or published."""


def _field(image: Any, name: str, default: Any = None) -> Any:
    if isinstance(image, dict):
        return image.get(name, default)
    return getattr(image, name, default)


def _properties(image: Any) -> dict[str, Any]:
    return _field(image, "properties", None) or {}


def _source_info(path: str | os.PathLike[str]) -> tuple[Path, str, str, int]:
    source = Path(path).expanduser()
    try:
        if not source.is_file():
            raise ImageEnsureError(f"image file is not a regular file: {source}")
        sha256 = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        with source.open("rb") as stream:
            if stream.read(4) != b"QFI\xfb":
                raise ImageEnsureError(f"image file is not qcow2: {source}")
            stream.seek(0)
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                sha256.update(block)
                md5.update(block)
                size += len(block)
    except OSError as error:
        raise ImageEnsureError(f"cannot read image file {source}: {error}") from error
    return source.resolve(), sha256.hexdigest(), md5.hexdigest(), size


def _verify(image: Any, *, project_id: str, region: str, digest: str,
            md5: str, size: int, name: str) -> str:
    image_id = str(_field(image, "id", "(unknown)"))
    status = str(_field(image, "status", "unknown")).upper()
    properties = _properties(image)
    checks = {
        "name": _field(image, "name") == name,
        "status": status == "ACTIVE",
        "owner": _field(image, "owner", _field(image, "owner_id")) == project_id,
        "visibility": _field(image, "visibility") == "private",
        "disk format": _field(image, "disk_format") == "qcow2",
        "container format": _field(image, "container_format") == "bare",
        "size": _field(image, "size") == size,
        "source digest": properties.get(DIGEST_PROPERTY) == digest,
        "publisher": properties.get(PUBLISHER_PROPERTY) == PUBLISHER,
    }
    remote_md5 = _field(image, "checksum")
    hash_algo = _field(image, "hash_algo")
    hash_value = _field(image, "hash_value")
    has_matching_hash = remote_md5 == md5 or (
        str(hash_algo).lower() == "sha256" and hash_value == digest
    )
    checks["Glance checksum"] = has_matching_hash
    actual_region = _field(image, "region") or _field(image, "region_name")
    if actual_region is not None:
        checks["region"] = actual_region == region
    failed = [label for label, passed in checks.items() if not passed]
    if failed:
        detail = ", ".join(failed)
        raise ImageEnsureError(
            f"image {image_id} failed validation ({detail}; status={status}); "
            f"inspect with: openstack image show {image_id}"
        )
    return image_id


def _wait_for_active(cloud: Any, image: Any, *, timeout: int) -> Any:
    image_id = str(_field(image, "id", "(unknown)"))
    deadline = time.monotonic() + timeout
    current = image
    while True:
        status = str(_field(current, "status", "unknown")).upper()
        if status == "ACTIVE":
            return current
        if status in {"ERROR", "KILLED", "DELETED", "DEACTIVATED"}:
            raise ImageEnsureError(
                f"image {image_id} entered status {status}; inspect with: "
                f"openstack image show {image_id}; remove only by ID after inspection"
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ImageEnsureError(
                f"timed out waiting for image {image_id} (status={status}); "
                f"inspect with: openstack image show {image_id}"
            )
        time.sleep(min(POLL_INTERVAL, remaining))
        current = cloud.get_image(image_id)
        if current is None:
            raise ImageEnsureError(f"image {image_id} disappeared while waiting")


def _existing(cloud: Any, name: str) -> list[Any]:
    return [image for image in cloud.list_images(name=name)
            if _field(image, "name") == name]


def ensure_image(cloud: Any, file: str | os.PathLike[str], *, name_prefix: str,
                 region: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Reuse one validated private image or publish the local qcow2 once."""
    source, digest, md5, size = _source_info(file)
    if not name_prefix or "/" in name_prefix:
        raise ImageEnsureError("name prefix must be a non-empty image name prefix")
    name = f"{name_prefix}-{digest[:16]}"
    project_id, resolved_region = cloud.image_scope()
    if not project_id:
        raise ImageEnsureError("OpenStack did not resolve a project ID unambiguously")
    if not resolved_region:
        raise ImageEnsureError("OpenStack did not resolve a Glance region")
    if resolved_region != region:
        raise ImageEnsureError(
            f"requested region {region!r} but OpenStack resolved {resolved_region!r}"
        )
    print(f"Project: {project_id}; Glance region: {resolved_region}", file=sys.stderr)

    matches = _existing(cloud, name)
    if len(matches) > 1:
        ids = ", ".join(str(_field(item, "id", "(unknown)")) for item in matches)
        raise ImageEnsureError(f"multiple images named {name}: {ids}; resolve duplicates by ID")
    if matches:
        candidate = matches[0]
        props = _properties(candidate)
        if props.get(DIGEST_PROPERTY) != digest or props.get(PUBLISHER_PROPERTY) != PUBLISHER:
            raise ImageEnsureError(
                f"image name conflict for {name} (ID {_field(candidate, 'id', '(unknown)')}); "
                "inspect it and choose a different --name-prefix"
            )
        candidate = _wait_for_active(cloud, candidate, timeout=timeout)
        fresh = cloud.get_image(str(_field(candidate, "id")))
        if fresh is None:
            raise ImageEnsureError(f"image {_field(candidate, 'id')} disappeared during validation")
        return _verify(fresh, project_id=project_id, region=resolved_region,
                       digest=digest, md5=md5, size=size, name=name)

    LOG.info("uploading %s (%d bytes, sha256 %s)", source, size, digest)
    try:
        created = cloud.create_image(
            name=name,
            filename=str(source),
            disk_format="qcow2",
            container_format="bare",
            visibility="private",
            properties={DIGEST_PROPERTY: digest, PUBLISHER_PROPERTY: PUBLISHER},
            sha256=digest,
            md5=md5,
            allow_duplicates=True,
            wait=True,
            timeout=timeout,
            validate_checksum=True,
        )
    except Exception as error:
        # The API may have accepted the upload even if its response was lost.
        try:
            retry_matches = [item for item in _existing(cloud, name)
                             if _properties(item).get(DIGEST_PROPERTY) == digest
                             and _properties(item).get(PUBLISHER_PROPERTY) == PUBLISHER]
        except Exception:
            retry_matches = []
        found = ", ".join(
            f"{_field(item, 'id', '(unknown)')} ({_field(item, 'status', 'unknown')})"
            for item in retry_matches
        )
        if retry_matches:
            commands = "; ".join(
                f"inspect with: openstack image show {_field(item, 'id')}; "
                f"cleanup only after inspection: openstack image delete {_field(item, 'id')}"
                for item in retry_matches
            )
            suffix = f"; matching image record(s): {found}; {commands}"
        else:
            suffix = f"; inspect with: openstack image list --name {name}"
        raise ImageEnsureError(
            f"upload failed: {error}{suffix}"
        ) from error

    created_id = _field(created, "id")
    if not created_id:
        raise ImageEnsureError("upload returned no image ID; inspect images by exact name")
    try:
        _wait_for_active(cloud, created, timeout=timeout)
        fresh = cloud.get_image(str(created_id))
        if fresh is None:
            raise ImageEnsureError(f"new image {created_id} disappeared after upload")
        return _verify(fresh, project_id=project_id, region=resolved_region,
                       digest=digest, md5=md5, size=size, name=name)
    except Exception as error:
        raise ImageEnsureError(
            f"image upload created ID {created_id} but validation failed: {error}; "
            f"inspect with: openstack image show {created_id}; "
            f"cleanup only after inspection: openstack image delete {created_id}"
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage immutable Guix worker images in Glance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ensure = subparsers.add_parser("ensure", help="reuse or upload a private qcow2 image")
    ensure.add_argument("--file", required=True, help="existing qcow2 built by guix system image")
    ensure.add_argument("--name-prefix", default="guix-worker")
    ensure.add_argument("--region", required=True, help="Glance region")
    ensure.add_argument("--cloud", help="clouds.yaml entry; defaults to OS_* environment")
    ensure.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"maximum upload/status wait in seconds (default: {DEFAULT_TIMEOUT})")
    arguments = parser.parse_args(argv)
    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)
    cloud = OpenStackCloud(arguments.cloud, region_name=arguments.region)
    try:
        print(ensure_image(cloud, arguments.file, name_prefix=arguments.name_prefix,
                           region=arguments.region, timeout=arguments.timeout))
        return 0
    except Exception as error:
        LOG.error("%s", error)
        return 1
    finally:
        cloud.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
