from datetime import datetime, timezone
from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from snakemake_executor_plugin_guix_openstack.reap import expired_servers, main


class FakeCloud:
    def __init__(self):
        self.servers = [
            {"id": "expired", "name": "old-worker", "metadata": {
                "sgo": "1", "sgo-expires": "2000-01-01T00:00:00+00:00",
            }},
            {"id": "untagged", "name": "other", "metadata": {
                "sgo-expires": "2000-01-01T00:00:00+00:00",
            }},
        ]
        self.deletes = []
        self.waited = []
        self.closed = False

    def list_servers(self):
        return list(self.servers)

    def delete_server(self, server_id):
        self.deletes.append(server_id)
        self.servers = [server for server in self.servers if server["id"] != server_id]

    def wait_for_delete(self, server, *, timeout):
        self.waited.append((server["id"], timeout))

    def close(self):
        self.closed = True


class ReaperTests(unittest.TestCase):
    def test_only_expired_tagged_servers_are_returned(self):
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        result = list(expired_servers(FakeCloud(), now))
        self.assertEqual([server["id"] for server in result], ["expired"])

    def test_dry_run_lists_expired_worker_without_deleting(self):
        cloud = FakeCloud()
        output = StringIO()
        with patch("snakemake_executor_plugin_guix_openstack.reap.OpenStackCloud", return_value=cloud):
            with redirect_stdout(output):
                result = main(["--dry-run"])
        self.assertEqual(result, 0)
        self.assertIn("would delete expired old-worker", output.getvalue())
        self.assertEqual(cloud.deletes, [])
        self.assertTrue(cloud.closed)

    def test_reaper_deletes_only_expired_sgo_worker_and_confirms_removal(self):
        cloud = FakeCloud()
        output = StringIO()
        with patch("snakemake_executor_plugin_guix_openstack.reap.OpenStackCloud", return_value=cloud):
            with redirect_stdout(output):
                result = main([])
        self.assertEqual(result, 0)
        self.assertIn("deleting expired old-worker", output.getvalue())
        self.assertEqual(cloud.deletes, ["expired"])
        self.assertEqual(cloud.waited, [("expired", 180)])
        self.assertEqual([server["id"] for server in cloud.servers], ["untagged"])
        self.assertTrue(cloud.closed)


if __name__ == "__main__":
    unittest.main()
