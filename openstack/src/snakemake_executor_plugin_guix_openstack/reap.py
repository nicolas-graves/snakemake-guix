"""Delete expired servers created by this executor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import sys

from .cloud import OpenStackCloud
from .instance import DELETE_TIMEOUT, _field, _metadata

LOG = logging.getLogger("snakemake_executor_plugin_guix_openstack.reap")


def expired_servers(cloud, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    for server in cloud.list_servers():
        metadata = _metadata(server)
        if metadata.get("sgo") != "1" or not metadata.get("sgo-expires"):
            continue
        try:
            expires = datetime.fromisoformat(metadata["sgo-expires"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            LOG.error("skipping server %s with invalid sgo-expires metadata", _field(server, "id"))
            continue
        if expires <= now:
            yield server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Delete expired Guix OpenStack workers")
    parser.add_argument("--cloud", help="clouds.yaml entry; defaults to OS_* environment")
    parser.add_argument("--dry-run", action="store_true", help="list expired workers without deleting them")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cloud = OpenStackCloud(arguments.cloud)
    try:
        expired = list(expired_servers(cloud))
        for server in expired:
            server_id = str(_field(server, "id"))
            name = _field(server, "name", "(unnamed)")
            if arguments.dry_run:
                print(f"would delete {server_id} {name}")
                continue
            print(f"deleting {server_id} {name}")
            cloud.delete_server(server_id)
            cloud.wait_for_delete(server, timeout=DELETE_TIMEOUT)
            if any(str(_field(item, "id")) == server_id for item in cloud.list_servers()):
                LOG.error("server %s remained visible after deletion", server_id)
                return 1
        if not expired:
            print("no expired guix-openstack servers")
        return 0
    finally:
        cloud.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
