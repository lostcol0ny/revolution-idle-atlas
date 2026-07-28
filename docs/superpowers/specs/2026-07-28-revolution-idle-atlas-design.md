# Revolution Idle Atlas — Design

**Date:** 2026-07-28
**Status:** Approved design, pending implementation plan

## Problem

Revolution Idle has deeply interconnected systems. Upgrading something in one
screen produces knock-on effects in unrelated screens — a Refine Tree node
boosts gold generation, which raises a relic's upgrade level, which increases
attack power. The wiki documents each system in isolation. No view shows the
chains that connect them.

A player asking "what actually feeds my attack power?" has to read six pages and
hold the graph in their head.

## Goals

1. Answer "what feeds X?" and "what does X affect?" for any game entity.
2. Make chains traversable — click through a dependency path hop by hop.
3. Make gaps visible. The wiki is actively under construction; the tool should
   show what is undocumented rather than silently omitting it.
4. Notice when the wiki changes, without polling it manually.

## Non-goals

- **Not a calculator.** No numeric predictions, no "which upgrade is better."
- **Not a wiki replacement.** Every node links out to the wiki for detail.
- **Not a save-file analyser.** See "Rejected alternatives."
- **Not automatically synchronised with the wiki.** The dataset is
  hand-maintained. Automation reports what changed; a human decides what that
  means.

## Research findings that constrain the design

Established by investigation on 2026-07-28:

| Finding | Consequence |
|---|---|
| ~450 graph-relevant entities, ~600–900 edges | Client-side rendering. No backend, no graph DB. |
| No Cargo, no Semantic MediaWiki, no Lua data tables | No structured query interface exists. |
| Mature pages use consistent named-param templates | Bootstrap extraction is viable for established content. |
| New pages use raw `{\| wikitable` markup instead | Newest content is least structured. Argues against a permanent parser. |
| Refine Tree encodes prerequisites as `req = 8,15` | 136 nodes / 158 edges bootstrappable with zero heuristics. |
| Effect strings use a controlled vocabulary with `+` `x` `^` sigils | Bootstrap regex is worthwhile; ongoing regex is not. |
| IL2CPP dump exposes stat enums, method bodies empty | Canonical stat vocabulary available. Formulas are not. |
| Saves are encrypted, CRC-hashed, device-locked | Save import is not viable. |
| `{{New Content}}` flags WIP pages (currently `Singularity`, `Plague`) | Machine-readable provisional marker, checkable without parsing. |
| 100 main-ns edits and 3 new pages in 16 days, against 77 articles | Daily change detection. New-page detection matters. |
| wiki.gg returns 403 to default Python user-agent | Scraper must send a descriptive UA. |

Two findings are decisive:

**The numeric formulas are unavailable from every source.** This is why the tool
encodes topology only — a constraint, not a scoping preference.

**The wiki is actively under construction and its newest content is its least
structured.** A permanent extraction pipeline would be perpetually chasing a
moving target, and its failures would be silent. Extraction is therefore a
one-time bootstrap, not a pipeline stage.

## Architecture

```
MediaWiki API (descriptive User-Agent required)
     │  scrape.py — fetches raw wikitext, performs NO parsing
     ▼
data/raw/<Page>.wikitext          checked in; diffed daily by CI
     │
     │  bootstrap/*.py — run ONCE during initial seeding, then archived
     ▼
data/relationships.yaml           SINGLE source of truth, hand-maintained
     │  build.py — validate + render
     ▼
public/graph.json                 build artifact the app fetches
docs/coverage.md                  generated gap report
```

### Why one hand-maintained file

An earlier draft split generated and curated data into separate files with
override-by-key semantics, so a repeatable scraper could coexist with hand
edits. Every complication in that design — merge rules, override keying,
orphaned-override detection, parsers hardened against wiki restructuring —
existed solely to serve repeatable extraction.

Making extraction one-time removes the entire category. There is one file, it is
owned by a human, and nothing else writes to it.

The trade is explicit: **wiki corrections do not propagate automatically.** They
arrive as a diff that a human reads and applies. Given that the wiki is
mid-construction and roughly a quarter of edges require human judgement
regardless, automatic propagation was never going to cover the interesting
cases.

### The scraper

`scrape.py` fetches raw wikitext for all main-namespace pages and writes one
file per page. It parses nothing. Its sole purpose is change detection, and
having no parsing logic means it has almost nothing that can break when the wiki
restructures.

### Bootstrap scripts

`bootstrap/` holds throwaway scripts used once during initial seeding, where
extraction is trivial and hand-entry would be tedious and error-prone:

- Refine Tree prerequisites from `{{RN|…|req = 8,15}}` — 158 edges, no heuristics
- Entity name/id lists from template invocations — relics, tarot cards, minerals
- Stat vocabulary from the IL2CPP enum dump — ~50 canonical stat nodes

