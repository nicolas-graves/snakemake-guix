"""Small, replaceable boundary around openstacksdk."""

from __future__ import annotations

from typing import Any


class OpenStackCloud:
    """Expose the small compute and Glance operations used by this plugin.

    Tests can pass a fake object implementing this same method set to
    ``OpenStackHosts`` or the image maintenance helper without credentials or
    a live cloud.
    """

    def __init__(self, cloud: str | None = None, region_name: str | None = None):
        try:
            import openstack
        except ImportError as error:  # pragma: no cover - packaging guard
            raise RuntimeError("openstacksdk is required for guix-openstack") from error
        options = {"cloud": cloud, "region_name": region_name}
        self.connection = openstack.connect(**{
            key: value for key, value in options.items() if value is not None
        })
        self.compute = self.connection.compute

    def find_flavor(self, name_or_id: str) -> Any:
        return self.compute.find_flavor(name_or_id)

    def find_image(self, name_or_id: str) -> Any:
        return self.connection.image.find_image(name_or_id)

    def image_scope(self) -> tuple[str | None, str | None]:
        """Return the authenticated project and selected Glance region."""
        project_id = self.connection.session.get_project_id()
        region_name = self.connection.config.get_region_name("image")
        return project_id, region_name

    def list_images(self, *, name: str) -> list[Any]:
        return list(self.connection.image.images(name=name))

    def get_image(self, image_id: str) -> Any:
        return self.connection.image.get_image(image_id)

    def create_image(self, **kwargs: Any) -> Any:
        return self.connection.image.create_image(**kwargs)

    def find_network(self, name_or_id: str) -> Any:
        return self.connection.network.find_network(name_or_id)

    def list_servers(self) -> list[Any]:
        return list(self.compute.servers(details=True))

    def limits(self) -> Any:
        return self.compute.get_limits()

    def create_server(self, **kwargs: Any) -> Any:
        return self.compute.create_server(**kwargs)

    def get_server(self, server_id: str) -> Any:
        from openstack.exceptions import ResourceNotFound

        try:
            return self.compute.get_server(server_id)
        except ResourceNotFound:
            return None

    def set_server_metadata(self, server: Any, **metadata: str) -> Any:
        return self.compute.set_server_metadata(server, **metadata)

    def wait_for_server(self, server: Any, *, timeout: int) -> Any:
        return self.compute.wait_for_server(
            server, status="ACTIVE", failures=["ERROR"], interval=2, wait=timeout
        )

    def console_output(self, server_id: str) -> str:
        result = self.compute.get_server_console_output(server_id, length=1000)
        if isinstance(result, dict):
            return result.get("output", "") or ""
        return str(result or "")

    def delete_server(self, server_id: str) -> None:
        self.compute.delete_server(server_id, ignore_missing=True)

    def wait_for_delete(self, server: Any, *, timeout: int) -> Any:
        return self.compute.wait_for_delete(server, interval=2, wait=timeout)

    def close(self) -> None:
        self.connection.close()
