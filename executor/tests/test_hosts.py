import asyncio
from pathlib import Path, PurePosixPath
from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from snakemake_interface_executor_plugins.executors.remote import RemoteExecutor

from snakemake_executor_plugin_guix_ssh import Executor, SshSettings
from snakemake_executor_plugin_guix_ssh.hosts import StaticHosts
from snakemake_executor_plugin_guix_ssh.lifecycle import RemoteJob, Status
from snakemake_executor_plugin_guix_ssh.model import Host


class RecordingSource:
    def __init__(self, hosts):
        self.hosts = hosts
        self.acquires = 0
        self.releases = []

    def acquire(self):
        self.acquires += 1
        return self.hosts

    def release(self, hosts, *, failed):
        self.releases.append((hosts, failed))


def bare_executor():
    executor = Executor.__new__(Executor)
    executor._hosts_lock = Lock()
    executor._cached_hosts = None
    executor._shutdown_lock = Lock()
    executor._released_hosts = False
    executor._failed = False
    executor.logger = SimpleNamespace(error=lambda *args, **kwargs: None)
    return executor


def test_static_hosts_preserve_configured_behavior_and_parse_lazily():
    source = StaticHosts(["worker.example:22:/var/tmp/work"])
    assert hasattr(source, "acquire") and hasattr(source, "release")
    hosts = source.acquire()
    assert hosts == [Host("worker.example", 22, PurePosixPath("/var/tmp/work"))]
    source.release(hosts, failed=True)
    assert source.acquire() == hosts


def test_remote_profile_is_validated_and_sourced_with_shell_quoting():
    with pytest.raises(ValueError, match="absolute path"):
        SshSettings(remote_profile="relative/profile")

    executor = bare_executor()
    executor.workflow = SimpleNamespace(
        executor_settings=SimpleNamespace(remote_profile="/opt/guix profile")
    )
    assert Executor.get_job_exec_prefix(executor, None) == (
        ". '/opt/guix profile/etc/profile'"
    )


def test_remote_snakemake_starts_in_the_staged_job_directory():
    executor = bare_executor()
    workflow = SimpleNamespace(
        overwrite_workdir="/controller/workflow",
        executor_settings=SimpleNamespace(remote_profile=None),
    )
    executor.workflow = workflow
    executor.controller_executable = Path("/gnu/store/snakemake/bin/snakemake")
    seen = {}

    def base_format_job_exec(self, job):
        seen["workdir"] = self.workflow.overwrite_workdir
        return "remote command"

    with patch.object(RemoteExecutor, "format_job_exec", base_format_job_exec):
        command = Executor.format_job_exec(executor, SimpleNamespace())

    assert seen["workdir"] == "."
    assert workflow.overwrite_workdir == "/controller/workflow"
    assert command.endswith("--sdm-guix-profile-cache .snakemake/guix/profiles")


def test_executor_acquires_hosts_once_and_validates_after_acquire():
    executor = bare_executor()
    host = Host.parse("worker.example:22:/var/tmp/work")
    source = RecordingSource([host])
    executor.host_source = source
    assert executor._hosts() == [host]
    assert executor._hosts() == [host]
    assert source.acquires == 1


def test_submission_failure_marks_run_failed_for_release_policy():
    executor = bare_executor()

    def fail(job):
        raise RuntimeError("submission failed")

    executor._run_job = fail
    with pytest.raises(RuntimeError, match="submission failed"):
        executor.run_job(SimpleNamespace())
    assert executor._failed


