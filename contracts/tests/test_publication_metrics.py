from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from snakemake_contracts.publication_metrics import EXPECTED, check_metric

pytest_plugins = ["pytester"]


@pytest.mark.parametrize("definition, message", [
    ("SUM", "must be a mapping"),
    ({"sql": "SUM(x)", "column": "x"}, "no other key"),
    ({"sql": " "}, "empty sql"),
    ({"aggregate": "SUM"}, "aggregate and column"),
    ({"aggregate": "MEDIAN", "column": "x"}, "not in"),
    ({"aggregate": "SUM", "column": ""}, "empty column"),
])
def test_malformed_entries_are_rejected(definition: object, message: str) -> None:
    with pytest.raises(AssertionError, match=message):
        check_metric("m", definition)


def test_sql_entries_are_only_checked_for_their_shape() -> None:
    check_metric("m", {"sql": "100.0 * SUM(a) / NULLIF(SUM(b), 0)"})


@pytest.mark.parametrize("aggregate", sorted(EXPECTED))
def test_each_aggregate_has_the_expected_semantics(aggregate: str) -> None:
    pytest.importorskip("duckdb")
    check_metric("m", {"aggregate": aggregate, "column": 'emplois "salariés"'})


def test_a_catalog_file_is_collected_one_test_per_metric(pytester: pytest.Pytester) -> None:
    pytest.importorskip("duckdb")
    pytester.makefile(".json", publication_metrics='{"a": {"aggregate": "MAX", "column": "x"}, "b": {"sql": "SUM(x)"}, '
                                                   '"c": {"aggregate": "MEDIAN", "column": "x"}}')
    result = pytester.runpytest("-p", "snakemake_contracts.publication_metrics")
    result.assert_outcomes(passed=2, failed=1)


def test_exported_directories_of_every_module(tmp_path: Path) -> None:
    from snakemake_contracts.pytest_exports import exported_directories

    for name, provides in (("a", "python:\n  lookups: scripts/lookups.py\n"), ("b", "out: x.csv\n"), ("c", None)):
        module = tmp_path / "modules" / name
        (module / "scripts").mkdir(parents=True)
        (module / "Snakefile").write_text("")
        if provides:
            (module / "provides.yaml").write_text(provides)
    assert exported_directories(tmp_path) == [str((tmp_path / "modules" / "a" / "scripts").resolve())]
