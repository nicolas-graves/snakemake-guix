from pathlib import Path, PurePosixPath
import subprocess as sp
from types import SimpleNamespace

import pytest

from snakemake_executor_plugin_guix_ssh.commands import CommandError, Commands
from snakemake_executor_plugin_guix_ssh.lifecycle import Lifecycle, RemoteJob, Status
from snakemake_executor_plugin_guix_ssh.model import Capacity, Host
from snakemake_executor_plugin_guix_ssh.transport import Transport


class RecordingCommands:
    def __init__(self):
        self.copies = []
        self.ssh_calls = []
        self.rsync_calls = []

    def guix_copy(self, host, path):
        self.copies.append((host, path))

    def ssh(self, host, script, *, retries=None):
        self.ssh_calls.append((host, script, retries))
        return sp.CompletedProcess([], 0, stdout="RUNNING\n", stderr="")

    def rsync(self, host, sources, destination, *, relative=True):
        self.rsync_calls.append((host, list(sources), destination, relative))
        if not relative:
            Path(destination).touch()


@pytest.fixture
def host():
    return Host.parse("worker.example:2222:/var/tmp/snakemake worker")


def test_host_parser_rejects_ambiguous_or_relative_values():
    with pytest.raises(ValueError, match="expected"):
        Host.parse("worker")
    with pytest.raises(ValueError, match="absolute"):
        Host.parse("worker:22:relative")


def test_ssh_arguments_are_argv_not_shell_text(host):
    commands = Commands("key with spaces", "-o 'ProxyCommand=proxy --flag'")
    assert commands.ssh_args(host) == [
        "-p",
        "2222",
        "-i",
        "key with spaces",
        "-o",
        "ProxyCommand=proxy --flag",
        "worker.example",
    ]


def test_cloud_host_options_pin_hostname_user_and_known_hosts(host):
    commands = Commands()
    commands.set_host_options(
        host.hostname, address="192.0.2.10", known_hosts="/run/user/1000/known_hosts"
    )

    assert commands.ssh_args(host) == [
        "-p", "2222",
        "-F", "/dev/null",
        "-o", "HostName=192.0.2.10",
        "-o", "User=root",
        "-o", "UserKnownHostsFile=/run/user/1000/known_hosts",
        "-o", "StrictHostKeyChecking=yes",
        "worker.example",
    ]
    commands.clear_host_options(host.hostname)
    assert commands.ssh_args(host)[-1] == "worker.example"


def test_preflight_rejects_guix_copy_port_mismatch(host, monkeypatch):
    commands = Commands()
    monkeypatch.setattr("snakemake_executor_plugin_guix_ssh.commands.shutil.which", lambda _: "/bin/tool")
    commands.run = lambda argv, **kwargs: sp.CompletedProcess(
        argv, 0, stdout="hostname worker.example\nuser user\nport 22\n", stderr=""
    )
    with pytest.raises(CommandError, match="configure port 2222"):
        commands.preflight(host)


def test_preflight_names_each_remote_requirement(host, monkeypatch):
    commands = Commands()
    monkeypatch.setattr("snakemake_executor_plugin_guix_ssh.commands.shutil.which", lambda _: "/bin/tool")
    commands.run = lambda argv, **kwargs: sp.CompletedProcess(
        argv, 0, stdout="hostname worker.example\nuser user\nport 2222\n", stderr=""
    )
    scripts = []
    commands.ssh = lambda host, script: scripts.append(script)

    commands.preflight(host)

    assert len(scripts) == 1
    assert "remote guix is unavailable" in scripts[0]
    assert "remote rsync is unavailable" in scripts[0]
    assert "remote workdir does not exist" in scripts[0]
    assert "remote workdir is not writable" in scripts[0]


def test_closure_is_deployed_once_per_host_and_digest(host):
    commands = RecordingCommands()
    transport = Transport(commands)
    first = SimpleNamespace(digest="a", profile_store_path=Path("/gnu/store/a"))
    second = SimpleNamespace(digest="b", profile_store_path=Path("/gnu/store/b"))

    transport.deploy_environment(host, first)
    transport.deploy_environment(host, first)
    transport.deploy_environment(host, second)

    assert [str(path) for _, path in commands.copies] == [
        "/gnu/store/a",
        "/gnu/store/b",
    ]


def test_staging_never_transfers_snakemake_metadata(host):
    commands = RecordingCommands()
    transport = Transport(commands)

    transport.stage_inputs(
        host,
        PurePosixPath("/remote/run/1"),
        ["inputs/a.txt", ".snakemake/metadata/x"],
    )

    assert commands.rsync_calls[0][1] == ["inputs/a.txt"]


