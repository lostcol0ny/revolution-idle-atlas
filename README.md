# Revolution Idle Atlas

A data pipeline that turns a hand-curated map of stat and resource dependencies in
the idle game [Revolution Idle](https://revolutionidle.wiki.gg/) into
`public/graph.json`, a graph document for a visualisation frontend.

## The single source of truth

`data/relationships.yaml` is **hand-maintained**. Nothing generates it, and
nothing may generate it. Every other piece of this repository exists to make
curating that one file tolerable:

| Path | Role |
|---|---|
| `data/relationships.yaml` | The dataset. Written by a human, reviewed by a human. |
| `data/raw/` | Scraped wikitext, one file per wiki page. Read-only reference used for **diffing** — it tells you when the wiki changed under you. It never feeds the dataset. |
| `data/inventory.yaml` | Optional. A map of system → known entity ids, used to report gaps. Absent by default; its absence is silent. |
| `public/graph.json` | Generated. The contract with the frontend. Committed. |
| `docs/coverage.md` | Generated. The curation to-do list. Committed. |
| `bootstrap/` | Throwaway. One-off scripts used to seed the initial dataset. Not imported by `src/`, not run by CI, not tested. Delete it rather than fix it. |

`public/graph.json` and `docs/coverage.md` are build products that are committed
to the repository. CI rebuilds them and fails if the result differs, so if a CI
run goes red on the artifact step, run `uv run atlas build` and commit the result.

## Commands

```sh
uv sync                  # install
uv run atlas build       # validate, then write public/graph.json and docs/coverage.md
uv run atlas build --check   # validate only; write nothing
uv run atlas scrape      # re-fetch data/raw/ from the wiki
uv run pytest            # tests
```

`atlas build` exits non-zero only on **errors** (unresolvable references,
duplicate ids, self-edges, malformed YAML). Warnings — a node pointing at a wiki
page no longer in `data/raw/`, or claiming `documented` confidence for a page the
wiki flags as work in progress — are printed but never fail the build.

`atlas scrape` talks to a live, volunteer-run wiki. Do not run it in a loop. A
scheduled GitHub Actions workflow runs it daily and opens a pull request when the
raw wikitext changes; that PR touches `data/raw/` only.

## `public/graph.json` schema

Version 1. The top-level document:

```json
{
  "version": 1,
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

`version` is an integer. It increments when the shape changes incompatibly; a
consumer should refuse a version it does not recognise.

Node and edge order is deterministic — it follows the order of
`data/relationships.yaml` — and keys within each object are sorted
alphabetically. **Fields whose value is null are omitted entirely** rather than
emitted as `null`, so a consumer must treat "key absent" and "no value" as the
same thing.

### Node

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Unique across all nodes. Edges reference this. |
| `name` | string | yes | Human-readable display label. |
| `system` | enum | yes | Which game system the node belongs to. |
| `kind` | enum | yes | What sort of thing the node is. |
| `wiki` | string | no | Wiki page title, optionally with a `#Section` anchor. |
| `confidence` | enum | no | Defaults to `documented`. |

`system`: `revolution`, `infinity`, `eternity`, `unity`, `zodiac`, `mineral`,
`tarot`, `singularity`, `plague`.

`kind`: `relic`, `stat`, `tree-node`, `currency`, `tarot-card`, `upgrade`,
`group`.

**Node `confidence`**: `documented`, `provisional`, `unknown`.

- `documented` — the wiki describes it and the description is stable.
- `provisional` — sourced from a page the wiki flags as work in progress.
- `unknown` — a placeholder. The entity exists but nothing about it is curated
  yet. These are counted as "stubs" in `docs/coverage.md`.

### Edge

| Field | Type | Required | Notes |
|---|---|---|---|
| `from` | string | yes | Source node `id`. Serialised as `from`, not `from_`. |
| `to` | string | yes | Target node `id`. |
| `rel` | enum | yes | The kind of relationship. |
| `op` | enum | no | How the effect combines, when known. |
| `note` | string | no | Free text. |
| `source` | string | yes | Where the claim came from: `wiki:<PageName>`, `observed`, `il2cpp`, or `discord`. |
| `confidence` | enum | no | Defaults to `documented`. |

`rel`: `boosts`, `unlocks`, `requires`. Edges point upstream → downstream:
`from` boosts / unlocks / is required by `to`.

`op`: `add`, `mult`, `exp`.

**Edge `confidence`**: `documented`, `provisional`, `uncertain`.

The two `confidence` vocabularies **differ deliberately**. A node's third value
is `unknown` — the node is a placeholder and nothing is curated. An edge's third
value is `uncertain` — the relationship is believed to exist but its direction,
magnitude or exact mechanism is not established. There is no such thing as an
`unknown` edge (an edge nobody knows about is simply absent), and there is no
such thing as a `provisional`-only node placeholder. Do not merge the enums.

### Cycles are legitimate

**The graph is not a DAG and a consumer must not assume it is.** Feedback loops
are real game mechanics — gold buys an upgrade that increases gold income — and
this pipeline treats them as data, never as errors. `docs/coverage.md` reports
strongly connected components under "Feedback loops" for information only.

Any traversal in a consumer must carry a visited set. A layout or dependency walk
written on the assumption of acyclicity will not terminate.

Self-edges (`from == to`) *are* rejected as errors, so a cycle always has length
two or more.
