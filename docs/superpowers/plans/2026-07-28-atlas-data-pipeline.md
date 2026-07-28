# Revolution Idle Atlas — Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data pipeline that validates a hand-maintained
`relationships.yaml` describing Revolution Idle's stat interdependencies, and
renders it to a static `graph.json` the web app will consume.

**Architecture:** A human owns `data/relationships.yaml` outright. `scrape.py`
fetches raw wikitext into `data/raw/` purely so CI can diff it and report what
changed on the wiki — it parses nothing. Throwaway `bootstrap/` scripts seed the
YAML once where extraction is trivial, then are archived. `build.py` validates
the YAML and renders `public/graph.json` plus a `docs/coverage.md` gap report.

**Tech Stack:** Python 3.12, uv, pydantic v2 (schema), PyYAML (parsing with line
numbers), networkx (cycle/SCC detection), httpx (HTTP), pytest.

## Global Constraints

- Python 3.12+. Package management via `uv` only — never `pip` or `poetry`.
- **Topology only.** No coefficients, per-level values, max levels, or any
  numeric game value enters the data model. The `op` field records an operator
  *class* (`add`/`mult`/`exp`) and nothing more.
- `data/relationships.yaml` is the single source of truth. Only a human writes
  to it. No script in `src/` may ever write to it.
- Scripts under `bootstrap/` are throwaway: not tested, not imported by `src/`,
  not run by CI.
- wiki.gg returns **HTTP 403 to the default Python user-agent**. Every request
  must send `User-Agent: revolution-idle-atlas/0.1 (+https://github.com/tobydillman/revolution-idle-atlas)`.
- Wiki API base URL: `https://revolutionidle.wiki.gg/api.php`
- YAML is parsed only through `yaml.SafeLoader` or a subclass of it. The
  line-tracking loader may override the *mapping* constructor and nothing else,
  so SafeLoader's constructor whitelist stays intact. A test asserts that
  `!!python/...` tags still raise.
- Validation errors must fuzzy-match unknown ids against known ids and suggest
  the closest alternative. The validator is the only correctness gate, so its
  error messages carry the ergonomic load.
- All file paths in this plan are relative to `/home/toby/projects/revolution-idle-atlas`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | uv project config, deps, `atlas` console script |
| `src/atlas/models.py` | Pydantic models and enums for Node, Edge, Dataset |
| `src/atlas/loader.py` | YAML → models, attaching source line numbers |
| `src/atlas/problems.py` | `Problem` record + formatting shared by validators |
| `src/atlas/validate.py` | Reference/duplicate/self-edge errors with fuzzy suggestions |
| `src/atlas/rawcheck.py` | Warnings derived from `data/raw/` wikitext (text search only) |
| `src/atlas/coverage.py` | Orphans, cycles, per-system coverage → `docs/coverage.md` |
| `src/atlas/render.py` | Dataset → `public/graph.json` |
| `src/atlas/scrape.py` | MediaWiki bulk wikitext fetch into `data/raw/` |
| `src/atlas/cli.py` | `atlas build` and `atlas scrape` entry points |
| `bootstrap/refine_tree.py` | One-time Refine Tree prerequisite extraction |
| `data/relationships.yaml` | The dataset. Hand-maintained. |
| `data/inventory.yaml` | Optional `{system: [entity-id]}` from IL2CPP enums, for the known-unknowns report |
| `tests/` | pytest suite + YAML/wikitext fixtures |
| `.github/workflows/ci.yml` | Runs tests and `atlas build --check` |

---

### Task 1: Project scaffold, schema models, and line-tracking loader

**Files:**
- Create: `pyproject.toml`
- Create: `src/atlas/__init__.py`
- Create: `src/atlas/models.py`
- Create: `src/atlas/loader.py`
- Test: `tests/test_loader.py`
- Test: `tests/fixtures/minimal.yaml`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `atlas.models.Node`, `atlas.models.Edge`, `atlas.models.Dataset`
  - Enums `System`, `Kind`, `Rel`, `Op`, `NodeConfidence`, `EdgeConfidence`
  - `atlas.loader.load_dataset(path: Path) -> Dataset`
  - `atlas.loader.SchemaError(Exception)` with `.problems: list[str]`
  - `Node.line` / `Edge.line` — 1-based source line, excluded from serialisation

- [ ] **Step 1: Create the uv project and pyproject.toml**

```toml
[project]
name = "revolution-idle-atlas"
version = "0.1.0"
description = "Relationship graph for Revolution Idle"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.9",
    "pyyaml>=6.0",
    "networkx>=3.3",
    "httpx>=0.27",
]

[project.scripts]
atlas = "atlas.cli:main"

[dependency-groups]
dev = ["pytest>=8.3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/atlas"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Then run:

```bash
mkdir -p src/atlas tests/fixtures data/raw public
touch src/atlas/__init__.py
uv sync
```

- [ ] **Step 2: Write the failing test**

Create `tests/fixtures/minimal.yaml`:

```yaml
nodes:
  - id: refine-node-121
    name: Refine Node 121
    system: mineral
    kind: tree-node
    wiki: Minerals/Refine_Tree
    confidence: documented
  - id: singularity
    name: Singularity
    system: singularity
    kind: currency
    wiki: Singularity
    confidence: provisional

edges:
  - from: refine-node-121
    to: singularity
    rel: unlocks
    note: "Singularity is unlocked by Refine Node 121"
    source: wiki:Singularity
    confidence: provisional
```

Create `tests/test_loader.py`:

```python
from pathlib import Path

import pytest
import yaml

from atlas.loader import SchemaError, load_dataset
from atlas.models import EdgeConfidence, Kind, Rel, System

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_nodes_and_edges():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert len(ds.nodes) == 2
    assert len(ds.edges) == 1
    assert ds.nodes[0].id == "refine-node-121"
    assert ds.nodes[0].system is System.MINERAL
    assert ds.nodes[0].kind is Kind.TREE_NODE


def test_edge_from_is_aliased():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    edge = ds.edges[0]
    assert edge.from_ == "refine-node-121"
    assert edge.to == "singularity"
    assert edge.rel is Rel.UNLOCKS
    assert edge.confidence is EdgeConfidence.PROVISIONAL
    assert edge.op is None


def test_line_numbers_are_attached():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert ds.nodes[0].line == 2
    assert ds.edges[0].line == 16


def test_bad_enum_raises_schema_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "nodes:\n"
        "  - id: x\n"
        "    name: X\n"
        "    system: not-a-system\n"
        "    kind: relic\n"
        "edges: []\n"
    )
    with pytest.raises(SchemaError) as exc:
        load_dataset(bad)
    assert any("system" in p for p in exc.value.problems)


