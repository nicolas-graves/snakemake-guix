"""Sources of SSH workers consumed by the executor."""

from typing import Iterable, Protocol

from .model import Host


class HostSource(Protocol):
    def acquire(self) -> list[Host]: ...

    def release(self, hosts: list[Host], *, failed: bool) -> None: ...


class StaticHosts:
    """The original configured-host behavior, expressed as a source."""

    def __init__(self, hosts: Iterable[str | Host]):
        self._configured_hosts = list(hosts)
        self._hosts: list[Host] | None = None

    def acquire(self) -> list[Host]:
        if self._hosts is None:
            self._hosts = [
                host if isinstance(host, Host) else Host.parse(host)
                for host in self._configured_hosts
            ]
        return list(self._hosts)

    def release(self, hosts: list[Host], *, failed: bool) -> None:
        pass
