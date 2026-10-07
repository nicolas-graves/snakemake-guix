from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, MutableMapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from snakemake_contracts.contracts import (
    ContractError,
    list_modules,
    load_provides,
    module_context,
    provides,
    validate_repo,
)


class FakeWorkflow:
    def __init__(self, snakefile: Path, config: MutableMapping[str, Any]) -> None:
        self.snakefile = snakefile
        self.config = config
        self.loaded: list[str] = []

    def configfile(self, path: str) -> None:
        self.loaded.append(path)
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(path)
        import yaml

        values = yaml.safe_load(config_path.read_text()) or {}
        self.config.update(values)


class ContractLibraryTests(unittest.TestCase):
    def test_load_provides_and_resolve_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            module_root = repo_root / "modules" / "alpha"
            module_root.mkdir(parents=True)
            (module_root / "Snakefile").write_text("rule all:\n    pass\n")
            (module_root / "provides.yaml").write_text("reads: reads.fastq\nreport: results/report.tsv\n")

            self.assertEqual(
                load_provides("alpha", repo_root),
                {"reads": "reads.fastq", "report": "results/report.tsv"},
            )
            self.assertEqual(
                provides("alpha", "report", repo_root),
                str(module_root / "out" / "results/report.tsv"),
            )

    def test_list_modules_and_validate_repo_use_real_repo_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            good = repo_root / "modules" / "good"
            good.mkdir(parents=True)
            (good / "Snakefile").write_text("rule all:\n    pass\n")
            (good / "provides.yaml").write_text("x: out/x.txt\n")

            ignored = repo_root / "modules" / "ignored"
            ignored.mkdir(parents=True)
            (ignored / "provides.yaml").write_text("bad: 123\n")

            self.assertEqual(list_modules(repo_root), ["good"])
            self.assertEqual(validate_repo(repo_root), [])


class ModuleContextTests(unittest.TestCase):
    def make_module(self, root: Path, name: str = "consumer") -> Path:
        module = root / "modules" / name
        module.mkdir(parents=True)
        snakefile = module / "Snakefile"
        snakefile.write_text("rule all:\n    pass\n")
        return snakefile

    def test_inherited_config_is_not_replaced_by_module_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = self.make_module(Path(tmp))
            (snakefile.parent / "config.yaml").write_text("out: ignored\n")
            config: dict[str, Any] = {"out": "inherited"}
            workflow = FakeWorkflow(snakefile, config)

            context = module_context(workflow, config)

            self.assertEqual(workflow.loaded, [])
            self.assertEqual(context.out_dir, "inherited")

    def test_required_config_loads_absolute_path_and_mutates_context_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = self.make_module(Path(tmp))
            config_path = snakefile.parent / "settings.yaml"
            config_path.write_text("cache: configured-cache\n")
            config: dict[str, Any] = {}
            workflow = FakeWorkflow(snakefile, config)

            context = module_context(workflow, config, configfile="settings.yaml")

            self.assertEqual(workflow.loaded, [str(config_path.resolve())])
            self.assertEqual(context.cache_dir, "configured-cache")

    def test_required_config_delegates_missing_file_error_to_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = self.make_module(Path(tmp))
            workflow = FakeWorkflow(snakefile, {})

            with self.assertRaises(FileNotFoundError):
                module_context(workflow, workflow.config)

    def test_local_defaults_load_existing_config_but_tolerate_missing_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configured_snakefile = self.make_module(root, "configured")
            configured_path = configured_snakefile.parent / "config.yaml"
            configured_path.write_text("data: input-data\n")
            configured_workflow = FakeWorkflow(configured_snakefile, {})

            configured = module_context(
                configured_workflow, configured_workflow.config, standalone="local-defaults"
            )
            self.assertEqual(configured_workflow.loaded, [str(configured_path.resolve())])
            self.assertEqual(configured.data_dir, "input-data")

            default_snakefile = self.make_module(root, "defaulted")
            default_workflow = FakeWorkflow(default_snakefile, {})
            defaulted = module_context(
                default_workflow, default_workflow.config, standalone="local-defaults"
            )
            self.assertEqual(default_workflow.loaded, [])
            self.assertEqual(defaulted.out_dir, str(default_snakefile.parent / "out"))
            self.assertEqual(defaulted.data_dir, str(default_snakefile.parent / "data"))
            self.assertEqual(defaulted.cache_dir, str(default_snakefile.parent / ".cache"))

    def test_directory_access_is_lazy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = self.make_module(Path(tmp))
            config: dict[str, Any] = {"cache": "only-cache"}
            context = module_context(FakeWorkflow(snakefile, config), config)

            self.assertEqual(context.cache_dir, "only-cache")
            with self.assertRaises(KeyError):
                _ = context.out_dir

    def test_out_is_lazy_supports_nested_paths_and_reports_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = self.make_module(Path(tmp), "alpha")
            config: dict[str, Any] = {"out": "/chosen/out"}
            context = module_context(FakeWorkflow(snakefile, config), config)

            self.assertFalse((snakefile.parent / "provides.yaml").exists())
            (snakefile.parent / "provides.yaml").write_text(
                "reads: reads.fastq\nreport: results/report.tsv\n"
            )
            self.assertEqual(context.out("report"), "/chosen/out/results/report.tsv")
            with self.assertRaisesRegex(KeyError, r"alpha:missing.*reads.*report"):
                context.out("missing")

    def test_missing_provides_is_only_an_error_when_out_is_called(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = self.make_module(Path(tmp))
            config: dict[str, Any] = {"out": "out"}
            context = module_context(FakeWorkflow(snakefile, config), config)

            with self.assertRaises(FileNotFoundError):
                context.out("anything")

    def test_require_override_and_fallback_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snakefile = self.make_module(root)
            producer = self.make_module(root, "producer").parent
            (producer / "provides.yaml").write_text("reads: nested/reads.fastq\n")

            for override in (None, ""):
                config: dict[str, Any] = {"out": "unused", "reads": override}
                context = module_context(FakeWorkflow(snakefile, config), config)
                self.assertEqual(context.require("producer", "reads"), str(producer / "out/nested/reads.fastq"))

            absent: dict[str, Any] = {"out": "unused"}
            context = module_context(FakeWorkflow(snakefile, absent), absent)
            self.assertEqual(context.require("producer", "reads"), str(producer / "out/nested/reads.fastq"))

            overridden: dict[str, Any] = {"reads": "/external/reads.fastq"}
            context = module_context(FakeWorkflow(snakefile, overridden), overridden)
            self.assertEqual(context.require("producer", "reads"), "/external/reads.fastq")

    def test_contract_operations_reject_unsupported_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snakefile = Path(tmp) / "elsewhere" / "Snakefile"
            snakefile.parent.mkdir()
            snakefile.write_text("")
            config: dict[str, Any] = {"out": "out"}
            context = module_context(FakeWorkflow(snakefile, config), config)

            with self.assertRaisesRegex(ContractError, r"<repo>/modules/<module>"):
                context.out("x")
            with self.assertRaisesRegex(ContractError, r"<repo>/modules/<module>"):
                context.require("producer", "x")


if __name__ == "__main__":
    unittest.main()