def test_workflow_source_staging_includes_config_modules_scripts_and_inputs(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    for name in (
        "Snakefile", "config.yaml", "modules/step/Snakefile", "scripts/run.py",
        "inputs/data.tsv", "large-model.bin",
    ):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    Path("large-model.bin").write_bytes(b"x" * 10_000_001)
    executor = bare_executor()
    executor.workflow = SimpleNamespace(
        main_snakefile=Path("Snakefile").resolve(),
        dag=SimpleNamespace(get_sources=lambda: {
            "Snakefile", "config.yaml", "modules/step/Snakefile", "scripts/run.py",
            "../external.py", "large-model.bin",
        }),
    )
    executor.logger = FakeLogger()
    job = SimpleNamespace(input=["inputs/data.tsv"])
    with pytest.raises(Exception, match="outside the working directory"):
        executor._workflow_sources(job)


def test_workflow_source_staging_falls_back_when_dag_sources_hits_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in (
        "Snakefile", "config.yaml", "modules/workflow.smk", "scripts/build.py",
        "env.scm", "inputs/data.tsv",
    ):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source")

    def broken_sources():
        raise TypeError("expected str, bytes or os.PathLike object, not NoneType")

    job = SimpleNamespace(
        input=["inputs/data.tsv"],
        software_env_spec=SimpleNamespace(
            source_path_attributes=lambda: ("manifest_file", "channel_file"),
            manifest_file=None,
            channel_file="env.scm",
        ),
        rule=SimpleNamespace(basedir=tmp_path),
    )
    executor = bare_executor()
    executor.workflow = SimpleNamespace(
        main_snakefile=Path("Snakefile").resolve(),
        included=["Snakefile", "modules/workflow.smk"],
        rules=[SimpleNamespace(script="scripts/build.py", notebook=None, basedir=tmp_path)],
        configfiles=["config.yaml"],
        dag=SimpleNamespace(get_sources=broken_sources, jobs=[job]),
    )
    executor.logger = FakeLogger()

    assert executor._workflow_sources(job) == [
        "Snakefile", "config.yaml", "env.scm", "modules/workflow.smk",
        "scripts/build.py", "inputs/data.tsv",
    ]
    assert any("software environment field is unset" in message
               for message in executor.logger.warnings)


def test_executor_rejects_empty_and_duplicate_hosts_after_acquire():
    host = Host.parse("worker.example:22:/var/tmp/work")
    for hosts, message in (([], "at least one"), ([host, host], "only once")):
        executor = bare_executor()
        executor.host_source = RecordingSource(hosts)
        with pytest.raises(Exception, match=message):
            executor._hosts()
        assert executor._cached_hosts == hosts


def test_shutdown_releases_hosts_once_after_base_shutdown():
    executor = bare_executor()
    host = Host.parse("worker.example:22:/var/tmp/work")
    executor._cached_hosts = [host]
    source = RecordingSource([host])
    executor.host_source = source
    with patch.object(RemoteExecutor, "shutdown") as base_shutdown:
        executor.shutdown()
        executor.shutdown()
    assert source.releases == [([host], False)]
    assert base_shutdown.call_count == 2


def test_shutdown_does_not_mark_release_complete_after_failure():
    executor = bare_executor()
    source = RecordingSource([])
    executor.host_source = source
    executor._failed = True

    def fail_release(hosts, *, failed):
        source.releases.append((hosts, failed))
        raise RuntimeError("delete failed")

    source.release = fail_release
    with patch.object(RemoteExecutor, "shutdown"):
        with pytest.raises(RuntimeError, match="delete failed"):
            executor.shutdown()
    assert not executor._released_hosts
    assert source.releases == [([], True)]


def test_shutdown_releases_hosts_even_when_base_shutdown_fails():
    executor = bare_executor()
    host = Host.parse("worker.example:22:/var/tmp/work")
    executor._cached_hosts = [host]
    source = RecordingSource([host])
    executor.host_source = source

    with patch.object(RemoteExecutor, "shutdown", side_effect=RuntimeError("join failed")):
        with pytest.raises(RuntimeError, match="join failed"):
            executor.shutdown()

    assert source.releases == [([host], False)]
    assert executor._released_hosts


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message, **kwargs):
        self.errors.append(message)


def make_active():
    host = Host.parse("worker.example:22:/var/tmp/work")
    remote = RemoteJob(host, PurePosixPath("/var/tmp/work/run/1"), "digest")
    job = SimpleNamespace(log=["logs/job.log"], benchmark="bench/job.tsv")
    active = SimpleNamespace(aux={"remote": remote}, external_jobid="job-1", job=job)
    return active, remote


