from pathlib import Path, PurePosixPath
import subprocess as sp
from types import SimpleNamespace

import pytest

from snakemake_executor_plugin_guix_ssh.commands import Commands
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

    def ssh(self, host, script):
        self.ssh_calls.append((host, script))
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
    with pytest.raises(ValueError, match="workflow-relative"):
        Transport(RecordingCommands()).stage_inputs(
            host, PurePosixPath("/remote/run/1"), ["../secret"]
        )


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


def test_status_is_polled_without_persistent_connection(host):
    commands = RecordingCommands()
    remote = RemoteJob(host, PurePosixPath("/remote/run/7"), "digest")
    status, message = Lifecycle(commands).status(remote)
    assert status is Status.RUNNING
    assert message == ""
    assert len(commands.ssh_calls) == 1