Output is reviewed, then pasted into `relationships.yaml`. From that point the
YAML is authoritative and the scripts are archived under `bootstrap/` for
reference. **They are not maintained and are not part of the build.**

Everything not covered by bootstrap is hand-authored, reading from
`data/raw/` — including all of the Singularity and Plague wikitable content,
relic effect targets, and anything learned from playing.

## Data model

One file, `data/relationships.yaml`. YAML over JSON because it is edited by hand
and reviewed as diffs.

### Nodes

```yaml
nodes:
  - id: relic-3                 # stable slug, referenced by edges
    name: Relic 3
    system: unity               # revolution|infinity|eternity|unity|zodiac|
                                # mineral|tarot|singularity|plague
    kind: relic                 # relic|stat|tree-node|currency|tarot-card|
                                # upgrade|group
    wiki: Relics#Relic_3        # deep link; may be omitted for stubs
    confidence: documented      # documented|provisional|unknown
```

`system` mirrors the game's own partitioning. The IL2CPP dump has no global
`StatType` enum — stats are split per-system (`ZodiacStats`,
`MineralUpgradeType`, `PlanetStatType`, `ElementFactorType`). Borrowing that
structure gives principled colouring, filtering, and collapsing.

`confidence: unknown` marks a **stub**: an entity known to exist whose effects
are undocumented. Stubs are first-class, not an error state.

### Edges

```yaml
edges:
  - from: refine-node-121
    to: singularity
    rel: unlocks                # boosts|unlocks|requires
    op: exp                     # add|mult|exp — optional
    note: "Singularity is unlocked by Refine Node 121"
    source: wiki:Singularity    # wiki:PageName | observed | il2cpp | discord
    confidence: provisional     # documented|provisional|uncertain
```

Field rationale:

- **`rel`** — `requires` (Refine Tree prerequisites) and `boosts` (stat effects)
  are different relationships and must not render identically.
- **`op`** — the `+` / `x` / `^` sigil appears directly in wiki effect text, so
  recording the operator *class* costs nothing extra while transcribing. It is
  not a formula: no coefficients, no per-level values. Lets multiplicative
  chains be spotted at a glance.
- **`source`** — provenance. `observed` covers relationships learned from
  personal gameplay that the wiki has not documented.
- **`confidence`** — rendered as dashed/muted edges so a visitor can judge
  reliability without a disclaimer paragraph.

### Note on `confidence` values

Nodes and edges share the field name but the third value differs, because they
express different doubts:

| Value | On a node | On an edge |
|---|---|---|
| `documented` | Entity and its effects are described on the wiki | Relationship is stated explicitly on the wiki |
| `provisional` | Entity is on a `{{New Content}}` page | Source page is `{{New Content}}`; may change |
| `unknown` | **Stub** — entity exists, effects undocumented | *(not used)* |
| `uncertain` | *(not used)* | Relationship inferred or observed, not confirmed |

A node is `unknown` when we know it exists but not what it does. An edge is
`uncertain` when we suspect a connection but cannot cite it. There is no such
thing as an `unknown` edge — an unknown relationship is simply an absent edge,
which is precisely what the Gaps view surfaces.

## Validation (`build.py`)

Because there is no capture-time tooling, the validator is the sole correctness
gate and its error messages carry the ergonomic load. Unknown-id errors must
fuzzy-match against known ids and suggest alternatives:

```
data/relationships.yaml:412  unknown node id 'relic-96'
                             did you mean 'relic-69'?
```

Errors (fail the build):
- Edge referencing a nonexistent node id
- Duplicate node ids
- Malformed enum values in `system`, `kind`, `rel`, `op`, `confidence`
- Self-edges

Warnings (never fail the build):
- A node whose `wiki:` page carries `{{New Content}}` in `data/raw/` but whose
  `confidence` is not `provisional`. This is a text search against raw wikitext,
  not a parser, and it keeps the WIP flag effectively automatic.
- A node whose `wiki:` page no longer exists in `data/raw/` — the page was
  renamed or deleted.

Reports (written to `docs/coverage.md`):
- Orphan nodes with zero edges — the curation to-do list
- Cycles — feedback loops are real mechanics and are surfaced, not rejected
- Entities present in IL2CPP enums but absent from the YAML — known-unknowns
  enumerable without playing
- Coverage percentage per system

## Application

**Stack:** Next.js (static export) + Cytoscape.js with a dagre layout, deployed
to Vercel.

Cytoscape.js is chosen because the entire app reduces to two graph queries —
`.predecessors()` and `.successors()` — which it provides natively along with
hop-limiting and mature layout algorithms. React Flow renders more attractively
but is a node-editor library with no traversal primitives; using it would mean
hand-writing BFS and adding `elkjs` for layout.

### Views

