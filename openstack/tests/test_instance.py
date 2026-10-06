from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from snakemake_executor_plugin_guix_ssh.commands import CommandError
from snakemake_executor_plugin_guix_openstack.instance import OpenStackHosts
from snakemake_executor_plugin_guix_openstack.sshconfig import SSHConfig


class FakeCloud:
    def __init__(self):
        self.servers = []
        self.deletes = []
        self.create_error = None
        self.wait_error = None
        self.close_error = None
        self.created_kwargs = None
        self.closed = False

    def find_flavor(self, name):
        return {"id": "flavor-id", "name": name, "vcpus": 4, "ram": 8192}

    def find_image(self, name):
        return {"id": "image-id", "name": name, "status": "ACTIVE"}

    def find_network(self, name):
        return {"id": "network-id", "name": name}

    def limits(self):
        return {"absolute": {
            "totalCoresUsed": 0, "maxTotalCores": 100,
            "totalRAMUsed": 0, "maxTotalRAMSize": 100000,
            "totalInstancesUsed": 0, "maxTotalInstances": 10,
        }}

    def list_servers(self):
        return list(self.servers)

    def create_server(self, **kwargs):
        self.created_kwargs = kwargs
        server = {
            "id": "server-id", "name": kwargs["name"], "status": "BUILD",
            "metadata": kwargs["metadata"],
            "addresses": {"Ext-Net": [{"version": 4, "addr": "192.0.2.10"}]},
        }
        self.servers.append(server)
        if self.create_error:
            raise self.create_error
        return server

    def wait_for_server(self, server, *, timeout):
        if self.wait_error:
            raise self.wait_error
        return server

    def get_server(self, server_id):
        return next((item for item in self.servers if item["id"] == server_id), None)

    def console_output(self, server_id):
        return "SGO-HOSTKEY-BEGIN\nssh-ed25519 AAAATEST worker\nSGO-HOSTKEY-END\n"

    def set_server_metadata(self, server, **metadata):
        server["metadata"].update(metadata)

    def delete_server(self, server_id):
        self.deletes.append(server_id)
        self.servers = [item for item in self.servers if item["id"] != server_id]

    def wait_for_delete(self, server, *, timeout):
        return server

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class FakeCommands:
    def __init__(self):
        self.calls = []
        self.host_options = {}

    def set_host_options(self, hostname, *, address, known_hosts):
        self.host_options[hostname] = (address, known_hosts)

    def clear_host_options(self, hostname):
        self.host_options.pop(hostname, None)

    def ssh(self, host, command):
        self.calls.append((host, command))


class OpenStackHostsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cloud = FakeCloud()
        self.commands = FakeCommands()
        self.settings = SimpleNamespace(
            cloud=None, flavor="b3-4", image="worker", max_hours=2,
            network="Ext-Net", name_prefix="snakemake", boot_timeout=60,
            on_existing="fail", keep="never", workdir="/work",
            identity_file="/tmp/id_worker",
        )
        self.source = OpenStackHosts(
            self.settings, run_id="0123456789abcdef", workflow_path="/work/repo",
            controller_host="controller", commands=self.commands, cloud=self.cloud,
            ssh_config=SSHConfig(Path(self.temp.name)), sleep=lambda _: None,
        )

    def test_acquire_is_lazy_and_release_deletes_once(self):
        self.assertEqual(self.cloud.servers, [])
        hosts = self.source.acquire()
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0].hostname, "sgo-01234567")
        self.assertEqual(
            self.commands.host_options[hosts[0].hostname],
            ("192.0.2.10", str(self.source.ssh_config.known_hosts_path)),
        )
        self.assertEqual(self.cloud.created_kwargs["networks"], [{"uuid": "network-id"}])
        self.assertEqual(self.source.acquire(), hosts)
        self.source.release(hosts, failed=False)
        self.source.release(hosts, failed=False)
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.cloud.servers, [])
        self.assertEqual(self.commands.host_options, {})

    def test_acquire_tries_second_ipv4_with_pinned_host_key(self):
        original_wait_for_server = self.cloud.wait_for_server

        def wait_for_server(server, *, timeout):
            server["addresses"]["Ext-Net"] = [
                {"version": 4, "addr": "192.0.2.1"},
                {"version": 4, "addr": "192.0.2.2"},
            ]
            return original_wait_for_server(server, timeout=timeout)

        self.cloud.wait_for_server = wait_for_server
        attempts = []

        def ssh(host, command):
            address, known_hosts_path = self.commands.host_options[host.hostname]
            attempts.append(address)
            if address == "192.0.2.1":
                raise CommandError("timed out")
            self.assertIn(
                f"{address} ssh-ed25519 AAAATEST",
                Path(known_hosts_path).read_text(),
            )

        self.commands.ssh = ssh
        hosts = self.source.acquire()
        self.assertEqual(attempts, ["192.0.2.1", "192.0.2.2"])
        self.assertEqual(self.commands.host_options[hosts[0].hostname][0], "192.0.2.2")
        self.assertIn("HostName 192.0.2.2", self.source.ssh_config.config_path.read_text())
        self.assertNotIn("192.0.2.1", self.source.ssh_config.known_hosts_path.read_text())
        self.source.release(hosts, failed=False)

    def test_release_without_any_remote_job_does_not_create_a_cloud_connection(self):
        self.source.cloud = None
        self.source.release([], failed=False)
        self.assertIsNone(self.source.cloud)

    def test_failed_create_that_actually_created_is_cleaned(self):
        self.cloud.create_error = TimeoutError("response lost")
        self.cloud.close_error = RuntimeError("connection close failed")
        with self.assertRaisesRegex(TimeoutError, "response lost"):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.cloud.servers, [])
        self.assertTrue(self.cloud.closed)

    def test_keyboard_interrupt_during_boot_wait_cleans_instance(self):
        self.cloud.wait_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.cloud.servers, [])

    def test_worker_api_failures_after_create_clean_instance(self):
        original_get_server = self.cloud.get_server
        get_server_calls = 0

        def get_server_fails_once(server_id):
            nonlocal get_server_calls
            get_server_calls += 1
            if get_server_calls == 1:
                raise RuntimeError("server lookup failed")
            return original_get_server(server_id)

        self.cloud.get_server = get_server_fails_once
        with self.assertRaisesRegex(RuntimeError, "server lookup failed"):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.cloud.servers, [])

    def test_console_failure_after_create_cleans_instance(self):
        self.cloud.console_output = lambda server_id: (_ for _ in ()).throw(
            RuntimeError("console API unavailable")
        )
        with self.assertRaisesRegex(RuntimeError, "console API unavailable"):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.cloud.servers, [])

    def test_active_wait_failure_after_create_cleans_instance(self):
        self.cloud.wait_error = RuntimeError("Nova wait failed")
        with self.assertRaisesRegex(RuntimeError, "Nova wait failed"):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.cloud.servers, [])

    def test_ssh_never_comes_up_then_config_and_instance_are_removed(self):
        self.settings.boot_timeout = 1
        ticks = [0]

        def sleep(seconds):
            ticks[0] += seconds

        class FailingCommands(FakeCommands):
            def ssh(self, host, command):
                raise CommandError("connection refused")

        self.source.commands = FailingCommands()
        self.source.clock = lambda: ticks[0]
        self.source.sleep = sleep
        with self.assertRaisesRegex(TimeoutError, "did not publish"):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertFalse(self.source.ssh_config.config_path.exists())
        self.assertFalse(self.source.ssh_config.known_hosts_path.exists())

    def test_release_failure_names_manual_delete_command(self):
        hosts = self.source.acquire()
        server = self.cloud.servers[0]
        self.cloud.delete_server = lambda server_id: self.cloud.deletes.append(server_id)
        self.cloud.wait_for_delete = lambda server, *, timeout: None
        self.cloud.close_error = RuntimeError("connection close failed")
        with self.assertRaisesRegex(RuntimeError, "openstack server delete server-id"):
            self.source.release(hosts, failed=False)
        self.assertFalse(self.source.ssh_config.config_path.exists())
        self.assertFalse(self.source.ssh_config.known_hosts_path.exists())
        self.assertEqual(self.commands.host_options, {})
        self.assertTrue(self.cloud.closed)

    def test_release_ignores_stale_server_list_after_direct_get_is_gone(self):
        hosts = self.source.acquire()
        stale = self.cloud.servers[0]
        self.cloud.list_servers = lambda: [stale]
        self.source.release(hosts, failed=False)
        self.assertEqual(self.cloud.deletes, ["server-id"])
        self.assertEqual(self.source.server_ids, set())

    def test_release_retries_direct_get_until_server_is_gone(self):
        hosts = self.source.acquire()
        stale = self.cloud.servers[0]
        original_get_server = self.cloud.get_server
        reads_after_delete = 0

        def get_server(server_id):
            nonlocal reads_after_delete
            if self.cloud.deletes:
                reads_after_delete += 1
                if reads_after_delete == 1:
                    return stale
            return original_get_server(server_id)

        self.cloud.get_server = get_server
        self.source.release(hosts, failed=False)
        self.assertEqual(reads_after_delete, 2)
        self.assertEqual(self.source.server_ids, set())

    def test_quota_preflight_happens_before_create(self):
        self.cloud.limits = lambda: {"absolute": {
            "totalCoresUsed": 99, "maxTotalCores": 100,
            "totalRAMUsed": 0, "maxTotalRAMSize": 100000,
            "totalInstancesUsed": 0, "maxTotalInstances": 10,
        }}
        with self.assertRaisesRegex(ValueError, "quota"):
            self.source.acquire()
        self.assertEqual(self.cloud.servers, [])

    def test_capacity_admission_reads_flavor_without_creating_server(self):
        job = SimpleNamespace(threads=4, resources={"mem_mb": 8000}, rule="large")
        self.source.validate_job(job)
        self.assertEqual(self.cloud.servers, [])
        too_large = SimpleNamespace(threads=5, resources={"mem_mb": 8000}, rule="large")
        with self.assertRaisesRegex(ValueError, "has 4 vCPUs"):
            self.source.validate_job(too_large)

    def test_keep_on_failure_retains_instance(self):
        self.settings.keep = "on-failure"
        hosts = self.source.acquire()
        self.source.release(hosts, failed=True)
        self.assertEqual(self.cloud.deletes, [])
        self.assertEqual(len(self.cloud.servers), 1)

    def test_on_existing_fail_preserves_existing_instance(self):
        self.source.workflow = "workflow-hash"
        self.cloud.servers.append({
            "id": "existing", "name": "old", "status": "ACTIVE",
            "metadata": {"sgo": "1", "sgo-workflow": "workflow-hash"},
        })
        with self.assertRaisesRegex(RuntimeError, "already has tagged"):
            self.source.acquire()
        self.assertEqual(self.cloud.deletes, [])

    def test_adopt_existing_worker_does_not_require_spare_quota(self):
        self.settings.on_existing = "adopt"
        self.source.workflow = "workflow-hash"
        server = {
            "id": "existing", "name": "old", "status": "ACTIVE",
            "metadata": {"sgo": "1", "sgo-workflow": "workflow-hash"},
            "addresses": {"Ext-Net": [{"version": 4, "addr": "192.0.2.10"}]},
        }
        self.cloud.servers.append(server)

        def quota_must_not_be_checked():
            raise AssertionError("adopting a worker must not need spare quota")

        self.cloud.limits = quota_must_not_be_checked
        hosts = self.source.acquire()

        self.assertEqual(self.cloud.created_kwargs, None)
        self.assertEqual(hosts[0].hostname, "sgo-01234567")
        self.assertEqual(self.cloud.deletes, [])

    def test_delete_existing_worker_frees_quota_before_creating_replacement(self):
        self.settings.on_existing = "delete"
        self.source.workflow = "workflow-hash"
        self.cloud.servers.append({
            "id": "old-server", "name": "old", "status": "ACTIVE",
            "metadata": {"sgo": "1", "sgo-workflow": "workflow-hash"},
        })
        original_limits = self.cloud.limits

        def limits_after_deletion():
            self.assertEqual([server["id"] for server in self.cloud.servers], [])
            return original_limits()

        self.cloud.limits = limits_after_deletion
        hosts = self.source.acquire()

        self.assertEqual(self.cloud.deletes, ["old-server"])
        self.assertEqual(hosts[0].hostname, "sgo-01234567")
        self.source.release(hosts, failed=False)
        self.assertEqual(self.cloud.deletes, ["old-server", "server-id"])


if __name__ == "__main__":
    unittest.main()
