from dataclasses import dataclass
from enum import Enum
import json
import shlex
from pathlib import PurePosixPath

from .commands import CommandError, Commands
from .model import Host


class Status(Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class RemoteJob:
    host: Host
    directory: PurePosixPath
    environment_digest: str

    @property
    def id(self) -> str:
        return f"{self.host.hostname}:{self.directory}"


class Lifecycle:
    def __init__(self, commands: Commands) -> None:
        self.commands = commands

    def launch(self, job: RemoteJob, command: str) -> None:
        directory = shlex.quote(str(job.directory))
        metadata = json.dumps(
            {"environment_digest": job.environment_digest}, separators=(",", ":")
        )
        inner = (
            "trap 'code=$?; printf %s \"$code\" > .exit.tmp; "
            "mv .exit.tmp exit' EXIT; " + command
        )
        script = (
            f"mkdir -p {directory} && cd {directory} && "
            f"printf %s {shlex.quote(metadata)} > metadata.json && "
            f"printf %s {shlex.quote(command)} > command && "
            f"nohup setsid bash -c {shlex.quote(inner)} >stdout 2>stderr < /dev/null & "
            "echo $! > pid"
        )
        self.commands.ssh(job.host, script)

    def status(self, job: RemoteJob) -> tuple[Status, str]:
        directory = shlex.quote(str(job.directory))
        script = (
            f"cd {directory} && if test -f exit; then cat exit; "
            "elif test -f pid && kill -0 $(cat pid) 2>/dev/null; then echo RUNNING; "
            "else echo LOST; fi"
        )
        try:
            result = self.commands.ssh(job.host, script)
        except CommandError as error:
            return Status.UNREACHABLE, str(error)
        value = result.stdout.strip()
        if value == "RUNNING":
            return Status.RUNNING, ""
        if value == "0":
            return Status.SUCCEEDED, ""
        logs = self.logs(job)
        return Status.FAILED, logs or f"remote process state is {value!r}"

    def logs(self, job: RemoteJob) -> str:
        directory = shlex.quote(str(job.directory))
        try:
            result = self.commands.ssh(
                job.host,
                f"cd {directory} && tail -n 200 stdout stderr 2>/dev/null || true",
            )
            return result.stdout
        except CommandError as error:
            return str(error)

    def cancel(self, job: RemoteJob) -> None:
        directory = shlex.quote(str(job.directory))
        self.commands.ssh(
            job.host,
            f"cd {directory} && test -f pid && kill -TERM -- -$(cat pid) 2>/dev/null || true",
        )

    def cleanup(self, job: RemoteJob) -> None:
        self.commands.ssh(job.host, f"rm -rf -- {shlex.quote(str(job.directory))}")