def test_staging_rejects_paths_outside_workflow(host):
    with pytest.raises(ValueError, match="traverses"):
        Transport(RecordingCommands()).stage_inputs(
            host, PurePosixPath("/remote/run/1"), ["../secret"]
        )


def test_absolute_paths_under_working_directory_map_to_relative_paths(host, tmp_path):
    source = tmp_path / "inputs" / "data.txt"
    source.parent.mkdir()
    source.write_text("data")
    commands = RecordingCommands()
    transport = Transport(commands)
    transport.stage_inputs(host, PurePosixPath("/remote/run/1"), [str(source)], tmp_path)
    assert commands.rsync_calls[0][1] == [f"{tmp_path}/./inputs/data.txt"]
    assert transport._safe_paths([str(source)], tmp_path) == ["inputs/data.txt"]


def test_failed_second_transfer_does_not_publish_first_output(host, tmp_path):
    class FailingCommands(RecordingCommands):
        def rsync(self, host, sources, destination, *, relative=True):
            if len(self.rsync_calls) == 1:
                raise RuntimeError("transfer failed")
            super().rsync(host, sources, destination, relative=relative)

    commands = FailingCommands()
    transport = Transport(commands)
    with pytest.raises(RuntimeError, match="transfer failed"):
        transport.retrieve_outputs(
            host, PurePosixPath("/remote/run/1"),
            ["receipt.txt", "manifest.json"], tmp_path,
        )
    assert not (tmp_path / "receipt.txt").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_path_mapping_rejects_absolute_outside_root_and_deduplicates_aliases(tmp_path):
    inside = tmp_path / "inside"
    inside.write_text("value")
    with pytest.raises(ValueError, match="outside working directory"):
        Transport._safe_paths([str(tmp_path.parent / "outside")], tmp_path)
    assert Transport._safe_paths(["inside", str(inside)], tmp_path) == ["inside"]


def test_directory_output_replaces_existing_directory(host, tmp_path):
    class DirectoryCommands(RecordingCommands):
        def rsync(self, host, sources, destination, *, relative=True):
            Path(destination).mkdir()
            (Path(destination) / "new.txt").write_text("new")

    previous = tmp_path / "result"
    previous.mkdir()
    (previous / "old.txt").write_text("old")
    Transport(DirectoryCommands()).retrieve_outputs(
        host, PurePosixPath("/remote/run/1"), ["result"], tmp_path
    )
    assert sorted(path.name for path in previous.iterdir()) == ["new.txt"]


def test_output_retrieval_does_not_preserve_remote_absolute_path(host, tmp_path):
    commands = RecordingCommands()
    transport = Transport(commands)

    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        transport.retrieve_outputs(
            host, PurePosixPath("/remote/run/1"), ["results/hello.txt"]
        )
    finally:
        os.chdir(previous)

    assert commands.rsync_calls[0][1] == [
        "worker.example:/remote/run/1/results/hello.txt"
    ]
    assert commands.rsync_calls[0][3] is False


def test_capacity_accounts_for_cpu_memory_and_gpu():
    job = SimpleNamespace(threads=4, resources={"mem_mb": 8000, "gpu": 1})
    capacity = Capacity(cpus=8, mem_mb=16000, gpus=1)
    assert capacity.feasible(job)
    capacity.reserve(job)
    assert not capacity.feasible(job)
    capacity.release(job)
    assert capacity.feasible(job)


def test_cancellation_targets_remote_process_group(host):
    commands = RecordingCommands()
    remote = RemoteJob(host, PurePosixPath("/remote/run/7"), "digest")
    Lifecycle(commands).cancel(remote)
    assert "kill -TERM -- -$(cat pid)" in commands.ssh_calls[0][1]


def test_launch_uses_one_attempt_and_writes_pid_in_job_directory(host):
    commands = RecordingCommands()
    remote = RemoteJob(host, PurePosixPath("/remote/run/7"), "digest")
    Lifecycle(commands).launch(remote, "sleep 1")
    _, script, retries = commands.ssh_calls[0]
    assert retries == 1
    assert "cd /remote/run/7 &&" in script
    assert "{ nohup setsid bash -c" in script
    assert 'printf %s "$$" > pid' in script
    assert "& for attempt in" in script


def test_status_is_polled_without_persistent_connection(host):
    commands = RecordingCommands()
    remote = RemoteJob(host, PurePosixPath("/remote/run/7"), "digest")
    status, message = Lifecycle(commands).status(remote)
    assert status is Status.RUNNING
    assert message == ""
    assert len(commands.ssh_calls) == 1
