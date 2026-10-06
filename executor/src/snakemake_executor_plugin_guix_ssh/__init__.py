from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import os
import hashlib
import json
import shlex
import shutil
import sys
from threading import Lock
import time
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
from .hosts import HostSource, StaticHosts
from .model import Capacity, Host
from .transport import Transport


@dataclass
class SshSettings(ExecutorSettingsBase):
    remote_profile: Optional[str] = field(
        default=None,
        metadata={
            "help": "Remote Guix profile whose etc/profile is sourced before Snakemake starts"
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
    unreachable_timeout: int = field(
        default=600, metadata={"help": "Seconds before an unreachable remote job fails"}
    )

    def __post_init__(self):
        if self.unreachable_timeout < 0:
            raise ValueError("unreachable_timeout must be non-negative")
        if self.remote_profile and not PurePosixPath(self.remote_profile).is_absolute():
            raise ValueError("remote_profile must be an absolute path")


@dataclass
class ExecutorSettings(SshSettings):
    hosts: list[str] = field(
        default_factory=list,
        metadata={
            "help": "SSH workers as HOST:PORT:ABSOLUTE_WORKDIR",
            "required": True,
            "nargs": "+",
        },
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Executor(RemoteExecutor):
    def __post_init__(self):
        settings: ExecutorSettings = self.workflow.executor_settings
        self.commands = Commands(
            settings.identity_file, settings.ssh_args, settings.retries
        )
        self.transport = Transport(self.commands, settings.transfer_concurrency)
        self.lifecycle = Lifecycle(self.commands)
        self.run_id = uuid.uuid4().hex
        self._next_host = 0
        self.host_source: HostSource = self.make_host_source(settings)
        self._hosts_lock = Lock()
        self._cached_hosts: list[Host] | None = None
        self._shutdown_lock = Lock()
        self._released_hosts = False
        self._failed = False
        self._unreachable_since: dict[str, float] = {}
        controller = shutil.which("snakemake")
        if controller is None:
            raise WorkflowError("cannot locate the Guix-provided snakemake executable")
        self.controller_executable = Path(controller).resolve()
        self.controller_store_item = _store_item(self.controller_executable)

    def make_host_source(self, settings: ExecutorSettings) -> HostSource:
        return StaticHosts(settings.hosts)

    def _hosts(self) -> list[Host]:
        with self._hosts_lock:
            if self._cached_hosts is None:
                hosts = self.host_source.acquire()
                self._cached_hosts = list(hosts)
                if not hosts:
                    raise WorkflowError("guix-ssh requires at least one host")
                if len({host.key for host in hosts}) != len(hosts):
                    raise WorkflowError("each Guix SSH host may occur only once")
            return self._cached_hosts

    def report_job_error(self, job_info, msg=None, **kwargs):
        self._failed = True
        return super().report_job_error(job_info, msg=msg, **kwargs)

    def shutdown(self):
        try:
            super().shutdown()
        finally:
            with self._shutdown_lock:
                if not self._released_hosts:
                    try:
                        self.host_source.release(
                            self._cached_hosts or [], failed=self._failed
                        )
                    except BaseException:
                        self.logger.error(
                            "failed to release guix-ssh hosts", exc_info=True
                        )
                        raise
                    self._released_hosts = True

    def get_python_executable(self):
        return shlex.quote(sys.executable)

    def get_job_exec_prefix(self, job: JobExecutorInterface):
        profile = self.workflow.executor_settings.remote_profile
        if not profile:
            return ""
        return f". {shlex.quote(profile.rstrip('/') + '/etc/profile')}"

    def format_job_exec(self, job: JobExecutorInterface) -> str:
        # The remote launcher has already changed to its staged job directory.
        # Pass that directory through to the child Snakemake process instead
        # of making it chdir to the controller's workflow path.
        workflow = self.workflow
        controller_workdir = workflow.overwrite_workdir
        workflow.overwrite_workdir = "."
        try:
            command = super().format_job_exec(job)
        finally:
            workflow.overwrite_workdir = controller_workdir
        python_invocation = f"{self.get_python_executable()} -m snakemake"
        command = command.replace(
            python_invocation, shlex.quote(str(self.controller_executable)), 1
        )
        return command + " --sdm-guix-profile-cache .snakemake/guix/profiles"

    def run_job(self, job: JobExecutorInterface):
        try:
            return self._run_job(job)
        except BaseException:
            self._failed = True
            raise

    def _run_job(self, job: JobExecutorInterface):
        hosts = self._hosts()
        host = hosts[self._next_host % len(hosts)]
        self._next_host += 1
        realized = _job_environment(job)
        remote = RemoteJob(
            host,
            host.workdir / self.run_id / str(job.jobid),
            realized.digest,
        )
        try:
            self.commands.preflight(host)
            self.commands.guix_copy(host, self.controller_store_item)
            self.transport.deploy_environment(host, realized)
            sources = self._workflow_sources(job)
            mapped = self.transport._safe_paths(sources)
            inventory = {
                path: _sha256(Path(path))
                for path in mapped if Path(path).is_file()
            }
            self.transport.stage_inputs(host, remote.directory, sources)
            self.commands.ssh(
                host,
                f"printf %s {shlex.quote(json.dumps(inventory, sort_keys=True))} "
                f"> {shlex.quote(str(remote.directory / 'sources.json'))}",
            )
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

    def _workflow_sources(self, job):
        sources = [os.path.relpath(self.workflow.main_snakefile)]
        try:
            dag_sources = self.workflow.dag.get_sources()
        except TypeError as error:
            # Snakemake 9.27 can pass None-valued software environment
            # attributes to is_local_file(), which calls os.fspath(None).
            if "NoneType" not in str(error):
                raise
            self.logger.warning(
                "Snakemake could not enumerate workflow sources because a "
                "software environment field is unset; collecting local sources directly"
            )
            dag_sources = self._workflow_sources_fallback(job)

        # DAG sources vary across Snakemake releases. The workflow registry
        # also contains parsed includes, config files and rule scripts.
        dag_sources = set(dag_sources) | self._workflow_sources_fallback(job)

        for source in sorted(dag_sources):
            source = os.fspath(source)
            if os.path.isabs(source):
                source = os.path.relpath(source)
            if source == ".." or source.startswith(".." + os.sep):
                raise WorkflowError(f"workflow source is outside the working directory: {source}")
            try:
                if not os.path.isfile(source):
                    raise WorkflowError(f"workflow source is not a regular file: {source}")
                size = os.path.getsize(source)
            except OSError as error:
                raise WorkflowError(f"workflow source is unavailable: {source}: {error}") from error
            if size > 10_000_000:
                declared_inputs = {
                    Path(os.fspath(path)).resolve() for path in job.input
                }
                if Path(source).resolve() not in declared_inputs:
                    raise WorkflowError(
                        f"workflow source {source!r} exceeds 10 MB; declare it as a job input"
                    )
                continue
            sources.append(source)
        sources.extend(os.fspath(path) for path in job.input)
        return list(dict.fromkeys(sources))

    def _workflow_sources_fallback(self, job):
        """Collect sources when Snakemake's DAG helper trips on an unset field."""
        sources = set()

        def add_source(source, basedir=None):
            if source is None:
                return
            get_path = getattr(source, "get_path_or_uri", None)
            if get_path is not None:
                try:
                    source = get_path(secret_free=True)
                except TypeError:
                    source = get_path()
            if source is None:
                return
            try:
                source = os.fspath(source)
            except TypeError:
                return
            if "://" in source:
                return
            if basedir and not os.path.isabs(source):
                source = os.path.join(os.fspath(basedir), source)
            try:
                source = os.path.relpath(source)
            except ValueError:
                return
            sources.add(source)

        for source in getattr(self.workflow, "included", ()):
            add_source(source)

        for rule in getattr(self.workflow, "rules", ()):
            script = getattr(rule, "script", None) or getattr(rule, "notebook", None)
            if script:
                basedir = getattr(rule, "basedir", None)
                add_source(script, basedir)

        for configfile in getattr(self.workflow, "configfiles", ()):
            add_source(configfile)

        dag_jobs = getattr(self.workflow.dag, "jobs", (job,))
        for dag_job in dag_jobs:
            spec = getattr(dag_job, "software_env_spec", None)
            if spec is None:
                continue
            attributes = getattr(spec, "source_path_attributes", None)
            if attributes is None:
                continue
            for attribute in attributes():
                add_source(
                    getattr(spec, attribute, None),
                    getattr(getattr(dag_job, "rule", None), "basedir", None),
                )

        return sources

    def _retrieve_auxiliary_outputs(self, job, remote):
        paths = list(job.log or ())
        benchmark = getattr(job, "benchmark", None)
        if benchmark:
            paths.append(benchmark)
        for path in dict.fromkeys(os.fspath(path) for path in paths):
            try:
                self.transport.retrieve_outputs(remote.host, remote.directory, [path])
            except (CommandError, OSError, ValueError) as error:
                self.logger.warning(
                    f"could not retrieve remote log/benchmark {path!r} for "
                    f"{remote.id}: {error}"
                )

    async def check_active_jobs(self, active_jobs):
        for active in active_jobs:
            remote = active.aux["remote"]
            status, message = self.lifecycle.status(remote)
            job_key = active.external_jobid or remote.id
            if status is Status.UNREACHABLE:
                since = self._unreachable_since.setdefault(job_key, time.monotonic())
                if time.monotonic() - since >= self.workflow.executor_settings.unreachable_timeout:
                    self._unreachable_since.pop(job_key, None)
                    self._retrieve_auxiliary_outputs(active.job, remote)
                    self.report_job_error(
                        active,
                        msg=(
                            f"remote host remained unreachable for "
                            f"{self.workflow.executor_settings.unreachable_timeout} seconds: {message}"
                        ),
                    )
                    if self.workflow.executor_settings.remove_failed:
                        self.lifecycle.cleanup(remote)
                else:
                    yield active
            elif status is Status.RUNNING:
                self._unreachable_since.pop(job_key, None)
                yield active
            elif status is Status.SUCCEEDED:
                self._unreachable_since.pop(job_key, None)
                try:
                    self.transport.retrieve_outputs(
                        remote.host, remote.directory, active.job.output
                    )
                except (CommandError, OSError, ValueError) as error:
                    self._retrieve_auxiliary_outputs(active.job, remote)
                    self.report_job_error(active, msg=f"output retrieval failed: {error}")
                    continue
                self._retrieve_auxiliary_outputs(active.job, remote)
                self.lifecycle.cleanup(remote)
                self.report_job_success(active)
            else:
                self._unreachable_since.pop(job_key, None)
                self._retrieve_auxiliary_outputs(active.job, remote)
                self.report_job_error(active, msg=message)
                if self.workflow.executor_settings.remove_failed:
                    self.lifecycle.cleanup(remote)

    def cancel_jobs(self, active_jobs):
        if active_jobs:
            self._failed = True
        for active in active_jobs:
            try:
                self.lifecycle.cancel(active.aux["remote"])
            except CommandError as error:
                self.logger.warning(f"failed to cancel {active.external_jobid}: {error}")
