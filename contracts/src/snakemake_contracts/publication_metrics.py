"""Pytest plugin for a module's ``publication_metrics.json`` catalog.

A catalog maps metric names to either ``{"sql": <aggregate expression>}``,
checked by the module's own tests, or ``{"aggregate": <AGG>, "column": <name>}``.
Each file found by collection becomes one test per metric: an ``sql`` entry is
only checked for its shape, an ``aggregate`` entry is executed in DuckDB over a
column with selected, grouped, null, signed and repeated observations.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

CATALOG_NAME = "publication_metrics.json"

ROWS: list[tuple[str, float | None]] = [
    ("selected", -10), ("selected", 90), ("selected", None), ("selected", 0),
    ("other", 1000), ("negative", -10), ("negative", -20), ("null", None),
]
# population -> result of AGG(column) over ROWS; "repeated" is "selected" with every row twice.
EXPECTED: dict[str, dict[str, float | None]] = {
    "MAX": {"selected": 90, "other": 1000, "negative": -10, "null": None, "none": None, "repeated": 90},
    "MIN": {"selected": -10, "other": 1000, "negative": -20, "null": None, "none": None, "repeated": -10},
    "SUM": {"selected": 80, "other": 1000, "negative": -30, "null": None, "none": None, "repeated": 160},
    "AVG": {"selected": 80 / 3, "other": 1000, "negative": -15, "null": None, "none": None, "repeated": 80 / 3},
    "COUNT": {"selected": 3, "other": 1, "negative": 2, "null": 0, "none": 0, "repeated": 6},
}


def check_metric(name: str, definition: Any) -> None:
    """Raise AssertionError unless ``definition`` is a well-formed catalog entry with the aggregate's semantics."""

    assert isinstance(definition, dict), f"{name}: an entry must be a mapping"
    if "sql" in definition:
        assert set(definition) == {"sql"}, f"{name}: an sql entry has no other key"
        assert isinstance(definition["sql"], str) and definition["sql"].strip(), f"{name}: empty sql"
        return
    assert set(definition) == {"aggregate", "column"}, f"{name}: expected sql, or aggregate and column"
    aggregate, column = definition["aggregate"], definition["column"]
    assert aggregate in EXPECTED, f"{name}: aggregate {aggregate!r} not in {sorted(EXPECTED)}"
    assert isinstance(column, str) and column, f"{name}: empty column"

    import duckdb

    quoted = '"' + column.replace('"', '""') + '"'
    expression = f"{aggregate}({quoted})"
    expected = EXPECTED[aggregate]
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE facts (population VARCHAR, {quoted} DOUBLE)")
        con.executemany("INSERT INTO facts VALUES (?, ?)", ROWS)

        def query(where: str) -> Any:
            return con.execute(f"SELECT {expression} FROM facts WHERE {where}").fetchone()[0]  # type: ignore[index]

        for population in ("selected", "other", "negative", "null"):
            assert query(f"population = '{population}'") == pytest.approx(expected[population]), (name, population)
        assert query("FALSE") == expected["none"], (name, "no row")
        grouped = dict(con.execute(f"SELECT population, {expression} FROM facts GROUP BY population").fetchall())
        assert grouped == pytest.approx({p: expected[p] for p in ("selected", "other", "negative", "null")}), name
        con.execute("INSERT INTO facts SELECT * FROM facts")
        assert query("population = 'selected'") == pytest.approx(expected["repeated"]), (name, "repeated rows")


class MetricItem(pytest.Item):
    def __init__(self, *, definition: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.definition = definition

    def runtest(self) -> None:
        check_metric(self.name, self.definition)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.path, None, f"{CATALOG_NAME}::{self.name}"


class CatalogFile(pytest.File):
    def collect(self) -> Iterator[MetricItem]:
        catalog = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(catalog, dict):
            raise self.CollectError(f"{self.path} must contain a mapping of metric names to entries")
        for name, definition in catalog.items():
            yield MetricItem.from_parent(self, name=name, definition=definition)


def pytest_collect_file(file_path: Path, parent: pytest.Collector) -> CatalogFile | None:
    if file_path.name == CATALOG_NAME:
        return CatalogFile.from_parent(parent, path=file_path)
    return None