def test_python_object_tags_are_rejected(tmp_path):
    """The line-tracking loader must not widen SafeLoader's constructor set."""
    evil = tmp_path / "evil.yaml"
    evil.write_text("nodes: !!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(yaml.YAMLError):
        load_dataset(evil)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.loader'`

- [ ] **Step 4: Write `src/atlas/models.py`**

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class System(StrEnum):
    REVOLUTION = "revolution"
    INFINITY = "infinity"
    ETERNITY = "eternity"
    UNITY = "unity"
    ZODIAC = "zodiac"
    MINERAL = "mineral"
    TAROT = "tarot"
    SINGULARITY = "singularity"
    PLAGUE = "plague"


class Kind(StrEnum):
    RELIC = "relic"
    STAT = "stat"
    TREE_NODE = "tree-node"
    CURRENCY = "currency"
    TAROT_CARD = "tarot-card"
    UPGRADE = "upgrade"
    GROUP = "group"


class Rel(StrEnum):
    BOOSTS = "boosts"
    UNLOCKS = "unlocks"
    REQUIRES = "requires"


class Op(StrEnum):
    ADD = "add"
    MULT = "mult"
    EXP = "exp"


class NodeConfidence(StrEnum):
    DOCUMENTED = "documented"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"


class EdgeConfidence(StrEnum):
    DOCUMENTED = "documented"
    PROVISIONAL = "provisional"
    UNCERTAIN = "uncertain"


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    system: System
    kind: Kind
    wiki: str | None = None
    confidence: NodeConfidence = NodeConfidence.DOCUMENTED
    line: int | None = Field(default=None, exclude=True)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    rel: Rel
    op: Op | None = None
    note: str | None = None
    source: str
    confidence: EdgeConfidence = EdgeConfidence.DOCUMENTED
    line: int | None = Field(default=None, exclude=True)


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}
```

- [ ] **Step 5: Write `src/atlas/loader.py`**

`LINE_KEY` is injected by the YAML loader into every mapping, then popped back
off before pydantic sees the data — pydantic runs with `extra="forbid"`, so a
stray key would be rejected.

```python
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from atlas.models import Dataset

LINE_KEY = "__line__"


