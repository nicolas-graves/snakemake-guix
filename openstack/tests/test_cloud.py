from types import SimpleNamespace
import inspect
import unittest
from unittest.mock import Mock, patch

from snakemake_executor_plugin_guix_openstack.cloud import OpenStackCloud


class CloudAdapterTests(unittest.TestCase):
    def setUp(self):
        class ResourceNotFound(Exception):
            pass

        self.ResourceNotFound = ResourceNotFound
        self.compute = Mock()
        self.image = Mock()
        self.network = Mock()
        self.connection = Mock(compute=self.compute, image=self.image, network=self.network)
        self.connect = Mock(return_value=self.connection)
        self.patch_openstack = patch.dict(
            "sys.modules", {
                "openstack": SimpleNamespace(connect=self.connect),
                "openstack.exceptions": SimpleNamespace(ResourceNotFound=ResourceNotFound),
            }
        )
        self.patch_openstack.start()
        self.addCleanup(self.patch_openstack.stop)

    def test_openstacksdk_proxy_methods_match_adapter_calls(self):
        self.patch_openstack.stop()
        from openstack.compute.v2._proxy import Proxy as ComputeProxy
        from openstack.compute.v2.server import Server
        from openstack.network.v2._proxy import Proxy as NetworkProxy

        self.assertIn("wait", inspect.signature(ComputeProxy.wait_for_server).parameters)
        self.assertIn("wait", inspect.signature(ComputeProxy.wait_for_delete).parameters)
        self.assertTrue(hasattr(ComputeProxy, "get_server_console_output"))
        self.assertTrue(hasattr(NetworkProxy, "find_network"))
        for field in ("image_id", "flavor_id", "networks", "metadata"):
            self.assertTrue(hasattr(Server, field), f"Server has no {field} field")

    def test_cloud_selection_and_wait_timeout_arguments(self):
        cloud = OpenStackCloud("ovh")
        self.connect.assert_called_once_with(cloud="ovh")
        cloud.wait_for_server("server", timeout=45)
        self.compute.wait_for_server.assert_called_once_with(
            "server", status="ACTIVE", failures=["ERROR"], interval=2, wait=45
        )
        cloud.wait_for_delete("server", timeout=30)
        self.compute.wait_for_delete.assert_called_once_with(
            "server", interval=2, wait=30
        )

    def test_console_response_is_normalized(self):
        self.compute.get_server_console_output.return_value = {"output": "console"}
        cloud = OpenStackCloud()
        self.assertEqual(cloud.console_output("server"), "console")
        self.compute.get_server_console_output.assert_called_once_with(
            "server", length=1000
        )
        self.connect.assert_called_once_with()

    def test_instance_operations_are_delegated_to_openstacksdk(self):
        cloud = OpenStackCloud()
        server = SimpleNamespace(id="server-id")
        self.compute.servers.return_value = [server]
        self.compute.get_server.return_value = server
        self.compute.get_limits.return_value = {"absolute": {}}

        self.assertEqual(cloud.list_servers(), [server])
        self.compute.servers.assert_called_once_with(details=True)
        self.assertEqual(cloud.get_server("server-id"), server)
        self.compute.get_server.assert_called_once_with("server-id")
        self.assertEqual(cloud.limits(), {"absolute": {}})
        self.compute.get_limits.assert_called_once_with()

        cloud.create_server(name="worker", metadata={"sgo": "1"})
        self.compute.create_server.assert_called_once_with(
            name="worker", metadata={"sgo": "1"}
        )
        cloud.set_server_metadata(
            server, **{"sgo-expires": "2030-01-01T00:00:00+00:00"}
        )
        self.compute.set_server_metadata.assert_called_once_with(
            server, **{"sgo-expires": "2030-01-01T00:00:00+00:00"}
        )
        cloud.delete_server("server-id")
        self.compute.delete_server.assert_called_once_with(
            "server-id", ignore_missing=True
        )

    def test_get_server_returns_none_only_for_not_found(self):
        cloud = OpenStackCloud()
        self.compute.get_server.side_effect = self.ResourceNotFound("gone")
        self.assertIsNone(cloud.get_server("server-id"))
        self.compute.get_server.side_effect = RuntimeError("API unavailable")
        with self.assertRaisesRegex(RuntimeError, "API unavailable"):
            cloud.get_server("server-id")

    def test_images_and_networks_use_their_own_service_proxies(self):
        cloud = OpenStackCloud()
        cloud.find_image("image-name")
        cloud.find_network("Ext-Net")
        self.image.find_image.assert_called_once_with("image-name")
        self.network.find_network.assert_called_once_with("Ext-Net")

    def test_glance_operations_and_region_are_delegated(self):
        self.connection.session = Mock()
        self.connection.session.get_project_id.return_value = "project-id"
        self.connection.config = Mock()
        self.connection.config.get_region_name.return_value = "GRA11"
        self.image.images.return_value = ["candidate"]
        self.image.get_image.return_value = "fresh"
        self.image.create_image.return_value = "created"
        cloud = OpenStackCloud("ovh", region_name="GRA11")
        self.connect.assert_called_once_with(cloud="ovh", region_name="GRA11")
        self.assertEqual(cloud.image_scope(), ("project-id", "GRA11"))
        self.assertEqual(cloud.list_images(name="worker"), ["candidate"])
        self.image.images.assert_called_once_with(name="worker")
        self.assertEqual(cloud.get_image("image-id"), "fresh")
        self.image.get_image.assert_called_once_with("image-id")
        self.assertEqual(cloud.create_image(name="worker"), "created")
        self.image.create_image.assert_called_once_with(name="worker")


if __name__ == "__main__":
    unittest.main()
