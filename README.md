# Revolution Idle Atlas

A data pipeline that turns a map of stat and resource dependencies in the idle
game [Revolution Idle](https://revolutionidle.wiki.gg/) into
`public/graph.json`, a graph document for a visualisation frontend.

## The dataset is two files, split by durability

The dataset lives in two files, and what separates them is **how long they
survive**, not who or what is allowed to write them:

- `data/derived.yaml` is **disposable**. `atlas extract` regenerates it in full
  from `data/raw/` on every run, so any edit to it lasts until the next run.
- `data/relationships.yaml` is **durable**. It survives extraction and **wins
  every merge**, which is what makes it the place to correct or delete anything
  generated.

`atlas build` loads both and merges them. A curated node overlays the generated
one **field by field**, so correcting one relic's name does not mean restating
its kind, wiki page and effects. A curated edge replaces the generated one
wholesale. A `suppress:` entry deletes a generated edge outright — the one
correction an overlay cannot express.

A third file, `data/sweep.yaml`, is neither half of that pair. It is not data
about the game; it is a description of where in `data/raw/` to find data about
the game. Editing it changes what `atlas extract` produces, so it is an input to
the disposable half, and everything read through it arrives at the lowest
confidence the schema has.

| Path | Role |
|---|---|
| `data/relationships.yaml` | The durable half. Survives extraction and wins every merge. Committed. |
| `data/derived.yaml` | The disposable half. Regenerated in full by `atlas extract`; do not hand-edit it, because the next run overwrites it. Committed. |
| `data/raw/` | Scraped wikitext, one file per wiki page. The input `atlas extract` parses, and the reference `atlas build` diffs against to tell you when the wiki changed under you. |
| `data/sweep.yaml` | The sweep manifest. Names which columns of which `data/raw/` pages carry an entity name and an effect, so a page can be swept without new Python. Committed. |
| `data/inventory.yaml` | Optional. A map of system → known entity ids, used to report gaps. Absent by default; its absence is silent. |
| `public/graph.json` | Generated. The contract with the frontend. Committed. |
| `docs/coverage.md` | Generated. The curation to-do list. Committed. |
| `bootstrap/` | Historical. Held one-off seeding scripts; all have been superseded by `atlas extract` and removed. |

`data/derived.yaml`, `public/graph.json` and `docs/coverage.md` are build
products that are committed to the repository. CI rebuilds them and fails if the
result differs. If a CI run goes red on the artifact step, run
`uv run atlas extract && uv run atlas build` and commit the result. A change to
`data/raw/` — the most common trigger — requires the extraction step first;
running only `atlas build` will leave `data/derived.yaml` stale and the step
stays red.

`atlas extract` reads `data/relationships.yaml` as well as `data/raw/`, because
the curated stats and their aliases are the vocabulary it matches effect prose
against. Adding a stat node or an alias therefore changes `data/derived.yaml`,
and a run of `atlas build` alone will not pick it up. It still makes no network
request, which is what keeps it safe to run in CI.

## Commands

```sh
uv sync                  # install
uv run atlas build       # merge both dataset files, validate, then write the artifacts
uv run atlas build --check   # validate only; write nothing
uv run atlas extract     # parse data/raw/ into data/derived.yaml
uv run atlas scrape      # re-fetch data/raw/ from the wiki
uv run pytest            # tests
```

`atlas build` exits non-zero only on **errors** (unresolvable references,
duplicate ids, self-edges, malformed YAML, a node whose `system` is not declared
in the `systems` array, a system whose `parent` is not a declared system, a cycle
in the system parent chain, or an out-of-range `targets_effect`). Warnings — a
node pointing at a wiki page no longer in `data/raw/`, a page the wiki flags as
work in progress paired with `documented` confidence, a `suppress` rule that
matches no edge, or a generated edge colliding with an earlier one on
`(from, to, rel)` — are printed but never fail the build.

The sweep manifest is read by `atlas extract`, not by `atlas build`, so its
warnings appear only on an extraction run: a manifest page that yields no
records, a page named in the manifest with no file in `data/raw/`, or two
manifest entries minting the same node id. Looking for them after `atlas build`
finds nothing, because that command never opens `data/sweep.yaml`.

A manifest page yielding no records is a **warning and not an error**, unlike one
of the four hand-written parsers producing no nodes, which is fatal. Those four
cover pages known to hold data, so zero means the page or the parser broke. A
manifest entry is a guess about a page's shape, and one wrong guess must not
block every build — including the artifact check in CI.

`atlas scrape` talks to a live, volunteer-run wiki. Do not run it in a loop. A
scheduled GitHub Actions workflow runs it daily and opens a pull request when the
raw wikitext changes; that PR touches `data/raw/` only.

## The sweep manifest

`data/sweep.yaml` lets a wiki page be read without writing a parser for it. Each
entry names a page and says which of its columns or template fields carry an
entity's name and its effects.

Everything read through the manifest is deliberately low-confidence: swept nodes
are `provisional` and swept edges are `uncertain` and always `boosts`. A column
heading is a guess about what a page means, and a wrong edge is worse than a
missing one — a missing one shows up in `docs/coverage.md`, a wrong one just
looks true. Correct anything wrong in `data/relationships.yaml`, which wins every
merge.

Two readers are available, selected by `reader`.

Fields common to both:

| Field | Required | Notes |
|---|---|---|
| `reader` | yes | `wikitable` or `record_template`. |
| `page` | yes | The wiki page **title**, underscored (`Dilation_Tree`, `Minerals/Refine_Tree`). Resolved to a file in `data/raw/` and written to each swept node's `wiki`. |
| `system` | yes | Must be declared in `data/relationships.yaml`'s `systems` array, or the build fails. |
| `kind` | yes | Any node `kind`. |
| `id_prefix` | yes | Node ids are `<id_prefix>-<slugified name>`. No entry's `id_prefix` may be a prefix of another's — `singularity` alongside `singularity-tree` is rejected, because the two are one row name apart from minting the same id. |
| `name_prefix` | no | Prepended to the name, and to the name only. For a table whose name column is a bare number — Singularity's tree rows are `1`, `2`, `3.1`, and `name_prefix: Tree Node` makes them readable. The id keeps the raw name (`singularity-tree-3-1`), since `id_prefix` already supplies the noun. |

`reader: wikitable`:

| Field | Required | Notes |
|---|---|---|
| `name_columns` | yes | One or more header names, joined by a space. Two are needed when neither identifies a row alone — `Dilation_Tree` rows are an `Axis` plus an `Index`. |
| `effect_columns` | yes | One or more header names. **Each becomes a separate effect**, because a Zodiac really does have four independent bonuses. |
| `per_level_column` | no | Only valid alongside exactly one `effect_columns` entry; with two there would be no way to say which effect it scales. |

`reader: record_template`:

| Field | Required | Notes |
|---|---|---|
| `template` | yes | Template name, e.g. `Minerals/Special_Minerals`. Matched case-insensitively. |
| `name_field` | yes | Template field holding the name. |
| `effect_fields` | yes | One or more template fields. Each becomes a separate effect. |
| `per_level_field` | no | Same single-effect restriction as `per_level_column`. |

**A page needs one entry per column shape, not one per page.** `Plague` has two:
its ER Upgrades table is `Name`/`Effect`, and its Statistics table is
`Statistic`/`Boost`. Every table on the page whose headers match an entry is
read, so `Trials` needs only one entry to cover all five of its difficulty tiers.

**What the reader will not do**, each for a reason:

- A row with fewer cells than headers is skipped, unless the shortfall is
  explained by a `rowspan` above it — which is carried down, because on
  `Dilation_Tree` the rowspan column is the name column.
- A `colspan` header cell is discarded as a caption, and a `colspan` data row is
  skipped.
- A table where a wanted column name appears twice is skipped entirely.
  `Minerals` lays two independent upgrade tables side by side in one wikitable;
  reading it positionally would take the right-hand half and silently drop the
  left.
- An effect cell containing no letters is not an effect. `Plague`'s ER Upgrades
  table writes `<==` to mean "see the Name column".

`docs/coverage.md`'s **Not swept** section lists every page in `data/raw/` that
no node points at, largest first. That is the queue.

## `public/graph.json` schema

Version 1. The top-level document:

```json
{
  "version": 1,
  "nodes": [ ... ],
  "edges": [ ... ],
  "systems": [ ... ]
}
```

`version` is an integer. It increments when the shape changes incompatibly; a
consumer should refuse a version it does not recognise.

`systems` is **optional** — it is omitted entirely when the dataset declares no
systems, which is what keeps a system-less document byte-identical to an older
v1 one. Everything added since v1 has been optional for the same reason.

Node and edge order is deterministic: generated records come first in the order
`atlas extract` produced them, then records that exist only in
`data/relationships.yaml`, in that file's order. A curated record that overrides
a generated one keeps the generated one's position. Keys within each object are
sorted alphabetically. **Fields whose value is null or an empty list are omitted
entirely** rather than emitted as `null` or `[]`, so a consumer must treat "key
absent" and "no value" as the same thing.

### System

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | What a node's `system` refers to. |
| `name` | string | yes | Human-readable display label. |
| `parent` | string | no | Another system's `id`. Systems nest one level in practice, but nothing enforces a depth limit; cycles are rejected. |

### Node

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Unique across all nodes. Edges reference this. |
| `name` | string | yes | Human-readable display label. For `relic-<n>` nodes this is composed at render time as `Relic <n> (<wiki name>)`, because players refer to relics by number; see below. |
| `system` | string | yes | Which game system the node belongs to. **Free string, not an enum** — see below. |
| `kind` | enum | yes | What sort of thing the node is. |
| `wiki` | string | no | Wiki page title, optionally with a `#Section` anchor. |
| `confidence` | enum | no | Defaults to `documented`. |
| `effects` | array | no | What the entity does. Omitted when empty. |
| `aliases` | array of string | no | Other names the wiki uses for this entity. Matching input, not display text. Omitted when empty. |

`system` is a **free string**, deliberately. The taxonomy is data, not an enum:
the declared systems live in this document's own `systems` array, and a
consumer should read them from there rather than hard-coding a union. It was an
enum once, and the same list had to be repeated in the Python models, the
frontend types and this README — they drifted, and a value present in one and
absent in another rendered a blank canvas.

A consumer may still keep a list of ids it has colours or ordering for
(`web/src/types.ts` does exactly this), but it must treat that list as a hint
and tolerate an id it has never seen.

`kind`: `relic`, `stat`, `tree-node`, `currency`, `tarot-card`, `upgrade`,
`group`.

**Relic labels are composed, not stored.** A node whose `kind` is `relic` and whose `id`
matches `relic-<n>` is emitted with `name` set to `Relic <n> (<name>)`. The composition
happens in `src/atlas/render.py`, after the merge, because a name can arrive from either
dataset file and composing it in the parser would be bypassed by any curated `name`
override. When the underlying name is empty or already equal to `Relic <n>`, the bare
`Relic <n>` is emitted — so `Relic 3 (Relic 3)` is unrepresentable.

#### Effect

An entry in a node's `effects` array.

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string | yes | The effect as prose. |
| `per_level` | string | no | **A string, not a number.** Kept exactly as the wiki writes it, including forms like `+(?)` and `*^`. The wiki's own notation carries information a parsed number cannot: `+(?)` means the operator is known and the coefficient is not. |
| `op` | enum | no | How the effect combines, when known. |

`aliases` exist because the wiki names one stat several ways — "Special Minerals Merge
Factor", "SMMF" and "Merge Factor" are one node. The extraction layer matches effect prose
against every node's `name` plus its `aliases`, longest surface form first. An
ALL-UPPERCASE alias is matched **case-sensitively** so that `AP` cannot fire inside
"Appears"; everything else is matched case-insensitively. Aliases shorter than three
characters are ignored unless they are ALL-UPPERCASE, where two is allowed. Every edge
produced by prose matching is stamped `confidence: uncertain`, because prose is weaker
evidence than a structural table cell.

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
| `targets_effect` | integer | no | 0-based index into the **target** node's `effects` array. See below. |
| `source` | string | yes | Where the claim came from. A free string; the convention is `wiki:<PageName>`, `observed`, `il2cpp`, or `discord`. |
| `confidence` | enum | no | Defaults to `documented`. |

`rel`: `boosts`, `unlocks`, `requires`. Edges point upstream → downstream:
`from` boosts / unlocks / is required by `to`.

`targets_effect` is set when the source modifies one specific effect of the
target rather than the target as a whole — "Relic 66 multiplies Relic 62's
*effect*" is second-order, and the two endpoint ids alone cannot say which
effect it lands on. It indexes the `effects` array of the node named by `to`,
and the build rejects an index that array does not have.

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

## The frontend

`web/` is a Vite + React single-page app that renders `public/graph.json` as an
ego graph: pick a node, see what feeds it on the left and what it feeds on the
right.

```sh
cd web
npm install
npm run dev        # http://localhost:5173
npm run typecheck  # both tsconfig projects: app, then tests + vite.config
npm run test       # vitest
npm run build      # -> web/dist
```

The app reads `public/graph.json` at runtime rather than importing it, and
`vite.config.ts` sets `publicDir: '../public'` so the repo-root committed
artifact is served and built directly. There is no copy step, so the app cannot
render a stale graph — what CI verified is what ships.

The app is a **read-only consumer**. It never writes the dataset and never
derives it. It shows *that* A boosts B, never by how much; formulas and
coefficients are out of scope and the pipeline does not carry them.

### Known gaps

`graph.json` carries `effects`, `targets_effect`, `aliases` and the `systems`
hierarchy, and the sweep has added 131 more nodes to `data/derived.yaml` — but
the React viewer still
renders only v1's fields. No component reads `effects` or `targets_effect`, so
the thing this pipeline exists to show is not yet visible in the UI. This is a
recorded sequencing decision: the schema contract was fixed before any UI was
built on it.

Every edge produced by the sweep carries `confidence: uncertain`. A consumer that
renders them identically to `documented` edges will present guesses as facts.

### Deployment

Deployed to Vercel as static files. There is no `vercel.json` and no rewrite
rules are needed — deep links use query parameters (`/?node=attack-power`),
not path segments, so every request already hits `/`.

| Setting | Value |
|---|---|
| Root directory | `web/` |
| Framework preset | Vite |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node.js version | 20.x |

Set these in the Vercel project dashboard. Because the root directory is
`web/` but `publicDir` points at `../public`, the project must be configured to
include files outside the root directory — Vercel does this by default when the
repository is imported whole, which is the standard flow.
