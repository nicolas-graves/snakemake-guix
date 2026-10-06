"""Pinned SSH trust material used by ssh, rsync, and guix copy."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4


HOSTKEY_BEGIN = "SGO-HOSTKEY-BEGIN"
HOSTKEY_END = "SGO-HOSTKEY-END"


def parse_console_host_key(console: str) -> str:
    """Return the single Ed25519 public key enclosed in the worker markers."""
    try:
        block = console.split(HOSTKEY_BEGIN, 1)[1].split(HOSTKEY_END, 1)[0]
    except IndexError as error:
        raise ValueError("worker host key is not present in the serial console") from error
    keys = [line.strip() for line in block.splitlines() if line.strip()]
    if len(keys) != 1:
        raise ValueError(f"expected one host key in console block, found {len(keys)}")
    fields = keys[0].split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise ValueError("worker console did not contain an Ed25519 host key")
    return f"{fields[0]} {fields[1]}"


class SSHConfig:
    def __init__(self, directory: Path | None = None):
        cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        self.directory = directory or cache_home / "snakemake-guix-openstack"
        self.config_path = self.directory / "ssh_config"
        self.known_hosts_path = self.directory / "known_hosts"

    def add(self, alias: str, address: str, identity_file: str, host_key: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self._replace_known_host(address, host_key)
        identity_path = self._quote(str(Path(identity_file).expanduser()))
        known_hosts_path = self._quote(str(self.known_hosts_path))
        entry = (
            f"Host {alias}\n"
            f"  HostName {address}\n"
            "  User root\n"
            f"  IdentityFile {identity_path}\n"
            "  IdentitiesOnly yes\n"
            f"  UserKnownHostsFile {known_hosts_path}\n"
            "  StrictHostKeyChecking yes\n"
        )
        old = self.config_path.read_text() if self.config_path.exists() else ""
        blocks = [block.strip() for block in old.split("\n\n") if block.strip()]
        blocks = [block for block in blocks if not block.splitlines()[0].startswith(f"Host {alias}")]
        self._atomic_write(self.config_path, "\n\n".join([*blocks, entry.rstrip()]) + "\n")

    def preflight(self, identity_file: str) -> None:
        """Ensure Guix copy can resolve the generated alias before renting a VM."""
        alias = f"sgo-preflight-{uuid4().hex}"
        address = "192.0.2.1"
        # The key is never used to connect; ssh -G only reads configuration.
        key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        try:
            self.add(alias, address, identity_file, key)
            result = subprocess.run(["ssh", "-G", alias], capture_output=True, text=True)
            if result.returncode:
                raise ValueError(f"cannot inspect generated SSH alias: {result.stderr.strip()}")
            options = dict(line.split(None, 1) for line in result.stdout.splitlines() if " " in line)
            identity = str(Path(identity_file).expanduser())
            identities = [line.split(None, 1)[1] for line in result.stdout.splitlines()
                          if line.startswith("identityfile ")]
            if (options.get("hostname") != address
                    or options.get("user") != "root"
                    or identity not in identities
                    or str(self.known_hosts_path) not in options.get("userknownhostsfile", "")):
                raise ValueError(
                    f"generated OpenStack SSH aliases are not visible to guix copy; "
                    f"add 'Include {self.config_path}' before any Host blocks in ~/.ssh/config"
                )
        finally:
            self.remove(alias)

    def remove(self, alias: str) -> None:
        address = None
        if self.config_path.exists():
            blocks = []
            for block in self.config_path.read_text().split("\n\n"):
                if not block.strip():
                    continue
                block = block.strip()
                lines = block.splitlines()
                if lines[0].split(maxsplit=1) == ["Host", alias]:
                    for line in lines[1:]:
                        key, _, value = line.strip().partition(" ")
                        if key.lower() == "hostname":
                            address = value.strip().strip('"')
                            break
                else:
                    blocks.append(block)
            if blocks:
                self._atomic_write(self.config_path, "\n\n".join(blocks) + "\n")
            else:
                self.config_path.unlink()
        if self.known_hosts_path.exists():
            lines = [line for line in self.known_hosts_path.read_text().splitlines()
                     if not address or not line.startswith(f"{address} ")]
            if lines:
                self._atomic_write(self.known_hosts_path, "\n".join(lines) + "\n")
            else:
                self.known_hosts_path.unlink()

    def _replace_known_host(self, address: str, host_key: str) -> None:
        lines = self.known_hosts_path.read_text().splitlines() if self.known_hosts_path.exists() else []
        lines = [line for line in lines if not line.startswith(f"{address} ")]
        self._atomic_write(self.known_hosts_path, "\n".join([*lines, f"{address} {host_key}"]) + "\n")

    @staticmethod
    def _quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def _atomic_write(path: Path, contents: str) -> None:
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(contents)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