**Focus view (primary).** Selected node centred, upstream fanning left,
downstream fanning right. Default depth 2 hops, expandable per-node. Clicking
any node re-centres. Sidebar shows the node's wiki link, note text, and
provenance. Selection is encoded in the URL (`/?node=relic-3&depth=3`) so views
are shareable — important for a public tool where people link each other
answers.

**Gaps view.** Stub nodes and zero-edge entities, sorted by neighbour
connectivity, so undocumented entities sitting in the middle of important chains
rank above peripheral ones. Doubles as a wiki-editing to-do list.

**System overview (secondary).** Whole-graph force-directed layout, filtered by
`system`. Orientation only — acknowledged to be a hairball at full scale.

### Rendering rules

- Node colour by `system`, shape by `kind`
- `confidence: unknown` nodes render with a dashed outline, muted
- `confidence: provisional` / `uncertain` edges render dashed
- `rel: requires` edges render visually distinct from `rel: boosts`
- `op` (when present) shown as an edge badge: `+` / `×` / `^`

## Maintenance

A scheduled GitHub Action runs `scrape.py` daily and opens a PR when
`data/raw/` changes. Because the scraper does no parsing, the PR is a plain
wikitext diff. The body separates:

- **New pages** — not previously present in `data/raw/`
- **Changed pages** — with per-page diff size
- **WIP flag changes** — pages that gained or lost `{{New Content}}`

New-page appearance is the highest-signal event on a wiki being actively filled
in, and must not be buried among text edits.

Merging the PR records that the change was *seen*, not that
`relationships.yaml` was updated for it. Applying the change is a separate,
human step.

Freshness is displayed in the app from the last `relationships.yaml` commit
date. Error reports route to GitHub issues; no custom infrastructure.

## v1 scope

**In** — Relics (70), Refine Tree (136), Tarot (78), Dilation Tree (13),
Zodiacs (12), Singularity + Plague (stub-heavy, high value), stat vocabulary
from IL2CPP enums (~50). Roughly **380 nodes**.

This covers the motivating chain end to end: ability-tree node → gold generation
→ relic upgrade → attack power.

**Deferred** — 575 achievements (collapsed to a single group node; they are
mostly leaves granting Souls/Time Flux), 100 common minerals, Elements.

### Build order

1. **Seed** — `scrape.py`, bootstrap scripts, and a reviewed
   `relationships.yaml` covering the motivating attack-power chain.
   `build.py` with validation and the coverage report. Deliverable: a valid
   `graph.json`.
2. **App** — focus view against the committed `graph.json`. Deliverable: a
   deployed site answering "what feeds X?".
3. **Automation** — the daily scraper Action and PR bot.
4. **Gaps view and system overview**, once the focus view is proven.

## Testing

- **Schema validation** in `build.py`, run in CI on every PR. This is the
  primary correctness gate, since bad data is the main failure mode.
- **Validator unit tests** covering each error and warning class, including the
  fuzzy-match suggestion output.
- **Golden-file test** rendering a small fixture `relationships.yaml` to a known
  `graph.json`.
- **Scraper test** confirming a non-200 response or empty page body fails
  loudly rather than writing an empty file into `data/raw/` — a silent empty
  scrape would show up as a mass deletion diff.

Bootstrap scripts are not tested; their output is reviewed by hand once and
then discarded as a code path.

No end-to-end browser tests in v1.

## Rejected alternatives

- **Sankey diagram** — encodes magnitude, which requires formulas that do not
  exist in any accessible source. Also undefined for cyclic graphs, and
  idle-game feedback loops guarantee cycles.
- **Whole-graph-only view** — unreadable past ~100 nodes.
- **Save-file import** — `ObscuredFileCrypto` encryption, CRC header, device
  locking via `DataFromAnotherDeviceDetected`.
- **A permanent extraction pipeline** — would require parsers for templates,
  wikitables, and effect-string regex, all maintained against a wiki whose
  newest content is its least structured, with failures that manifest as
  silently missing edges. Replaced by one-time bootstrap plus raw-text diffing.
- **A capture CLI** — an ergonomics layer over a schema the validator already
  checks. Its main value, catching typo'd node ids, is delivered by fuzzy-matched
  validator errors at a fraction of the cost.
- **Backend / graph database** — 450 nodes fits trivially in a static JSON file.

## Risks

| Risk | Mitigation |
|---|---|
| Hand-maintained YAML drifts behind a fast-moving wiki | Daily diff PR makes drift visible; `confidence` makes staleness explicit rather than silent |
| Curation burden exceeds appetite | v1 defers 675 low-value entities; coverage report prioritises by connectivity; the graph remains useful while incomplete |
| Scraper silently writes empty files, producing a mass-deletion diff | Scraper fails loudly on non-200 or empty body; covered by test |
| Bootstrap output contains systematic errors seeded into the YAML | Output reviewed before paste; `source` field records provenance for later audit |
| IL2CPP enum names are a decompilation artifact | Only identifier strings used as vocabulary; standard fan-tooling practice |
