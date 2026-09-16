from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import os
import shlex
import shutil
import sys
import uuid
from typing import Optional

from snakemake_interface_common.exceptions import WorkflowError
from snakemake_interface_executor_plugins.executors.base import SubmittedJobInfo
from snakemake_interface_executor_plugins.executors.remote import RemoteExecutor
from snakemake_interface_executor_plugins.jobs import JobExecutorInterface
from snakemake_interface_executor_plugins.settings import (
    CommonSettings,
    ExecutorSettingsBase,
)

from .commands import CommandError, Commands
from .lifecycle import Lifecycle, RemoteJob, Status
from .model import Capacity, Host
from .transport import Transport


@dataclass
class ExecutorSettings(ExecutorSettingsBase):
    hosts: list[str] = field(
        default_factory=list,
        metadata={
            "help": "SSH workers as HOST:PORT:ABSOLUTE_WORKDIR",
            "required": True,
            "nargs": "+",
        },
    )
    identity_file: Optional[str] = field(
        default=None, metadata={"help": "SSH identity file"}
    )
    ssh_args: Optional[str] = field(
        default=None, metadata={"help": "Additional SSH arguments"}
    )
    remove_failed: bool = field(
        default=False,
        metadata={"help": "Remove failed remote job directories instead of retaining them"},
    )
    transfer_concurrency: int = field(
        default=2, metadata={"help": "Maximum concurrent file transfers"}
    )
    retries: int = field(
        default=3, metadata={"help": "SSH and transfer attempt limit"}
    )

    @property
    def parsed_hosts(self) -> list[Host]:
        return [Host.parse(value) for value in self.hosts]


common_settings = CommonSettings(
    non_local_exec=True,
    implies_no_shared_fs=True,
    job_deploy_sources=True,
    pass_default_storage_provider_args=False,
    pass_default_resources_args=True,
    pass_envvar_declarations_to_cmd=True,
    auto_deploy_default_storage_provider=False,
    init_seconds_before_status_checks=1,
    can_transfer_local_files=True,
)


def _job_environment(job: JobExecutorInterface):
    """Compatibility adapter pending addition to JobExecutorInterface."""
    environment = getattr(job, "software_env", None)
    if environment is None:
        raise WorkflowError(
            "guix-ssh requires every remote job to declare a Guix software environment"
        )
    realize = getattr(environment, "realize", None)
    if realize is None:
        raise WorkflowError(
            "the selected software deployment plugin does not expose realize(); "
            "use snakemake-software-deployment-plugin-guix>=0.4"
        )
    return realize()


def _store_item(path: Path) -> Path:
    resolved = path.resolve()
    parts = resolved.parts
    try:
        index = parts.index("store")
    except ValueError as error:
        raise WorkflowError(f"executable is not in the Guix store: {resolved}") from error
    if index == 0 or parts[index - 1] != "gnu" or len(parts) <= index + 1:
        raise WorkflowError(f"executable is not in the Guix store: {resolved}")
    return Path(*parts[: index + 2])


class Executor(RemoteExecutor):
    def __post_init__(self):
        settings: ExecutorSettings = self.workflow.executor_settings
        self.hosts = settings.parsed_hosts
        if not self.hosts:
            raise WorkflowError("guix-ssh requires at least one host")
        if len({host.key for host in self.hosts}) != len(self.hosts):
            raise WorkflowError("each Guix SSH host may occur only once")
        self.commands = Commands(
            settings.identity_file, settings.ssh_args, settings.retries
        )
        self.transport = Transport(self.commands, settings.transfer_concurrency)
        self.lifecycle = Lifecycle(self.commands)
        self.run_id = uuid.uuid4().hex
        self._next_host = 0
        controller = shutil.which("snakemake")
        if controller is None:
            raise WorkflowError("cannot locate the Guix-provided snakemake executable")
        self.controller_executable = Path(controller).resolve()
        self.controller_store_item = _store_item(self.controller_executable)

    def get_python_executable(self):
        return shlex.quote(sys.executable)

    def format_job_exec(self, job: JobExecutorInterface) -> str:
        command = super().format_job_exec(job)
        python_invocation = f"{self.get_python_executable()} -m snakemake"
        command = command.replace(
            python_invocation, shlex.quote(str(self.controller_executable)), 1
        )
        return command + " --sdm-guix-profile-cache .snakemake/guix/profiles"

    def run_job(self, job: JobExecutorInterface):
        host = self.hosts[self._next_host % len(self.hosts)]
        self._next_host += 1
        realized = _job_environment(job)
        remote = RemoteJob(
            host,
            host.workdir / self.run_id / str(job.jobid),
            realized.digest,
        )
        try:
            self.commands.guix_copy(host, self.controller_store_item)
            self.transport.deploy_environment(host, realized)
            sources = [os.path.relpath(self.workflow.main_snakefile), *job.input]
            self.transport.stage_inputs(host, remote.directory, sources)
            remote_cache = (
                remote.directory
                / ".snakemake"
                / "guix"
                / "profiles"
                / realized.digest
            )
            self.commands.ssh(
                host,
                f"mkdir -p {shlex.quote(str(remote_cache))} && "
                f"ln -sfn {shlex.quote(str(realized.profile_store_path))} "
                f"{shlex.quote(str(remote_cache / 'profile'))} && "
                f"touch {shlex.quote(str(remote_cache / '.complete'))}",
            )
            self.lifecycle.launch(remote, self.format_job_exec(job))
        except (CommandError, OSError, ValueError) as error:
            raise WorkflowError(f"failed to submit job {job.jobid} to {host}: {error}")
        self.report_job_submission(
            SubmittedJobInfo(job, external_jobid=remote.id, aux={"remote": remote})
        )

    async def check_active_jobs(self, active_jobs):
        for active in active_jobs:
            remote = active.aux["remote"]
            status, message = self.lifecycle.status(remote)
            if status in (Status.RUNNING, Status.UNREACHABLE):
                yield active
            elif status is Status.SUCCEEDED:
                try:
                    self.transport.retrieve_outputs(
                        remote.host, remote.directory, active.job.output
                    )
                except (CommandError, OSError, ValueError) as error:
                    self.report_job_error(active, msg=f"output retrieval failed: {error}")
                    continue
                self.lifecycle.cleanup(remote)
                self.report_job_success(active)
            else:
                self.report_job_error(active, msg=message)
                if self.workflow.executor_settings.remove_failed:
                    self.lifecycle.cleanup(remote)

    def cancel_jobs(self, active_jobs):
        for active in active_jobs:
            try:
                self.lifecycle.cancel(active.aux["remote"])
            except CommandError as error:
                self.logger.warning(f"failed to cancel {active.external_jobid}: {error}")
