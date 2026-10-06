import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from snakemake_interface_common.exceptions import WorkflowError

from snakemake_executor_plugin_guix_openstack import Executor, ExecutorSettings


def settings(identity_file, **overrides):
    values = {
        "flavor": "b3-8",
        "image": "worker-image",
        "max_hours": 1,
        "rules": ["expensive"],
        "identity_file": str(identity_file),
    }
    values.update(overrides)
    return ExecutorSettings(**values)


def job(rule_name="expensive"):
    return SimpleNamespace(rule=SimpleNamespace(name=rule_name), threads=1, resources={})


def bare_executor(executor_settings, source):
    executor = Executor.__new__(Executor)
    executor.workflow = SimpleNamespace(executor_settings=executor_settings)
    executor.openstack_hosts = source
    return executor


def test_executor_settings_include_inherited_ssh_safety_defaults(tmp_path):
    config = settings(tmp_path / "identity")
    assert config.retries == 3
    assert config.transfer_concurrency == 2
    assert config.unreachable_timeout == 600
    assert config.rules == ["expensive"]
    assert config.workdir == "/var/tmp"
    assert config.ssh_args == "-o ConnectTimeout=5 -o ConnectionAttempts=1"


def test_executor_settings_reject_negative_unreachable_timeout(tmp_path):
    with pytest.raises(ValueError, match="unreachable_timeout must be non-negative"):
        settings(tmp_path / "identity", unreachable_timeout=-1)


def test_openstack_jobs_source_the_worker_system_profile(tmp_path):
    executor = bare_executor(settings(tmp_path / "identity"), SimpleNamespace())
    prefix = Executor.get_job_exec_prefix(executor, job())
    assert prefix.startswith(". /run/current-system/profile/etc/profile && ")
    assert "/run/current-system/profile/lib/python*/site-packages" in prefix
    assert 'PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$site_packages"' in prefix
    assert prefix.endswith("export PYTHONPATH")


def test_host_source_uses_effective_workdir_when_workflow_workdir_is_a_method(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    captured = {}

    def host_source(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "snakemake_executor_plugin_guix_openstack.OpenStackHosts", host_source
    )
    executor = Executor.__new__(Executor)
    executor.workflow = SimpleNamespace(workdir=lambda value: None)
    executor.run_id = "test-run"
    executor.commands = object()

    Executor.make_host_source(executor, settings(tmp_path / "identity"))

    assert captured["workflow_path"] == str(Path.cwd())


def test_unallowlisted_rule_fails_before_any_host_validation(tmp_path):
    class Source:
        validated = False

        def validate_job(self, job):
            self.validated = True

    source = Source()
    executor = bare_executor(settings(tmp_path / "missing-key"), source)
    with pytest.raises(WorkflowError, match="not in guix-openstack-rules"):
        executor.run_job(job("upstream"))
    assert not source.validated


def test_missing_identity_fails_before_cloud_preflight(tmp_path):
    class Source:
        validated = False

        def validate_job(self, job):
            self.validated = True

    source = Source()
    executor = bare_executor(settings(tmp_path / "missing-key"), source)
    with pytest.raises(WorkflowError, match="identity file does not exist"):
        executor.run_job(job())
    assert not source.validated


def test_allowed_job_dispatches_to_ssh_implementation_once(tmp_path, monkeypatch):
    identity = tmp_path / "identity"
    identity.write_text("private-key-placeholder")

    class Source:
        started_at = None

        def validate_job(self, job):
            pass

    executor = bare_executor(settings(identity), Source())
    executor._hosts = lambda: [object()]
    calls = []
    monkeypatch.setattr(
        "snakemake_executor_plugin_guix_openstack.GuixSSHExecutor._run_job",
        lambda self, job: calls.append(job) or "submitted",
    )
    selected = job()

    assert executor.run_job(selected) == "submitted"
    assert calls == [selected]


def test_flavor_rejection_is_reported_before_base_executor_submission(tmp_path):
    identity = tmp_path / "identity"
    identity.write_text("private-key-placeholder")

    class Source:
        def validate_job(self, job):
            raise ValueError("job does not fit flavor")

    executor = bare_executor(settings(identity), Source())
    with pytest.raises(WorkflowError, match="does not fit flavor"):
        executor.run_job(job())


def test_hard_cap_refuses_additional_jobs(tmp_path, monkeypatch):
    identity = tmp_path / "identity"
    identity.write_text("private-key-placeholder")

    class Source:
        started_at = 0
        validated = False

        def validate_job(self, job):
            self.validated = True

    source = Source()
    executor = bare_executor(settings(identity), source)
    monkeypatch.setattr("snakemake_executor_plugin_guix_openstack.time.monotonic", lambda: 3601)
    with pytest.raises(WorkflowError, match="max-hours elapsed"):
        executor.run_job(job())
    assert not source.validated


def test_hard_cap_is_rechecked_after_serialized_first_acquisition(tmp_path, monkeypatch):
    identity = tmp_path / "identity"
    identity.write_text("private-key-placeholder")

    class Source:
        started_at = None
        validated = False

        def validate_job(self, job):
            self.validated = True

    source = Source()
    executor = bare_executor(settings(identity), source)

    def acquire():
        source.started_at = 0
        return [object()]

    executor._hosts = acquire
    monkeypatch.setattr("snakemake_executor_plugin_guix_openstack.time.monotonic", lambda: 3601)
    with pytest.raises(WorkflowError, match="max-hours elapsed"):
        executor.run_job(job())
    assert source.validated


def test_hard_cap_cancels_and_errors_every_active_job(monkeypatch):
    source = SimpleNamespace(started_at=0)
    executor = bare_executor(settings("/unused"), source)
    cancelled = []
    errors = []
    executor.cancel_jobs = lambda active: cancelled.extend(active)
    executor.report_job_error = lambda active, msg=None: errors.append((active, msg))
    active_jobs = [SimpleNamespace(external_jobid="a"), SimpleNamespace(external_jobid="b")]
    monkeypatch.setattr("snakemake_executor_plugin_guix_openstack.time.monotonic", lambda: 3601)

    async def check():
        return [active async for active in executor.check_active_jobs(active_jobs)]

    remaining = asyncio.run(check())
    assert remaining == []
    assert cancelled == active_jobs
    assert len(errors) == 2
    assert all("max-hours elapsed" in msg for _, msg in errors)
