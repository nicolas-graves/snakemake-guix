"""Snakemake executor that provisions one temporary OpenStack worker per run."""

from dataclasses import dataclass, field
import math
from pathlib import Path, PurePosixPath
import shlex
import socket
import time
from typing import Optional

from snakemake_interface_common.exceptions import WorkflowError
from snakemake_executor_plugin_guix_ssh import (
    Executor as GuixSSHExecutor,
    SshSettings,
    common_settings,
)

from .instance import OpenStackHosts


@dataclass
class ExecutorSettings(SshSettings):
    flavor: Optional[str] = field(default=None, metadata={"help": "OpenStack flavor name or ID", "required": True})
    image: Optional[str] = field(default=None, metadata={"help": "Active Guix worker image name or ID", "required": True})
    max_hours: Optional[float] = field(default=None, metadata={"help": "Hard limit on instance lifetime in hours", "required": True})
    rules: list[str] = field(default_factory=list, metadata={"help": "Rule names allowed to run remotely", "required": True, "nargs": "+"})
    network: str = field(default="Ext-Net", metadata={"help": "OpenStack network for the worker"})
    cloud: Optional[str] = field(default=None, metadata={"help": "clouds.yaml entry (defaults to OS_* environment)"})
    workdir: str = field(default="/var/tmp", metadata={"help": "Remote job root"})
    ssh_args: Optional[str] = field(default="-o ConnectTimeout=5 -o ConnectionAttempts=1", metadata={"help": "Additional SSH arguments"})
    boot_timeout: int = field(default=900, metadata={"help": "Seconds allowed for the worker to boot and accept SSH"})
    on_existing: str = field(default="fail", metadata={"help": "Policy for a live worker belonging to this workflow: fail, adopt, or delete"})
    keep: str = field(default="never", metadata={"help": "Keep the instance never, on-failure, or always (expiry still applies)"})
    name_prefix: str = field(default="snakemake", metadata={"help": "Prefix for the OpenStack server name"})
    identity_file: Optional[str] = field(default=None, metadata={"help": "SSH identity file used by the controller", "required": True})

    def __post_init__(self):
        super().__post_init__()
        for name in ("flavor", "image", "max_hours"):
            if getattr(self, name) is None:
                raise ValueError(f"guix-openstack requires {name.replace('_', '-')} setting")
        if not math.isfinite(self.max_hours) or self.max_hours <= 0:
            raise ValueError("guix-openstack-max-hours must be a finite number greater than zero")
        if not self.rules:
            raise ValueError("guix-openstack-rules must list at least one rule")
        if not self.identity_file:
            raise ValueError("guix-openstack requires guix-openstack-identity-file")
        if self.on_existing not in {"fail", "adopt", "delete"}:
            raise ValueError("guix-openstack-on-existing must be fail, adopt, or delete")
        if self.keep not in {"never", "on-failure", "always"}:
            raise ValueError("guix-openstack-keep must be never, on-failure, or always")
        if self.boot_timeout <= 0:
            raise ValueError("guix-openstack-boot-timeout must be greater than zero")
        if not PurePosixPath(self.workdir).is_absolute():
            raise ValueError("guix-openstack-workdir must be an absolute remote path")


class Executor(GuixSSHExecutor):
    """Guix SSH execution with lazy OpenStack provisioning."""

    def get_job_exec_prefix(self, job):
        profile = (
            self.workflow.executor_settings.remote_profile
            or "/run/current-system/profile"
        )
        profile = shlex.quote(profile.rstrip("/"))
        return (
            f". {profile}/etc/profile && "
            "for site_packages in "
            f"{profile}/lib/python*/site-packages; do "
            'if [ -d "$site_packages" ]; then '
            'PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$site_packages"; '
            "fi; done && export PYTHONPATH"
        )

    def make_host_source(self, settings: ExecutorSettings):
        source = OpenStackHosts(
            settings,
            run_id=self.run_id,
            workflow_path=str(Path.cwd().resolve()),
            controller_host=socket.gethostname(),
            commands=self.commands,
        )
        self.openstack_hosts = source
        return source

    def run_job(self, job):
        try:
            return self._run_job(job)
        except BaseException:
            self._failed = True
            raise

    def _run_job(self, job):
        settings: ExecutorSettings = self.workflow.executor_settings
        if job.rule.name not in settings.rules:
            raise WorkflowError(
                f"rule {job.rule.name!r} is not in guix-openstack-rules; "
                "only explicitly allowlisted rules may use the billed worker"
            )
        identity_file = Path(settings.identity_file).expanduser()
        if not identity_file.is_file():
            raise WorkflowError(f"SSH identity file does not exist: {identity_file}")
        started = getattr(self.openstack_hosts, "started_at", None)
        if started is not None and time.monotonic() - started >= float(settings.max_hours) * 3600:
            raise WorkflowError("guix-openstack-max-hours elapsed; refusing to submit another job")
        try:
            self.openstack_hosts.validate_job(job)
        except (ValueError, RuntimeError) as error:
            raise WorkflowError(str(error)) from error
        self._hosts()
        started = getattr(self.openstack_hosts, "started_at", None)
        if started is not None and time.monotonic() - started >= float(settings.max_hours) * 3600:
            raise WorkflowError("guix-openstack-max-hours elapsed; refusing to submit another job")
        return GuixSSHExecutor._run_job(self, job)

    async def check_active_jobs(self, active_jobs):
        source = self.openstack_hosts
        started = getattr(source, "started_at", None)
        max_seconds = float(self.workflow.executor_settings.max_hours) * 3600
        if started is not None and time.monotonic() - started >= max_seconds:
            for active in list(active_jobs):
                try:
                    self.cancel_jobs([active])
                finally:
                    self.report_job_error(
                        active,
                        msg=(
                            "guix-openstack-max-hours elapsed; the remote job was "
                            "cancelled to stop instance billing"
                        ),
                    )
            return
        async for active in super().check_active_jobs(active_jobs):
            yield active


__all__ = ["Executor", "ExecutorSettings", "common_settings"]
