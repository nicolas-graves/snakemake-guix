"""Ephemeral OpenStack instance implementation of guix-ssh's HostSource."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import math
from pathlib import PurePosixPath
import time
from typing import Any

from snakemake_executor_plugin_guix_ssh.commands import CommandError
from snakemake_executor_plugin_guix_ssh.model import Capacity, Host

from .cloud import OpenStackCloud
from .sshconfig import SSHConfig, parse_console_host_key

LOG = logging.getLogger(__name__)
DELETE_TIMEOUT = 180


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _metadata(server: Any) -> dict[str, str]:
    return dict(_field(server, "metadata", {}) or {})


class OpenStackHosts:
    """Create exactly one tagged server lazily and release it at executor shutdown."""

    def __init__(
        self,
        settings: Any,
        *,
        run_id: str,
        workflow_path: str,
        controller_host: str,
        commands: Any,
        cloud: Any | None = None,
        ssh_config: SSHConfig | None = None,
        clock=time.monotonic,
        utcnow=lambda: datetime.now(timezone.utc),
        sleep=time.sleep,
    ):
        self.settings = settings
        self.run_id = run_id
        self.run8 = run_id[:8]
        self.workflow = hashlib.sha256(
            f"{controller_host}\0{workflow_path}".encode()
        ).hexdigest()
        self.commands = commands
        self.cloud = cloud
        self.ssh_config = ssh_config or SSHConfig()
        self.clock = clock
        self.utcnow = utcnow
        self.sleep = sleep
        self.hosts: list[Host] = []
        self.server_ids: set[str] = set()
        self._acquired = False
        self._released = False
        self.started_at: float | None = None
        self._flavor = None
        self._image = None
        self._network = None

    def _connection(self):
        if self.cloud is None:
            self.cloud = OpenStackCloud(self.settings.cloud)
        return self.cloud

    def acquire(self) -> list[Host]:
        if self._acquired:
            return list(self.hosts)
        self._acquired = True
        cloud = self._connection()
        server = None
        server_name = f"{self.settings.name_prefix}-{self.run8}"
        metadata = {
            "sgo": "1",
            "sgo-run": self.run_id,
            "sgo-workflow": self.workflow,
            "sgo-expires": self._expiry(),
        }
        try:
            flavor, image = self._preflight(cloud)
            existing = self._existing(cloud)
            if existing:
                server = self._handle_existing(cloud, existing, metadata)
                if server is None:
                    existing = []
            if server is None:
                # Quota only matters when we are about to create a new server.
                # An existing worker can be adopted even when the project has
                # no spare quota, and `delete` may free quota before this check.
                self._check_quota(cloud, flavor)
                self.started_at = self.clock()
                server = cloud.create_server(
                    name=server_name,
                    image_id=_field(image, "id"),
                    flavor_id=_field(flavor, "id"),
                    networks=[{"uuid": _field(self._network, "id")}],
                    metadata=metadata,
                )
            if self.started_at is None:
                self.started_at = self.clock()
            deadline = self.started_at + self.settings.boot_timeout
            server_id = _field(server, "id")
            if server_id:
                self.server_ids.add(str(server_id))
            remaining_seconds = deadline - self.clock()
            if remaining_seconds <= 0:
                raise TimeoutError("worker did not become active before boot timeout")
            remaining = math.ceil(remaining_seconds)
            server = cloud.wait_for_server(server, timeout=remaining)
            server_id = str(_field(server, "id"))
            self.server_ids.add(server_id)
            host = self._wait_for_ssh(cloud, server, deadline)
            self.hosts = [host]
            return list(self.hosts)
        except BaseException:
            # create_server can time out after Nova accepted the request. Resolve by
            # run metadata/name before propagating so no failed boot is left billing.
            lookup_error = None
            if not self.server_ids:
                for attempt in range(3):
                    try:
                        self.server_ids.update(
                            str(_field(item, "id"))
                            for item in cloud.list_servers()
                            if _metadata(item).get("sgo-run") == self.run_id
                            or _field(item, "name") == server_name
                        )
                        lookup_error = None
                        break
                    except Exception as error:
                        lookup_error = error
                        if attempt < 2:
                            self.sleep(1)
                if lookup_error is not None:
                    LOG.exception(
                        "could not look up a possibly created OpenStack server",
                        exc_info=lookup_error,
                    )
            if server is not None and _field(server, "id"):
                self.server_ids.add(str(_field(server, "id")))
            cleanup_error = None
            try:
                self._delete_ids(cloud)
            except BaseException as error:
                cleanup_error = error
            finally:
                self._close_cloud()
            if cleanup_error is not None:
                LOG.error(
                    "failed to clean up instance after acquire failed",
                    exc_info=(type(cleanup_error), cleanup_error, cleanup_error.__traceback__),
                )
                raise RuntimeError(
                    f"instance acquisition failed and cleanup failed: {cleanup_error}; "
                    f"delete any remaining server with: openstack server delete "
                    f"{' '.join(sorted(self.server_ids))}"
                ) from cleanup_error
            if lookup_error is not None:
                raise RuntimeError(
                    f"could not confirm whether OpenStack created {server_name}; "
                    "inspect with `openstack server list --name "
                    f"{server_name}` and delete any matching server"
                ) from lookup_error
            alias = f"sgo-{self.run8}"
            self.commands.clear_host_options(alias)
            self.ssh_config.remove(alias)
            raise

    def _preflight(self, cloud):
        flavor = self._flavor or cloud.find_flavor(self.settings.flavor)
        if flavor is None:
            raise ValueError(f"OpenStack flavor {self.settings.flavor!r} was not found")
        image = self._image or cloud.find_image(self.settings.image)
        if image is None or str(_field(image, "status", "")).upper() != "ACTIVE":
            raise ValueError(f"OpenStack image {self.settings.image!r} is not active")
        network = self._network or cloud.find_network(self.settings.network)
        if network is None:
            raise ValueError(f"OpenStack network {self.settings.network!r} was not found")
        self._flavor, self._image, self._network = flavor, image, network
        return flavor, image

    def _check_quota(self, cloud, flavor):
        limits = cloud.limits()
        absolute = _field(limits, "absolute", limits)
        checks = (
            ("total_cores_used", "totalCoresUsed", "max_total_cores", "maxTotalCores", "vcpus"),
            ("total_ram_used", "totalRAMUsed", "max_total_ram_size", "maxTotalRAMSize", "ram"),
            ("total_instances_used", "totalInstancesUsed", "max_total_instances", "maxTotalInstances", None),
        )
        for used_key, old_used_key, max_key, old_max_key, flavor_key in checks:
            maximum = _field(absolute, max_key, _field(absolute, old_max_key))
            used = _field(absolute, used_key, _field(absolute, old_used_key))
            if maximum is None or used is None or int(maximum) < 0:
                continue
            requested = _field(flavor, flavor_key, 1) if flavor_key else 1
            if int(used) + int(requested) > int(maximum):
                hint = "check the OVH Public Cloud project quota or free instances"
                raise ValueError(f"OpenStack quota {max_key} would be exceeded; {hint}")

    def _existing(self, cloud):
        return [
            server
            for server in cloud.list_servers()
            if _metadata(server).get("sgo") == "1"
            and _metadata(server).get("sgo-workflow") == self.workflow
            and str(_field(server, "status", "")).upper() != "DELETED"
        ]

    def _handle_existing(self, cloud, servers, new_metadata):
        policy = self.settings.on_existing
        if policy == "fail":
            ids = ", ".join(str(_field(server, "id")) for server in servers)
            raise RuntimeError(f"workflow already has tagged OpenStack server(s): {ids}")
        if policy == "delete":
            self.server_ids.update(str(_field(server, "id")) for server in servers)
            self._delete_ids(cloud)
            return None
        if policy != "adopt":
            raise ValueError(f"unknown on-existing policy: {policy}")
        if len(servers) != 1:
            raise RuntimeError("cannot adopt multiple OpenStack servers for one workflow")
        server = servers[0]
        self.started_at = self.clock()
        self.server_ids.add(str(_field(server, "id")))
        cloud.set_server_metadata(server, **new_metadata)
        return server

    def _wait_for_ssh(self, cloud, server, deadline: float) -> Host:
        server_id = str(_field(server, "id"))
        while self.clock() < deadline:
            server = cloud.get_server(server_id)
            addresses = self._addresses(server)
            if addresses:
                try:
                    key = parse_console_host_key(cloud.console_output(server_id))
                except (CommandError, ValueError, OSError, TimeoutError) as error:
                    LOG.debug("waiting for worker host key (%s): %s", server_id, error)
                    self.sleep(2)
                    continue
                alias = f"sgo-{self.run8}"
                host = Host(alias, 22, PurePosixPath(self.settings.workdir))
                for address in addresses:
                    registered = False
                    try:
                        self.ssh_config.add(alias, address, self.settings.identity_file, key)
                        registered = True
                        self.commands.set_host_options(
                            alias,
                            address=address,
                            known_hosts=str(self.ssh_config.known_hosts_path),
                        )
                        self.commands.ssh(host, "true")
                        return host
                    except (CommandError, ValueError, OSError, TimeoutError) as error:
                        LOG.debug("waiting for worker SSH (%s, %s): %s", server_id, address, error)
                        self.commands.clear_host_options(alias)
                        if registered:
                            self.ssh_config.remove(alias)
            self.sleep(2)
        raise TimeoutError(
            f"worker {server_id} did not publish its host key and accept SSH "
            f"within {self.settings.boot_timeout} seconds"
        )

    def _addresses(self, server):
        addresses = _field(server, "addresses", {}) or {}
        networks = [addresses.get(self.settings.network, [])]
        networks.extend(
            candidates for name, candidates in addresses.items()
            if name != self.settings.network
        )
        result = []
        for candidates in networks:
            for address in candidates:
                value = _field(address, "addr")
                if str(_field(address, "version")) == "4" and value and value not in result:
                    result.append(value)
        return result

    def _expiry(self):
        return (self.utcnow() + timedelta(hours=float(self.settings.max_hours), minutes=15))\
            .astimezone(timezone.utc).isoformat()

    def release(self, hosts: list[Host], *, failed: bool) -> None:
        if self._released:
            return
        if not self._acquired:
            self._released = True
            return
        keep = self.settings.keep == "always" or (
            self.settings.keep == "on-failure" and failed
        )
        if keep:
            LOG.warning("keeping OpenStack server(s) %s per guix-openstack-keep", sorted(self.server_ids))
            self._released = True
            self._close_cloud()
            return
        try:
            deletion_error = None
            try:
                if self.server_ids:
                    self._delete_ids(self._connection())
            except BaseException as error:
                deletion_error = error

            cleanup_errors = []
            for host in hosts or self.hosts:
                try:
                    self.commands.clear_host_options(host.hostname)
                    self.ssh_config.remove(host.hostname)
                except BaseException as error:
                    cleanup_errors.append(error)

            if deletion_error is not None:
                for error in cleanup_errors:
                    LOG.error(
                        "failed to remove SSH configuration after instance deletion failed",
                        exc_info=(type(error), error, error.__traceback__),
                    )
                raise deletion_error
            if cleanup_errors:
                raise RuntimeError(
                    "failed to remove SSH configuration: "
                    + "; ".join(str(error) for error in cleanup_errors)
                ) from cleanup_errors[0]
            self._released = True
        finally:
            self._close_cloud()

    def _close_cloud(self):
        close = getattr(self.cloud, "close", None)
        if close is not None:
            self.cloud = None
            try:
                close()
            except Exception:
                # Connection teardown must not hide the more useful acquire or
                # deletion error that triggered cleanup. The server lifecycle
                # has already been handled independently of this session.
                LOG.error("failed to close OpenStack connection", exc_info=True)

    def _delete_ids(self, cloud):
        failures = []
        for server_id in sorted(self.server_ids):
            try:
                server = cloud.get_server(server_id)
                if server is None:
                    self.server_ids.discard(server_id)
                    continue
                cloud.delete_server(server_id)
                cloud.wait_for_delete(server, timeout=DELETE_TIMEOUT)
                for attempt in range(5):
                    if cloud.get_server(server_id) is None:
                        break
                    if attempt == 4:
                        raise RuntimeError("server still exists after wait_for_delete")
                    self.sleep(1)
                self.server_ids.discard(server_id)
            except BaseException as error:
                failures.append((server_id, error))
        if failures:
            detail = "; ".join(
                f"{server_id}: {error} (run `openstack server delete {server_id}`)"
                for server_id, error in failures
            )
            raise RuntimeError(f"could not delete OpenStack server(s): {detail}")

    def validate_job(self, job) -> None:
        """Check flavor sizing without creating an instance."""
        required_flavor = job.resources.get("openstack_flavor")
        if required_flavor and required_flavor != self.settings.flavor:
            raise ValueError(
                f"job {job.rule} requires OpenStack flavor {required_flavor!r}, "
                f"but the profile selects {self.settings.flavor!r}"
            )
        cloud = self._connection()
        flavor = self._flavor or cloud.find_flavor(self.settings.flavor)
        if flavor is None:
            raise ValueError(f"OpenStack flavor {self.settings.flavor!r} was not found")
        self._flavor = flavor
        cpus = int(_field(flavor, "vcpus", 0))
        mem_mb = int(_field(flavor, "ram", 0))
        capacity = Capacity(cpus=cpus, mem_mb=mem_mb)
        if not capacity.feasible(job):
            requested_mem = int(job.resources.get("mem_mb", 0))
            requested_gpus = int(job.resources.get("gpu", job.resources.get("gpus", 0)))
            raise ValueError(
                f"job {job.rule} needs {job.threads} threads, {requested_mem} MiB, "
                f"and {requested_gpus} GPUs; flavor {self.settings.flavor} has "
                f"{cpus} vCPUs, {mem_mb} MiB, and no declared GPUs"
            )