class SchemaError(Exception):
    """Raised when relationships.yaml does not match the schema."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(problems))


# Subclasses SafeLoader, so it inherits SafeLoader's constructor whitelist and
# cannot instantiate arbitrary Python types. The only override is the plain
# mapping constructor, which attaches a source line number for error messages.
class _LineLoader(yaml.SafeLoader):
    """SafeLoader that records the source line of every mapping."""


def _construct_mapping(loader: _LineLoader, node: yaml.MappingNode) -> dict[str, Any]:
    loader.flatten_mapping(node)
    mapping = dict(loader.construct_pairs(node, deep=True))
    mapping[LINE_KEY] = node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_dataset(path: Path) -> Dataset:
    # Equivalent to yaml.load(..., Loader=_LineLoader), spelled out so the
    # SafeLoader lineage is the only thing a reader has to verify.
    loader = _LineLoader(path.read_text(encoding="utf-8"))
    try:
        raw = loader.get_single_data()
    finally:
        loader.dispose()
    if raw is None:
        raw = {}
    raw.pop(LINE_KEY, None)

    lines: dict[str, list[int | None]] = {}
    for section in ("nodes", "edges"):
        items = raw.get(section) or []
        section_lines: list[int | None] = []
        for item in items:
            if isinstance(item, dict):
                section_lines.append(item.pop(LINE_KEY, None))
            else:
                section_lines.append(None)
        lines[section] = section_lines

    try:
        dataset = Dataset.model_validate(raw)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        raise SchemaError(problems) from exc

    for node, line in zip(dataset.nodes, lines["nodes"], strict=True):
        node.line = line
    for edge, line in zip(dataset.edges, lines["edges"], strict=True):
        edge.line = line

    return dataset
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_loader.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/atlas tests/
git commit -m "feat: add dataset schema and line-tracking YAML loader"
```

---

### Task 2: Reference validation with fuzzy suggestions

**Files:**
- Create: `src/atlas/problems.py`
- Create: `src/atlas/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `atlas.models.Dataset`, `atlas.loader.load_dataset`
- Produces:
  - `atlas.problems.Problem` — frozen dataclass with `severity`, `line`, `message`
  - `atlas.problems.Problem.render(path: str) -> str`
  - `atlas.validate.validate_dataset(ds: Dataset) -> list[Problem]` (errors only)
  - `atlas.validate.suggest(unknown: str, known: Iterable[str]) -> str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validate.py`:

```python
from atlas.models import Dataset, Edge, Node
from atlas.validate import suggest, validate_dataset


def _node(node_id: str, line: int | None = None) -> Node:
    return Node(id=node_id, name=node_id, system="unity", kind="relic", line=line)


def _edge(src: str, dst: str, line: int | None = None) -> Edge:
    return Edge(
        **{"from": src, "to": dst, "rel": "boosts", "source": "observed", "line": line}
    )


def test_clean_dataset_has_no_problems():
    ds = Dataset(nodes=[_node("relic-69"), _node("atoms-gain")],
                 edges=[_edge("relic-69", "atoms-gain")])
    assert validate_dataset(ds) == []


def test_dangling_reference_is_an_error():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("relic-96", "relic-69", line=12)])
    problems = validate_dataset(ds)
    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].line == 12
    assert "relic-96" in problems[0].message


def test_dangling_reference_suggests_closest_id():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("relic-96", "relic-69")])
    problems = validate_dataset(ds)
    assert "did you mean 'relic-69'?" in problems[0].message


def test_no_suggestion_when_nothing_is_close():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("zzzzzzzz", "relic-69")])
    assert "did you mean" not in validate_dataset(ds)[0].message


def test_duplicate_node_ids_are_an_error():
    ds = Dataset(nodes=[_node("relic-69", line=2), _node("relic-69", line=8)], edges=[])
    problems = validate_dataset(ds)
    assert len(problems) == 1
    assert "duplicate node id 'relic-69'" in problems[0].message
    assert problems[0].line == 8


def test_self_edge_is_an_error():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("relic-69", "relic-69")])
    problems = validate_dataset(ds)
    assert len(problems) == 1
    assert "self-edge" in problems[0].message


def test_both_endpoints_dangling_reports_twice():
    ds = Dataset(nodes=[_node("a")], edges=[_edge("x", "y")])
    assert len(validate_dataset(ds)) == 2


def test_suggest_returns_none_for_empty_candidates():
    assert suggest("anything", []) is None


def test_problem_render_includes_path_and_line():
    ds = Dataset(nodes=[_node("a")], edges=[_edge("b", "a", line=42)])
    rendered = validate_dataset(ds)[0].render("data/relationships.yaml")
    assert rendered.startswith("data/relationships.yaml:42  error  ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.validate'`

- [ ] **Step 3: Write `src/atlas/problems.py`**

```python
from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    severity: Severity
    message: str
    line: int | None = None

    def render(self, path: str) -> str:
        location = f"{path}:{self.line}" if self.line is not None else path
        return f"{location}  {self.severity}  {self.message}"
```

- [ ] **Step 4: Write `src/atlas/validate.py`**

```python
import difflib
from collections.abc import Iterable

from atlas.models import Dataset
from atlas.problems import Problem


def suggest(unknown: str, known: Iterable[str]) -> str | None:
    matches = difflib.get_close_matches(unknown, list(known), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _unknown_ref(field: str, ref: str, known: Iterable[str], line: int | None) -> Problem:
    message = f"edge {field} references unknown node id '{ref}'"
    hint = suggest(ref, known)
    if hint is not None:
        message += f" — did you mean '{hint}'?"
    return Problem(severity="error", message=message, line=line)


def validate_dataset(ds: Dataset) -> list[Problem]:
    problems: list[Problem] = []

    seen: set[str] = set()
    for node in ds.nodes:
        if node.id in seen:
            problems.append(
                Problem(
                    severity="error",
                    message=f"duplicate node id '{node.id}'",
                    line=node.line,
                )
            )
        seen.add(node.id)

    known = ds.node_ids()
    for edge in ds.edges:
        if edge.from_ not in known:
            problems.append(_unknown_ref("from", edge.from_, known, edge.line))
        if edge.to not in known:
            problems.append(_unknown_ref("to", edge.to, known, edge.line))
        if edge.from_ == edge.to:
            problems.append(
                Problem(
                    severity="error",
                    message=f"self-edge on '{edge.from_}'",
                    line=edge.line,
                )
            )

    return problems
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add src/atlas/problems.py src/atlas/validate.py tests/test_validate.py
git commit -m "feat: add reference validation with fuzzy id suggestions"
```

---

### Task 3: Raw-wikitext warnings

**Files:**
- Create: `src/atlas/rawcheck.py`
- Test: `tests/test_rawcheck.py`

**Interfaces:**
- Consumes: `atlas.models.Dataset`, `atlas.problems.Problem`
- Produces:
  - `atlas.rawcheck.raw_filename(wiki: str) -> str` — `"Minerals/Refine_Tree"` → `"Minerals__Refine_Tree.wikitext"`
  - `atlas.rawcheck.check_against_raw(ds: Dataset, raw_dir: Path) -> list[Problem]` (warnings only)

Warnings emitted:
1. A node whose wiki page contains `{{New Content}}` but whose `confidence` is
   not `provisional`.
2. A node whose `wiki:` page has no corresponding file in `data/raw/`.

If `raw_dir` does not exist, return `[]` — a fresh checkout with no scrape yet
must not fail the build.

The `wiki` field may carry a `#Section` anchor (`Relics#Relic_3`); only the part
before `#` names the page. Slashes become `__` so subpages stay flat on disk.

- [ ] **Step 1: Write the failing test**

Create `tests/test_rawcheck.py`:

```python
from pathlib import Path

from atlas.models import Dataset, Node
from atlas.rawcheck import check_against_raw, raw_filename


def _node(node_id: str, wiki: str | None, confidence: str = "documented") -> Node:
    return Node(
        id=node_id, name=node_id, system="unity", kind="relic",
        wiki=wiki, confidence=confidence, line=3,
    )


def test_raw_filename_flattens_subpages():
    assert raw_filename("Minerals/Refine_Tree") == "Minerals__Refine_Tree.wikitext"


def test_raw_filename_drops_section_anchor():
    assert raw_filename("Relics#Relic_3") == "Relics.wikitext"


def test_missing_raw_dir_yields_no_warnings(tmp_path):
    ds = Dataset(nodes=[_node("a", "Relics")], edges=[])
    assert check_against_raw(ds, tmp_path / "absent") == []


def test_new_content_page_without_provisional_warns(tmp_path):
    (tmp_path / "Singularity.wikitext").write_text("{{New Content}}\nSingularity is...")
    ds = Dataset(nodes=[_node("singularity", "Singularity", "documented")], edges=[])
    problems = check_against_raw(ds, tmp_path)
    assert len(problems) == 1
    assert problems[0].severity == "warning"
    assert "{{New Content}}" in problems[0].message
    assert problems[0].line == 3


def test_new_content_page_with_provisional_is_quiet(tmp_path):
    (tmp_path / "Singularity.wikitext").write_text("{{New Content}}\nSingularity is...")
    ds = Dataset(nodes=[_node("singularity", "Singularity", "provisional")], edges=[])
    assert check_against_raw(ds, tmp_path) == []


def test_missing_page_warns(tmp_path):
    (tmp_path / "Relics.wikitext").write_text("stuff")
    ds = Dataset(nodes=[_node("gone", "DeletedPage")], edges=[])
    problems = check_against_raw(ds, tmp_path)
    assert len(problems) == 1
    assert "DeletedPage" in problems[0].message
    assert "no longer exists" in problems[0].message


def test_node_without_wiki_is_skipped(tmp_path):
    (tmp_path / "Relics.wikitext").write_text("stuff")
    ds = Dataset(nodes=[_node("stub", None, "unknown")], edges=[])
    assert check_against_raw(ds, tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rawcheck.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.rawcheck'`

- [ ] **Step 3: Write `src/atlas/rawcheck.py`**

```python
from pathlib import Path

from atlas.models import Dataset, NodeConfidence
from atlas.problems import Problem

NEW_CONTENT_MARKER = "{{New Content}}"


def raw_filename(wiki: str) -> str:
    page = wiki.split("#", 1)[0]
    return page.replace("/", "__") + ".wikitext"


def check_against_raw(ds: Dataset, raw_dir: Path) -> list[Problem]:
    if not raw_dir.is_dir():
        return []

    problems: list[Problem] = []
    for node in ds.nodes:
        if node.wiki is None:
            continue

        page_file = raw_dir / raw_filename(node.wiki)
        if not page_file.is_file():
            problems.append(
                Problem(
                    severity="warning",
                    message=(
                        f"node '{node.id}' points at wiki page "
                        f"'{node.wiki}' which no longer exists in data/raw/"
                    ),
                    line=node.line,
                )
            )
            continue

        text = page_file.read_text(encoding="utf-8")
        if NEW_CONTENT_MARKER in text and node.confidence is not NodeConfidence.PROVISIONAL:
            problems.append(
                Problem(
                    severity="warning",
                    message=(
                        f"node '{node.id}' sources from a {NEW_CONTENT_MARKER} page "
                        f"but confidence is '{node.confidence}' — expected 'provisional'"
                    ),
                    line=node.line,
                )
            )

    return problems
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rawcheck.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/atlas/rawcheck.py tests/test_rawcheck.py
git commit -m "feat: warn on WIP-flag drift and missing wiki pages"
```

---

### Task 4: Coverage report

**Files:**
- Create: `src/atlas/coverage.py`
- Test: `tests/test_coverage.py`

**Interfaces:**
- Consumes: `atlas.models.Dataset`
- Produces:
  - `atlas.coverage.CoverageReport` — dataclass with `orphans: list[str]`,
    `cycles: list[list[str]]`, `per_system: dict[str, tuple[int, int]]`,
    `stub_count: int`, `missing_entities: dict[str, list[str]]`
  - `atlas.coverage.load_inventory(path: Path) -> dict[str, list[str]]`
  - `atlas.coverage.analyse(ds, inventory=None) -> CoverageReport`
  - `atlas.coverage.render_markdown(report: CoverageReport) -> str`

Cycles are reported as **strongly connected components of size > 1**, not
enumerated simple cycles. Enumerating every cycle can blow up combinatorially;
SCCs are bounded by node count and answer the useful question ("these nodes form
a feedback loop"). `per_system` maps system name to `(connected, total)`.

`missing_entities` implements the spec's known-unknowns report: entity ids the
game's IL2CPP enums prove exist but which the YAML has no node for. The enum
inventory lives in `data/inventory.yaml` — a hand-transcribed
`{system: [id, ...]}` mapping, since the dump itself is a large binary artefact
not worth checking in. The file is **optional**: when absent, `analyse` receives
`inventory=None` and the report section is omitted entirely. This mirrors
`rawcheck.check_against_raw`, which returns `[]` when `data/raw/` is missing —
a pipeline stage that depends on an optional local artefact degrades to silence
rather than failing the build.

- [ ] **Step 1: Write the failing test**

Create `tests/test_coverage.py`:

```python
from atlas.coverage import analyse, load_inventory, render_markdown
from atlas.models import Dataset, Edge, Node


def _node(node_id: str, system: str = "unity", confidence: str = "documented") -> Node:
    return Node(id=node_id, name=node_id, system=system, kind="relic",
                confidence=confidence)


def _edge(src: str, dst: str) -> Edge:
    return Edge(**{"from": src, "to": dst, "rel": "boosts", "source": "observed"})


def test_orphans_are_nodes_with_no_edges():
    ds = Dataset(
        nodes=[_node("a"), _node("b"), _node("lonely")],
        edges=[_edge("a", "b")],
    )
    assert analyse(ds).orphans == ["lonely"]


def test_orphan_detection_counts_incoming_edges():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    assert analyse(ds).orphans == []


def test_feedback_loop_is_reported_as_a_cycle():
    ds = Dataset(
        nodes=[_node("gold"), _node("upgrade")],
        edges=[_edge("gold", "upgrade"), _edge("upgrade", "gold")],
    )
    cycles = analyse(ds).cycles
    assert len(cycles) == 1
    assert sorted(cycles[0]) == ["gold", "upgrade"]


def test_acyclic_graph_reports_no_cycles():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    assert analyse(ds).cycles == []


def test_per_system_counts_connected_and_total():
    ds = Dataset(
        nodes=[_node("a", "unity"), _node("b", "unity"), _node("c", "tarot")],
        edges=[_edge("a", "b")],
    )
    per_system = analyse(ds).per_system
    assert per_system["unity"] == (2, 2)
    assert per_system["tarot"] == (0, 1)


def test_stub_count_counts_unknown_confidence():
    ds = Dataset(
        nodes=[_node("a"), _node("b", confidence="unknown")],
        edges=[],
    )
    assert analyse(ds).stub_count == 1


def test_markdown_mentions_orphans_and_cycles():
    ds = Dataset(
        nodes=[_node("gold"), _node("upgrade"), _node("lonely")],
        edges=[_edge("gold", "upgrade"), _edge("upgrade", "gold")],
    )
    md = render_markdown(analyse(ds))
    assert "lonely" in md
    assert "Feedback loops" in md
    assert "Orphan nodes" in md


def test_inventory_entities_absent_from_yaml_are_reported():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    inventory = {"unity": ["relic-1", "relic-2"], "tarot": ["the-fool"]}
    missing = analyse(ds, inventory=inventory).missing_entities
    assert missing == {"unity": ["relic-2"], "tarot": ["the-fool"]}


def test_fully_covered_system_is_absent_from_missing_entities():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    inventory = {"unity": ["relic-1"]}
    assert analyse(ds, inventory=inventory).missing_entities == {}


def test_missing_entities_empty_without_inventory():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    assert analyse(ds).missing_entities == {}


def test_markdown_omits_known_unknowns_section_without_inventory():
    md = render_markdown(analyse(Dataset(nodes=[_node("a")], edges=[])))
    assert "Known unknowns" not in md


def test_markdown_lists_known_unknowns_when_inventory_given():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    md = render_markdown(analyse(ds, inventory={"unity": ["relic-1", "relic-2"]}))
    assert "Known unknowns" in md
    assert "relic-2" in md


def test_load_inventory_returns_none_when_file_absent(tmp_path):
    assert load_inventory(tmp_path / "nope.yaml") is None


def test_load_inventory_reads_system_to_ids_mapping(tmp_path):
    path = tmp_path / "inventory.yaml"
    path.write_text("unity:\n  - relic-1\n  - relic-2\n")
    assert load_inventory(path) == {"unity": ["relic-1", "relic-2"]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.coverage'`

- [ ] **Step 3: Write `src/atlas/coverage.py`**

```python
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import yaml

from atlas.models import Dataset, NodeConfidence


@dataclass
class CoverageReport:
    orphans: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    per_system: dict[str, tuple[int, int]] = field(default_factory=dict)
    stub_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    missing_entities: dict[str, list[str]] = field(default_factory=dict)
    has_inventory: bool = False


def load_inventory(path: Path) -> dict[str, list[str]] | None:
    """Read the optional IL2CPP entity inventory. None when the file is absent."""
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _build_graph(ds: Dataset) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(n.id for n in ds.nodes)
    known = ds.node_ids()
    for edge in ds.edges:
        if edge.from_ in known and edge.to in known:
            graph.add_edge(edge.from_, edge.to)
    return graph


def analyse(
    ds: Dataset, inventory: dict[str, list[str]] | None = None
) -> CoverageReport:
    graph = _build_graph(ds)

    orphans = sorted(n for n in graph.nodes if graph.degree(n) == 0)

    cycles = sorted(
        (sorted(component) for component in nx.strongly_connected_components(graph)
         if len(component) > 1),
        key=lambda component: (-len(component), component[0]),
    )

    per_system: dict[str, tuple[int, int]] = {}
    for node in ds.nodes:
        connected, total = per_system.get(node.system, (0, 0))
        is_connected = graph.degree(node.id) > 0
        per_system[node.system] = (connected + int(is_connected), total + 1)

    stub_count = sum(
        1 for n in ds.nodes if n.confidence is NodeConfidence.UNKNOWN
    )

    known = ds.node_ids()
    missing_entities = {}
    for system, entity_ids in (inventory or {}).items():
        absent = sorted(e for e in entity_ids if e not in known)
        if absent:
            missing_entities[system] = absent

    return CoverageReport(
        orphans=orphans,
        cycles=cycles,
        per_system=per_system,
        stub_count=stub_count,
        node_count=len(ds.nodes),
        edge_count=len(ds.edges),
        missing_entities=missing_entities,
        has_inventory=inventory is not None,
    )


def render_markdown(report: CoverageReport) -> str:
    lines = [
        "# Coverage report",
        "",
        "Generated by `atlas build`. Do not edit by hand.",
        "",
        f"- Nodes: {report.node_count}",
        f"- Edges: {report.edge_count}",
        f"- Stubs (confidence `unknown`): {report.stub_count}",
        "",
        "## Per-system coverage",
        "",
        "| System | Connected | Total | Coverage |",
        "|---|---|---|---|",
    ]
    for system in sorted(report.per_system):
        connected, total = report.per_system[system]
        pct = (100 * connected // total) if total else 0
        lines.append(f"| {system} | {connected} | {total} | {pct}% |")

    lines += ["", "## Orphan nodes", ""]
    if report.orphans:
        lines.append("Nodes with no edges in either direction — the curation to-do list.")
        lines.append("")
        lines += [f"- `{node_id}`" for node_id in report.orphans]
    else:
        lines.append("None.")

    lines += ["", "## Feedback loops", ""]
    if report.cycles:
        lines.append("Strongly connected components. These are real game mechanics, not errors.")
        lines.append("")
        for component in report.cycles:
            lines.append("- " + " → ".join(f"`{n}`" for n in component))
    else:
        lines.append("None.")

    if report.has_inventory:
        lines += ["", "## Known unknowns", ""]
        if report.missing_entities:
            lines.append(
                "Entities the game's enums prove exist but which have no node yet."
            )
            lines.append("")
            for system in sorted(report.missing_entities):
                lines.append(f"### {system}")
                lines.append("")
                lines += [f"- `{e}`" for e in report.missing_entities[system]]
                lines.append("")
            lines.pop()
        else:
            lines.append("None — every inventoried entity has a node.")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_coverage.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/atlas/coverage.py tests/test_coverage.py
git commit -m "feat: add coverage report with orphan and feedback-loop detection"
```

---

### Task 5: Render graph.json and wire the `atlas build` CLI

**Files:**
- Create: `src/atlas/render.py`
- Create: `src/atlas/cli.py`
- Test: `tests/test_render.py`
- Test: `tests/test_cli_build.py`
- Test: `tests/fixtures/expected_graph.json`

**Interfaces:**
- Consumes: `atlas.models.Dataset`, `atlas.loader.load_dataset`,
  `atlas.validate.validate_dataset`, `atlas.rawcheck.check_against_raw`,
  `atlas.coverage.analyse`, `atlas.coverage.render_markdown`
- Produces:
  - `atlas.render.to_graph(ds: Dataset) -> dict` — deterministic, key-sorted
  - `atlas.cli.main(argv: list[str] | None = None) -> int`
  - `atlas build [--check]` — `--check` validates and reports without writing

`graph.json` is a neutral `{nodes, edges}` shape, deliberately **not** Cytoscape's
`elements` format. Keeping the data contract independent of the rendering library
means swapping libraries later does not require re-rendering the dataset, and it
keeps the golden-file test readable. The app transforms on load.

Node/edge dicts omit `None` fields so the artifact stays small and diffs stay
readable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render.py`:

```python
import json

from atlas.loader import load_dataset
from atlas.render import to_graph
from tests.test_coverage import _edge, _node  # noqa: F401
from atlas.models import Dataset

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_graph_has_schema_version_and_counts():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    graph = to_graph(ds)
    assert graph["version"] == 1
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1


def test_edge_uses_from_not_from_underscore():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    edge = to_graph(ds)["edges"][0]
    assert edge["from"] == "a"
    assert "from_" not in edge


def test_none_fields_are_omitted():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    graph = to_graph(ds)
    assert "op" not in graph["edges"][0]
    assert "wiki" not in graph["nodes"][0]


def test_line_numbers_are_not_serialised():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    graph = to_graph(ds)
    assert "line" not in graph["nodes"][0]
    assert "line" not in graph["edges"][0]


def test_output_is_deterministic():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert json.dumps(to_graph(ds)) == json.dumps(to_graph(ds))


def test_matches_golden_file():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    expected = json.loads((FIXTURES / "expected_graph.json").read_text())
    assert to_graph(ds) == expected
```

Create `tests/fixtures/expected_graph.json`:

```json
{
  "version": 1,
  "nodes": [
    {
      "confidence": "documented",
      "id": "refine-node-121",
      "kind": "tree-node",
      "name": "Refine Node 121",
      "system": "mineral",
      "wiki": "Minerals/Refine_Tree"
    },
    {
      "confidence": "provisional",
      "id": "singularity",
      "kind": "currency",
      "name": "Singularity",
      "system": "singularity",
      "wiki": "Singularity"
    }
  ],
  "edges": [
    {
      "confidence": "provisional",
      "from": "refine-node-121",
      "note": "Singularity is unlocked by Refine Node 121",
      "rel": "unlocks",
      "source": "wiki:Singularity",
      "to": "singularity"
    }
  ]
}
```

Create `tests/test_cli_build.py`:

```python
import json
import shutil
from pathlib import Path

from atlas.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    shutil.copy(FIXTURES / "minimal.yaml", tmp_path / "data" / "relationships.yaml")
    return tmp_path


def test_build_writes_graph_and_coverage(tmp_path):
    root = _project(tmp_path)
    assert main(["build", "--root", str(root)]) == 0
    graph = json.loads((root / "public" / "graph.json").read_text())
    assert len(graph["nodes"]) == 2
    assert (root / "docs" / "coverage.md").is_file()


def test_check_mode_writes_nothing(tmp_path):
    root = _project(tmp_path)
    assert main(["build", "--root", str(root), "--check"]) == 0
    assert not (root / "public" / "graph.json").exists()


def test_validation_error_returns_nonzero_and_writes_nothing(tmp_path):
    root = _project(tmp_path)
    (root / "data" / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: a\n"
        "    name: A\n"
        "    system: unity\n"
        "    kind: relic\n"
        "edges:\n"
        "  - from: ghost\n"
        "    to: a\n"
        "    rel: boosts\n"
        "    source: observed\n"
    )
    assert main(["build", "--root", str(root)]) == 1
    assert not (root / "public" / "graph.json").exists()


def test_warnings_do_not_fail_the_build(tmp_path):
    root = _project(tmp_path)
    raw = root / "data" / "raw"
    raw.mkdir()
    (raw / "Singularity.wikitext").write_text("plain text, no marker")
    (raw / "Minerals__Refine_Tree.wikitext").write_text("stuff")
    assert main(["build", "--root", str(root)]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py tests/test_cli_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.render'`

- [ ] **Step 3: Write `src/atlas/render.py`**

```python
from typing import Any

from atlas.models import Dataset

GRAPH_SCHEMA_VERSION = 1


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in sorted(payload.items()) if v is not None}


def to_graph(ds: Dataset) -> dict[str, Any]:
    return {
        "version": GRAPH_SCHEMA_VERSION,
        "nodes": [_clean(n.model_dump(mode="json")) for n in ds.nodes],
        "edges": [_clean(e.model_dump(mode="json", by_alias=True)) for e in ds.edges],
    }
```

- [ ] **Step 4: Write `src/atlas/cli.py`**

```python
import argparse
import json
import sys
from pathlib import Path

from atlas.coverage import analyse, load_inventory, render_markdown
from atlas.loader import SchemaError, load_dataset
from atlas.problems import Problem
from atlas.rawcheck import check_against_raw
from atlas.render import to_graph
from atlas.validate import validate_dataset

DATASET_REL_PATH = Path("data") / "relationships.yaml"


def _report(problems: list[Problem], path: str) -> None:
    for problem in problems:
        print(problem.render(path), file=sys.stderr)


def _build(root: Path, check_only: bool) -> int:
    dataset_path = root / DATASET_REL_PATH
    display_path = str(DATASET_REL_PATH)

    try:
        dataset = load_dataset(dataset_path)
    except FileNotFoundError:
        print(f"{display_path}: not found", file=sys.stderr)
        return 1
    except SchemaError as exc:
        for problem in exc.problems:
            print(f"{display_path}  error  {problem}", file=sys.stderr)
        return 1

    errors = validate_dataset(dataset)
    warnings = check_against_raw(dataset, root / "data" / "raw")
    _report(errors + warnings, display_path)

    if errors:
        print(f"{len(errors)} error(s) — not writing output", file=sys.stderr)
        return 1

    inventory = load_inventory(root / "data" / "inventory.yaml")
    report = analyse(dataset, inventory=inventory)
    print(
        f"ok: {report.node_count} nodes, {report.edge_count} edges, "
        f"{len(report.orphans)} orphans, {len(warnings)} warning(s)"
    )

    if check_only:
        return 0

    graph_path = root / "public" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(to_graph(dataset), indent=2) + "\n", encoding="utf-8")

    coverage_path = root / "docs" / "coverage.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(render_markdown(report), encoding="utf-8")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="validate the dataset and render graph.json")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument(
        "--check", action="store_true", help="validate only; write no files"
    )

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args.root, args.check)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_render.py tests/test_cli_build.py -v`
Expected: 6 passed in test_render, 4 passed in test_cli_build

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add src/atlas/render.py src/atlas/cli.py tests/
git commit -m "feat: render graph.json and add atlas build CLI"
```

---

### Task 6: Wiki scraper

**Files:**
- Create: `src/atlas/scrape.py`
- Modify: `src/atlas/cli.py` (add the `scrape` subcommand)
- Test: `tests/test_scrape.py`

**Interfaces:**
- Consumes: `atlas.rawcheck.raw_filename`
- Produces:
  - `atlas.scrape.USER_AGENT: str`
  - `atlas.scrape.ScrapeError(Exception)`
  - `atlas.scrape.fetch_pages(client: httpx.Client) -> dict[str, str]` — page title → wikitext
  - `atlas.scrape.write_raw(pages: dict[str, str], raw_dir: Path) -> int`
  - `atlas scrape [--root PATH]`

Uses `generator=allpages` with `prop=revisions&rvslots=main` to pull content in
bulk, following `continue` tokens. Namespace 0 only.

**Failing loudly matters here.** A silent empty scrape would delete every file in
`data/raw/`, and the daily PR would show a mass deletion that looks like the wiki
was wiped. `fetch_pages` raises `ScrapeError` on a non-2xx response, and
`write_raw` raises if handed an empty mapping.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scrape.py`:

```python
import httpx
import pytest

from atlas.scrape import USER_AGENT, ScrapeError, fetch_pages, write_raw

PAGE_ONE = {
    "query": {
        "pages": {
            "1": {
                "title": "Relics",
                "revisions": [{"slots": {"main": {"*": "relic text"}}}],
            }
        }
    },
    "continue": {"gapcontinue": "Singularity", "continue": "gapcontinue||"},
}

PAGE_TWO = {
    "query": {
        "pages": {
            "2": {
                "title": "Minerals/Refine Tree",
                "revisions": [{"slots": {"main": {"*": "refine text"}}}],
            }
        }
    }
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sends_descriptive_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json=PAGE_TWO)

    fetch_pages(_client(handler))
    assert seen["ua"] == USER_AGENT
    assert "revolution-idle-atlas" in USER_AGENT


def test_follows_continuation():
    responses = [PAGE_ONE, PAGE_TWO]

    def handler(request):
        return httpx.Response(200, json=responses.pop(0))

    pages = fetch_pages(_client(handler))
    assert pages == {"Relics": "relic text", "Minerals/Refine Tree": "refine text"}


def test_non_200_raises():
    def handler(request):
        return httpx.Response(403, text="forbidden")

    with pytest.raises(ScrapeError, match="403"):
        fetch_pages(_client(handler))


def test_empty_result_raises():
    def handler(request):
        return httpx.Response(200, json={"query": {"pages": {}}})

    with pytest.raises(ScrapeError, match="no pages"):
        fetch_pages(_client(handler))


def test_write_raw_flattens_subpage_titles(tmp_path):
    count = write_raw({"Minerals/Refine Tree": "text"}, tmp_path)
    assert count == 1
    assert (tmp_path / "Minerals__Refine_Tree.wikitext").read_text() == "text"


def test_write_raw_removes_stale_files(tmp_path):
    (tmp_path / "Deleted.wikitext").write_text("old")
    write_raw({"Relics": "text"}, tmp_path)
    assert not (tmp_path / "Deleted.wikitext").exists()
    assert (tmp_path / "Relics.wikitext").exists()


def test_write_raw_refuses_empty_mapping(tmp_path):
    with pytest.raises(ScrapeError, match="refusing"):
        write_raw({}, tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scrape.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.scrape'`

- [ ] **Step 3: Write `src/atlas/scrape.py`**

```python
from pathlib import Path
from typing import Any

import httpx

from atlas.rawcheck import raw_filename

API_URL = "https://revolutionidle.wiki.gg/api.php"
USER_AGENT = (
    "revolution-idle-atlas/0.1 "
    "(+https://github.com/tobydillman/revolution-idle-atlas)"
)

BASE_PARAMS: dict[str, Any] = {
    "action": "query",
    "format": "json",
    "generator": "allpages",
    "gapnamespace": 0,
    "gaplimit": 50,
    "prop": "revisions",
    "rvprop": "content",
    "rvslots": "main",
}


class ScrapeError(Exception):
    """Raised when the wiki API misbehaves or returns nothing usable."""


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)


def fetch_pages(client: httpx.Client) -> dict[str, str]:
    pages: dict[str, str] = {}
    params = dict(BASE_PARAMS)

    while True:
        response = client.get(API_URL, params=params)
        if response.status_code != 200:
            raise ScrapeError(
                f"wiki API returned {response.status_code} for {response.url}"
            )

        payload = response.json()
        for page in payload.get("query", {}).get("pages", {}).values():
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            content = revisions[0].get("slots", {}).get("main", {}).get("*")
            if content is None:
                continue
            pages[page["title"]] = content

        cont = payload.get("continue")
        if not cont:
            break
        params = dict(BASE_PARAMS) | cont

    if not pages:
        raise ScrapeError("wiki API returned no pages — refusing to continue")

    return pages


def write_raw(pages: dict[str, str], raw_dir: Path) -> int:
    if not pages:
        raise ScrapeError("refusing to write an empty scrape into data/raw/")

    raw_dir.mkdir(parents=True, exist_ok=True)

    expected: set[str] = set()
    for title, content in pages.items():
        filename = raw_filename(title.replace(" ", "_"))
        expected.add(filename)
        (raw_dir / filename).write_text(content, encoding="utf-8")

    for existing in raw_dir.glob("*.wikitext"):
        if existing.name not in expected:
            existing.unlink()

    return len(pages)
```

- [ ] **Step 4: Add the `scrape` subcommand to `src/atlas/cli.py`**

Add this import alongside the existing ones:

```python
from atlas.scrape import ScrapeError, fetch_pages, make_client, write_raw
```

Add this function above `main`:

```python
def _scrape(root: Path) -> int:
    try:
        with make_client() as client:
            pages = fetch_pages(client)
        count = write_raw(pages, root / "data" / "raw")
    except ScrapeError as exc:
        print(f"scrape failed: {exc}", file=sys.stderr)
        return 1
    print(f"ok: wrote {count} pages to data/raw/")
    return 0
```

In `main`, add the subparser after the `build` one:

```python
    scrape = sub.add_parser("scrape", help="fetch raw wikitext into data/raw/")
    scrape.add_argument("--root", type=Path, default=Path.cwd())
```

And extend the dispatch:

```python
    if args.command == "build":
        return _build(args.root, args.check)
    if args.command == "scrape":
        return _scrape(args.root)
    return 1
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_scrape.py -v`
Expected: 7 passed

- [ ] **Step 6: Do a real scrape**

Run: `uv run atlas scrape`
Expected: `ok: wrote 77 pages to data/raw/` (exact count will drift as the wiki grows)

Verify: `ls data/raw/ | head` shows `.wikitext` files, and
`grep -l "{{New Content}}" data/raw/*.wikitext` lists `Singularity` and `Plague`.

- [ ] **Step 7: Commit**

```bash
git add src/atlas/scrape.py src/atlas/cli.py tests/test_scrape.py data/raw/
git commit -m "feat: add wiki scraper writing raw wikitext for diffing"
```

---

### Task 7: Bootstrap the Refine Tree and seed the dataset

**Files:**
- Create: `bootstrap/README.md`
- Create: `bootstrap/refine_tree.py`
- Create: `data/relationships.yaml`

**Interfaces:**
- Consumes: `data/raw/Minerals__Refine_Tree.wikitext` (from Task 6)
- Produces: `data/relationships.yaml` — the dataset all later work builds on

Per the Global Constraints, `bootstrap/` is **throwaway**: not tested, not
imported by `src/`, not run by CI. It prints YAML to stdout for a human to
review and paste. It must never write to `data/relationships.yaml` directly.

The Refine Tree wikitext uses `{{RN|<n>| max = .. | rfp = .. | effect = .. | req = 8,15 }}`.
The `req` parameter is a comma-separated list of prerequisite node numbers.

- [ ] **Step 1: Write `bootstrap/README.md`**

```markdown
# Bootstrap scripts

One-time seeding scripts, run by hand during initial dataset construction.

**These are not maintained.** They are not tested, not imported by `src/atlas`,
and not run by CI. They print YAML to stdout; a human reviews it and pastes it
into `data/relationships.yaml`, which is the single source of truth from that
point onward.

If a script here stops working because the wiki changed, delete it rather than
fixing it — its job is already done.

## Usage

    uv run python bootstrap/refine_tree.py > /tmp/refine.yaml
```

- [ ] **Step 2: Write `bootstrap/refine_tree.py`**

```python
"""One-time: extract Refine Tree nodes and prerequisite edges. See README."""

import re
import sys
from pathlib import Path

RAW = Path("data/raw/Minerals__Refine_Tree.wikitext")
RN_PATTERN = re.compile(r"\{\{RN\|(\d+)\|([^{}]*)\}\}", re.DOTALL)


def parse_params(blob: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in blob.split("|"):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        params[key.strip()] = value.strip()
    return params


def main() -> int:
    if not RAW.is_file():
        print(f"missing {RAW} — run `uv run atlas scrape` first", file=sys.stderr)
        return 1

    matches = RN_PATTERN.findall(RAW.read_text(encoding="utf-8"))
    if not matches:
        print("no {{RN|...}} invocations found", file=sys.stderr)
        return 1

    print("# --- Refine Tree nodes (bootstrap output, review before pasting) ---")
    print("nodes:")
    for number, _ in matches:
        print(f"  - id: refine-node-{number}")
        print(f"    name: Refine Node {number}")
        print("    system: mineral")
        print("    kind: tree-node")
        print("    wiki: Minerals/Refine_Tree")
        print("    confidence: documented")

    print()
    print("edges:")
    edge_count = 0
    for number, blob in matches:
        params = parse_params(blob)
        req = params.get("req", "").strip()
        if not req:
            continue
        for prereq in (r.strip() for r in req.split(",") if r.strip()):
            print(f"  - from: refine-node-{prereq}")
            print(f"    to: refine-node-{number}")
            print("    rel: requires")
            print("    source: wiki:Minerals/Refine_Tree")
            print("    confidence: documented")
            edge_count += 1

    print(f"\n# {len(matches)} nodes, {edge_count} prerequisite edges", file=sys.stderr)
    print(f"# {len(matches)} nodes, {edge_count} prerequisite edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the bootstrap and sanity-check the counts**

Run: `uv run python bootstrap/refine_tree.py > /tmp/refine.yaml`
Expected on stderr: roughly `# 136 nodes, 158 prerequisite edges`

If the node count is far from 136, the template shape changed — inspect
`data/raw/Minerals__Refine_Tree.wikitext` before trusting the output.

- [ ] **Step 4: Hand-author the seed `data/relationships.yaml`**

Start from the bootstrap output, then hand-add the motivating chain. The file
below is the minimum the seed must contain — the Refine Tree block from
`/tmp/refine.yaml` gets merged into the same two `nodes:` / `edges:` lists.

```yaml
# Revolution Idle Atlas — relationship dataset.
# Single source of truth. Hand-maintained. Nothing but a human writes here.
#
# confidence (nodes): documented | provisional | unknown
# confidence (edges): documented | provisional | uncertain
# source: wiki:<PageName> | observed | il2cpp | discord

nodes:
  - id: attack-power
    name: Attack Power
    system: unity
    kind: stat
    wiki: Unity#Attacks
    confidence: documented

  - id: gold
    name: Gold
    system: unity
    kind: currency
    wiki: Unity#Attacks
    confidence: documented

  - id: relic-3
    name: Relic 3
    system: unity
    kind: relic
    wiki: Relics#Relic_3
    confidence: documented

  - id: singularity
    name: Singularity
    system: singularity
    kind: currency
    wiki: Singularity
    confidence: provisional

  - id: atoms-gain
    name: Atoms Gain
    system: singularity
    kind: stat
    wiki: Singularity
    confidence: provisional

  - id: relic-69
    name: Relic 69
    system: unity
    kind: relic
    wiki: Relics
    confidence: provisional

  - id: plague
    name: Plague
    system: plague
    kind: currency
    wiki: Plague
    confidence: unknown

edges:
  - from: relic-3
    to: attack-power
    rel: boosts
    source: wiki:Relics
    confidence: documented

  - from: gold
    to: relic-3
    rel: boosts
    note: "Relic upgrade level scales with lifetime gold"
    source: wiki:Relics
    confidence: uncertain

  - from: refine-node-121
    to: singularity
    rel: unlocks
    note: "Singularity is unlocked by Refine Node 121"
    source: wiki:Singularity
    confidence: provisional

  - from: relic-69
    to: atoms-gain
    rel: boosts
    op: exp
    note: "Modifies the 1,000,000 atom threshold buff"
    source: wiki:Singularity
    confidence: provisional
```

- [ ] **Step 5: Build and inspect the coverage report**

Run: `uv run atlas build`
Expected: `ok: N nodes, M edges, ... orphans, ... warning(s)` and exit code 0.

Then read `docs/coverage.md`. The Refine Tree nodes with no `req` and no
dependents will appear as orphans — that is correct and expected; it is the
curation to-do list doing its job.

- [ ] **Step 6: Verify the WIP warning fires**

Temporarily change `singularity`'s `confidence` from `provisional` to
`documented` and run `uv run atlas build`. Expected on stderr:

```
data/relationships.yaml:NN  warning  node 'singularity' sources from a {{New Content}} page but confidence is 'documented' — expected 'provisional'
```

Change it back to `provisional` before committing.

- [ ] **Step 7: Commit**

```bash
git add bootstrap/ data/relationships.yaml public/graph.json docs/coverage.md
git commit -m "feat: seed relationships dataset from Refine Tree bootstrap"
```

---

### Task 8: CI workflow and the daily scrape PR bot

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/scrape.yml`

**Interfaces:**
- Consumes: `atlas build --check`, `atlas scrape`, `uv run pytest`
- Produces: CI gate on every PR; a daily PR when `data/raw/` changes

`ci.yml` runs on every push and PR. `scrape.yml` runs daily and opens a PR only
when the raw wikitext actually changed. Merging that PR records that the change
was *seen* — updating `relationships.yaml` remains a separate human step.

The PR body separates new pages from edited ones, because a new page appearing
on a wiki under active construction is the highest-signal event and must not be
buried in a list of text edits.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Run tests
        run: uv run pytest -v

      - name: Validate dataset
        run: uv run atlas build --check
```

- [ ] **Step 2: Verify CI passes locally**

Run: `uv run pytest -v && uv run atlas build --check`
Expected: all tests pass, then `ok: N nodes, M edges, ...`, exit code 0.

- [ ] **Step 3: Write `.github/workflows/scrape.yml`**

```yaml
name: Daily wiki scrape

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Scrape wiki
        run: uv run atlas scrape

      - name: Summarise changes
        id: summary
        run: |
          {
            echo 'body<<PRBODY'
            echo 'Automated wiki scrape. Raw wikitext only — `relationships.yaml` is untouched.'
            echo ''
            echo '### New pages'
            git ls-files --others --exclude-standard data/raw/ \
              | sed 's|data/raw/|- |; s|\.wikitext$||' | grep . || echo '_none_'
            echo ''
            echo '### Changed pages'
            git diff --numstat -- data/raw/ \
              | awk '{printf "- %s (+%s/-%s)\n", $3, $1, $2}' | grep . || echo '_none_'
            echo ''
            echo '### Removed pages'
            git diff --diff-filter=D --name-only -- data/raw/ \
              | sed 's|data/raw/|- |; s|\.wikitext$||' | grep . || echo '_none_'
            echo ''
            echo '### WIP-flagged pages'
            grep -l '{{New Content}}' data/raw/*.wikitext 2>/dev/null \
              | sed 's|data/raw/|- |; s|\.wikitext$||' || echo '_none_'
            echo 'PRBODY'
          } >> "$GITHUB_OUTPUT"

      - name: Open pull request
        uses: peter-evans/create-pull-request@v7
        with:
          add-paths: data/raw
          branch: wiki-scrape
          title: "chore: daily wiki scrape"
          body: ${{ steps.summary.outputs.body }}
          commit-message: "chore: daily wiki scrape"
          delete-branch: true
```

- [ ] **Step 4: Verify the summary script runs**

Touch a raw file so there is something to report, then run the shell body
standalone to confirm it produces sensible markdown:

```bash
echo "" >> data/raw/Relics.wikitext
git diff --numstat -- data/raw/ | awk '{printf "- %s (+%s/-%s)\n", $3, $1, $2}'
git checkout data/raw/Relics.wikitext
```

Expected: one line like `- data/raw/Relics.wikitext (+1/-0)`

- [ ] **Step 5: Commit**

```bash
git add .github/
git commit -m "ci: add test gate and daily wiki scrape PR bot"
```

---

## Done criteria

- `uv run pytest` passes.
- `uv run atlas build` writes `public/graph.json` and `docs/coverage.md`.
- `uv run atlas build --check` exits non-zero on a dangling reference and prints
  a fuzzy-matched suggestion.
- `uv run atlas scrape` populates `data/raw/` and fails loudly on an empty result.
- `data/relationships.yaml` contains the Refine Tree plus the motivating
  attack-power chain.

## Follow-on

The web app is a separate plan, written once `graph.json` exists. Its contract is
the `{version, nodes, edges}` shape produced by `atlas.render.to_graph`.