def test_unreachable_job_is_retained_until_timeout_then_errors(monkeypatch):
    executor = bare_executor()
    executor.workflow = SimpleNamespace(
        executor_settings=SimpleNamespace(unreachable_timeout=10, remove_failed=False)
    )
    executor.lifecycle = SimpleNamespace(status=lambda _: (Status.UNREACHABLE, "offline"))
    executor._unreachable_since = {"job-1": 0}
    executor._retrieve_auxiliary_outputs = lambda *args: None
    errors = []
    executor.report_job_error = lambda active, msg=None: errors.append(msg)
    active, _ = make_active()
    monkeypatch.setattr("snakemake_executor_plugin_guix_ssh.time.monotonic", lambda: 11)
    remaining = asyncio.run(_collect(executor.check_active_jobs([active])))
    assert remaining == []
    assert "remained unreachable" in errors[0]


def test_unreachable_timer_resets_when_host_responds(monkeypatch):
    executor = bare_executor()
    executor.workflow = SimpleNamespace(
        executor_settings=SimpleNamespace(unreachable_timeout=10, remove_failed=False)
    )
    executor.lifecycle = SimpleNamespace(status=lambda _: (Status.RUNNING, ""))
    executor._unreachable_since = {"job-1": 0}
    active, _ = make_active()
    monkeypatch.setattr("snakemake_executor_plugin_guix_ssh.time.monotonic", lambda: 100)
    remaining = asyncio.run(_collect(executor.check_active_jobs([active])))
    assert remaining == [active]
    assert executor._unreachable_since == {}


async def _collect(generator):
    return [item async for item in generator]


def test_auxiliary_logs_and_benchmark_are_fetched_individually():
    executor = bare_executor()
    executor.transport = SimpleNamespace(retrieve_outputs=Mock())
    executor.logger = FakeLogger()
    active, remote = make_active()
    executor._retrieve_auxiliary_outputs(active.job, remote)
    assert [call.args[2] for call in executor.transport.retrieve_outputs.call_args_list] == [
        ["logs/job.log"],
        ["bench/job.tsv"],
    ]


def test_success_retrieves_outputs_logs_and_benchmark_before_cleanup():
    executor = bare_executor()
    active, remote = make_active()
    active.job.output = ["results/output.txt"]
    events = []
    executor.workflow = SimpleNamespace(
        executor_settings=SimpleNamespace(unreachable_timeout=10, remove_failed=False)
    )
    executor.lifecycle = SimpleNamespace(
        status=lambda _: (Status.SUCCEEDED, ""),
        cleanup=lambda _: events.append("cleanup"),
    )
    executor.transport = SimpleNamespace(
        retrieve_outputs=lambda _host, _directory, paths: events.append(list(paths))
    )
    executor.logger = FakeLogger()
    executor._unreachable_since = {}
    executor.report_job_success = lambda _: events.append("success")
    asyncio.run(_collect(executor.check_active_jobs([active])))
    assert events == [
        ["results/output.txt"], ["logs/job.log"], ["bench/job.tsv"],
        "cleanup", "success",
    ]


def test_failure_retrieves_logs_before_remove_failed_cleanup():
    executor = bare_executor()
    active, _ = make_active()
    events = []
    executor.workflow = SimpleNamespace(
        executor_settings=SimpleNamespace(unreachable_timeout=10, remove_failed=True)
    )
    executor.lifecycle = SimpleNamespace(
        status=lambda _: (Status.FAILED, "job failed"),
        cleanup=lambda _: events.append("cleanup"),
    )
    executor.transport = SimpleNamespace(
        retrieve_outputs=lambda _host, _directory, paths: events.append(list(paths))
    )
    executor.logger = FakeLogger()
    executor._unreachable_since = {}
    executor.report_job_error = lambda _, msg=None: events.append(("error", msg))
    asyncio.run(_collect(executor.check_active_jobs([active])))
    assert events == [
        ["logs/job.log"], ["bench/job.tsv"], ("error", "job failed"), "cleanup"
    ]
