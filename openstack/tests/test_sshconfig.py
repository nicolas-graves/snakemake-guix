from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from snakemake_executor_plugin_guix_openstack.sshconfig import (
    SSHConfig,
    parse_console_host_key,
)


class SSHConfigTests(unittest.TestCase):
    def test_only_marked_ed25519_key_is_accepted(self):
        self.assertEqual(
            parse_console_host_key(
                "boot\nSGO-HOSTKEY-BEGIN\nssh-ed25519 AAAA key\nSGO-HOSTKEY-END\n"
            ),
            "ssh-ed25519 AAAA",
        )
        with self.assertRaises(ValueError):
            parse_console_host_key("ssh-ed25519 AAAA without markers")

    def test_config_pins_key_and_remove_cleans_run_entry(self):
        with TemporaryDirectory() as directory:
            config = SSHConfig(Path(directory))
            config.add("sgo-abcd1234", "192.0.2.1", "/home/user/key", "ssh-ed25519 AAAA")
            text = config.config_path.read_text()
            self.assertIn("StrictHostKeyChecking yes", text)
            self.assertIn("UserKnownHostsFile", text)
            self.assertEqual(
                config.known_hosts_path.read_text(), "192.0.2.1 ssh-ed25519 AAAA\n"
            )
            config.add("sgo-ef012345", "192.0.2.2", "/home/user/key", "ssh-ed25519 BBBB")
            config.remove("sgo-abcd1234")
            self.assertIn("Host sgo-ef012345", config.config_path.read_text())
            self.assertEqual(config.known_hosts_path.read_text(), "192.0.2.2 ssh-ed25519 BBBB\n")
            config.remove("sgo-ef012345")
            self.assertFalse(config.config_path.exists())
            self.assertFalse(config.known_hosts_path.exists())


if __name__ == "__main__":
    unittest.main()
