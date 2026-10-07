from __future__ import annotations

import runpy
import types
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "wrapper"))
sys.path.insert(0, str(ROOT / "src"))

from snakemake_contracts_wrapper import build_argv, namespace_flag, render_shell, snake_to_kebab


WRAPPER_SCRIPT = ROOT / "wrapper" / "snakemake_contracts_wrapper" / "snakemake_wrapper" / "wrapper.py"


class WrapperCommandTests(unittest.TestCase):
    def test_snake_to_kebab(self) -> None:
        self.assertEqual(snake_to_kebab("rp2019_f09_87"), "rp2019-f09-87")

    def test_namespace_flag(self) -> None:
        self.assertEqual(namespace_flag("input", "rp_stock"), "--rp-stock")
        self.assertEqual(namespace_flag("output", "m2_86_inv"), "--output-m2-86-inv")
        self.assertEqual(namespace_flag("output", "output"), "--output")

    def test_build_argv_excludes_script_and_expands_names(self) -> None:
        argv = build_argv(
            ["python3", "/tmp/build_joint.py"],
            input={"script": "/tmp/build_joint.py", "rp_stock": "/data/rp_stock.csv"},
            output={"f09": "/tmp/out.parquet"},
            params={"mc_samples": 10},
        )
        self.assertEqual(
            argv,
            [
                "python3",
                "/tmp/build_joint.py",
                "--rp-stock",
                "/data/rp_stock.csv",
                "--output-f09",
                "/tmp/out.parquet",
                "--mc-samples",
                "10",
            ],
        )

    def test_build_argv_handles_log_namespace(self) -> None:
        argv = build_argv(
            "python3",
            input={"sample": "/tmp/sample.csv"},
            output={"result": "/tmp/out.csv"},
            log={"log": "/tmp/run.log"},
            output_prefix="",
        )
        self.assertEqual(
            argv,
            [
                "python3",
                "--sample",
                "/tmp/sample.csv",
                "--result",
                "/tmp/out.csv",
                "--log",
                "/tmp/run.log",
            ],
        )

    def test_build_argv_expands_sequences(self) -> None:
        argv = build_argv(
            "python3",
            input={"reads": [Path("/tmp/r1.fastq"), Path("/tmp/r2.fastq")]},
        )
        self.assertEqual(
            argv,
            [
                "python3",
                "--reads",
                "/tmp/r1.fastq",
                "--reads",
                "/tmp/r2.fastq",
            ],
        )

    def test_build_argv_output_key_named_output(self) -> None:
        argv = build_argv(
            ["python3", "/tmp/parse.py"],
            input={"script": "/tmp/parse.py", "input": "/tmp/in.txt"},
            output={"output": "/tmp/out.csv"},
            log={"log": "/tmp/run.log"},
        )
        self.assertEqual(
            argv,
            [
                "python3",
                "/tmp/parse.py",
                "--input",
                "/tmp/in.txt",
                "--output",
                "/tmp/out.csv",
                "--log",
                "/tmp/run.log",
            ],
        )

    def test_build_argv_script_keyword(self) -> None:
        argv = build_argv(
            script="/tmp/parse.py",
            input={"input": "/tmp/in.txt"},
            output={"output": "/tmp/out.csv"},
            log={"log": "/tmp/run.log"},
        )
        self.assertEqual(
            argv,
            [
                "/tmp/parse.py",
                "--input", "/tmp/in.txt",
                "--output", "/tmp/out.csv",
                "--log", "/tmp/run.log",
            ],
        )

    def test_build_argv_script_and_command_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_argv("python3", script="/tmp/parse.py")

    def test_build_argv_neither_script_nor_command_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_argv()

    def test_render_shell_quotes(self) -> None:
        command = render_shell(
            ["python3", "/tmp/build joint.py"],
            input={"sample_name": "a b"},
        )
        self.assertIn("'/tmp/build joint.py'", command)
        self.assertIn("--sample-name", command)
        self.assertIn("'a b'", command)

    def test_snakemake_wrapper_cache_does_not_imply_log_arg(self) -> None:
        commands: list[str] = []
        shell_module = types.ModuleType("snakemake.shell")
        setattr(shell_module, "shell", lambda cmd, **kwargs: commands.append(cmd))
        sys.modules["snakemake"] = types.ModuleType("snakemake")
        sys.modules["snakemake.shell"] = shell_module
        snakemake = types.SimpleNamespace(
            input={"script": "/tmp/parse.py", "input": "/tmp/in.txt"},
            output={"output": "/tmp/out.txt"},
            log={},
            params={},
            threads=1,
            config={"cache": "/tmp/cache"},
        )

        try:
            runpy.run_path(str(WRAPPER_SCRIPT), init_globals={"snakemake": snakemake})
        finally:
            sys.modules.pop("snakemake.shell", None)
            sys.modules.pop("snakemake", None)

        self.assertEqual(len(commands), 1)
        self.assertNotIn("--log", commands[0])

    def test_snakemake_wrapper_cache_log_requires_opt_in(self) -> None:
        commands: list[str] = []
        shell_module = types.ModuleType("snakemake.shell")
        setattr(shell_module, "shell", lambda cmd, **kwargs: commands.append(cmd))
        sys.modules["snakemake"] = types.ModuleType("snakemake")
        sys.modules["snakemake.shell"] = shell_module
        snakemake = types.SimpleNamespace(
            input={"script": "/tmp/parse.py", "input": "/tmp/in.txt"},
            output={"output": "/tmp/out.txt"},
            log={},
            params={},
            threads=1,
            config={"cache": "/tmp/cache", "scripts_accept_log_arg": True},
        )

        try:
            runpy.run_path(str(WRAPPER_SCRIPT), init_globals={"snakemake": snakemake})
        finally:
            sys.modules.pop("snakemake.shell", None)
            sys.modules.pop("snakemake", None)

        self.assertEqual(len(commands), 1)
        self.assertIn("--log /tmp/cache/logs/parse.log", commands[0])

    def test_snakemake_wrapper_log_opt_in_must_be_boolean_true(self) -> None:
        commands: list[str] = []
        shell_module = types.ModuleType("snakemake.shell")
        setattr(shell_module, "shell", lambda cmd, **kwargs: commands.append(cmd))
        sys.modules["snakemake"] = types.ModuleType("snakemake")
        sys.modules["snakemake.shell"] = shell_module
        snakemake = types.SimpleNamespace(
            input={"script": "/tmp/parse.py", "input": "/tmp/in.txt"},
            output={"output": "/tmp/out.txt"},
            log={},
            params={},
            threads=1,
            config={"cache": "/tmp/cache", "scripts_accept_log_arg": "true"},
        )

        try:
            runpy.run_path(str(WRAPPER_SCRIPT), init_globals={"snakemake": snakemake})
        finally:
            sys.modules.pop("snakemake.shell", None)
            sys.modules.pop("snakemake", None)

        self.assertEqual(len(commands), 1)
        self.assertNotIn("--log", commands[0])

    def test_snakemake_wrapper_requires_script_input(self) -> None:
        commands: list[str] = []
        shell_module = types.ModuleType("snakemake.shell")
        setattr(shell_module, "shell", lambda cmd, **kwargs: commands.append(cmd))
        sys.modules["snakemake"] = types.ModuleType("snakemake")
        sys.modules["snakemake.shell"] = shell_module
        snakemake = types.SimpleNamespace(
            input={"input": "/tmp/in.txt"},
            output={"output": "/tmp/out.txt"},
            log={},
            params={},
            threads=1,
            config={"cache": "/tmp/cache", "scripts_accept_log_arg": True},
        )

        try:
            with self.assertRaisesRegex(ValueError, "named input 'script'"):
                runpy.run_path(str(WRAPPER_SCRIPT), init_globals={"snakemake": snakemake})
        finally:
            sys.modules.pop("snakemake.shell", None)
            sys.modules.pop("snakemake", None)

        self.assertEqual(commands, [])

    def test_snakemake_wrapper_rejects_non_scalar_script_input(self) -> None:
        commands: list[str] = []
        shell_module = types.ModuleType("snakemake.shell")
        setattr(shell_module, "shell", lambda cmd, **kwargs: commands.append(cmd))
        sys.modules["snakemake"] = types.ModuleType("snakemake")
        sys.modules["snakemake.shell"] = shell_module
        snakemake = types.SimpleNamespace(
            input={"script": ["/tmp/a.py", "/tmp/b.py"]},
            output={"output": "/tmp/out.txt"},
            log={},
            params={},
            threads=1,
            config={},
        )

        try:
            with self.assertRaisesRegex(ValueError, "input 'script' to be a path"):
                runpy.run_path(str(WRAPPER_SCRIPT), init_globals={"snakemake": snakemake})
        finally:
            sys.modules.pop("snakemake.shell", None)
            sys.modules.pop("snakemake", None)

        self.assertEqual(commands, [])

    def test_snakemake_wrapper_rejects_non_path_cache(self) -> None:
        commands: list[str] = []
        shell_module = types.ModuleType("snakemake.shell")
        setattr(shell_module, "shell", lambda cmd, **kwargs: commands.append(cmd))
        sys.modules["snakemake"] = types.ModuleType("snakemake")
        sys.modules["snakemake.shell"] = shell_module
        snakemake = types.SimpleNamespace(
            input={"script": "/tmp/parse.py"},
            output={"output": "/tmp/out.txt"},
            log={},
            params={},
            threads=1,
            config={"cache": True, "scripts_accept_log_arg": True},
        )

        try:
            with self.assertRaisesRegex(ValueError, "config 'cache' to be a path"):
                runpy.run_path(str(WRAPPER_SCRIPT), init_globals={"snakemake": snakemake})
        finally:
            sys.modules.pop("snakemake.shell", None)
            sys.modules.pop("snakemake", None)

        self.assertEqual(commands, [])


if __name__ == "__main__":
    unittest.main()
