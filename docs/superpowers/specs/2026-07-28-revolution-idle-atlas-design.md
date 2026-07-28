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
4. Stay current with a wiki that changes daily, without daily manual effort.

## Non-goals

- **Not a calculator.** No numeric predictions, no "which upgrade is better."
- **Not a wiki replacement.** Every node links out to the wiki for detail.
- **Not a save-file analyser.** See "Rejected alternatives."

## Research findings that constrain the design

Established by investigation on 2026-07-28:

| Finding | Consequence |
|---|---|
| ~450 graph-relevant entities, ~600–900 edges | Client-side rendering. No backend, no graph DB. |
| No Cargo, no Semantic MediaWiki, no Lua data tables | No structured query interface. Must parse wikitext. |
| Mature pages use consistent named-param templates | Template parser handles the majority of established content. |
| **New pages use raw `{| wikitable` markup instead** | Wikitable parser is required, not optional. |
| Refine Tree encodes prerequisites as `req = 8,15` | 136 nodes / 158 edges extractable with zero heuristics. |
| Effect strings use a controlled vocabulary with `+` `x` `^` sigils | ~30 regex rules cover an estimated 70–80% of remaining edges. |
| Relic effects wikilink their targets | Relic→system edges come from link targets. |
| IL2CPP dump exposes stat enums, method bodies empty | Canonical stat vocabulary available. Formulas are not. |
| Saves are encrypted, CRC-hashed, device-locked | Save import is not viable. |
| `{{New Content}}` template flags WIP pages (currently `Singularity`, `Plague`) | Machine-readable provisional-data marker. |
| 100 main-ns edits and 3 new pages in 16 days, against 77 articles | Daily scrape cadence. New-page detection matters. |
| wiki.gg returns 403 to default Python user-agent | Scraper must send a descriptive UA. |

The decisive finding: **the actual numeric formulas are unavailable from every
source.** This is why the tool encodes topology only — it is a constraint, not a
scoping preference.

## Data model

Two hand-writable YAML files under `data/`, checked into git. YAML over JSON
because they are edited by hand and reviewed as diffs.

### Nodes

```yaml
- id: relic-3                 # stable slug, referenced by edges
  name: Relic 3
  system: unity               # revolution|infinity|eternity|unity|zodiac|
                              # mineral|tarot|singularity|plague
  kind: relic                 # relic|stat|tree-node|currency|tarot-card|
                              # upgrade|group
  wiki: Relics#Relic_3        # deep link, may be omitted for stubs
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
- from: refine-node-121
  to: singularity
  rel: unlocks                # boosts|unlocks|requires
  op: exp                     # add|mult|exp — optional, free from source sigil
  note: "Singularity is unlocked by Refine Node 121"
  source: wiki:Singularity    # wiki:PageName | observed | il2cpp | discord
  confidence: provisional     # documented|provisional|uncertain
```

Field rationale:

- **`rel`** — `requires` (Refine Tree prerequisites) and `boosts` (stat effects)
  are different relationships and must not render identically. Derived from
  which parser produced the edge.
- **`op`** — the `+` / `x` / `^` sigil is already present in wiki effect strings,
  so capturing the operator *class* costs no extra curation. It is not a
  formula: no coefficients, no per-level values. Lets multiplicative chains be
  spotted at a glance.
- **`source`** — provenance. `observed` covers relationships learned from
  personal gameplay that the wiki has not documented.
- **`confidence`** — auto-set to `provisional` when the source page carries
  `{{New Content}}`. Rendered as dashed/muted edges so a visitor can judge
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

## Pipeline

```
MediaWiki API (descriptive User-Agent required)
     │  scrape.py
     ▼
data/raw/<Page>.json              checked in, one file per page, diffable
     │  extract.py                template parser + wikitable parser + regex rules
     ▼
data/edges.generated.yaml         NEVER hand-edited
data/nodes.generated.yaml         NEVER hand-edited
     +
data/edges.curated.yaml           ONLY hand-edited; additions AND overrides
data/nodes.curated.yaml           ONLY hand-edited
     │  build.py                  merge, validate, report
     ▼
public/graph.json                 single build artifact the app fetches
docs/coverage.md                  generated gap report
```

### The generated/curated split

This is the load-bearing structural decision. If the scraper wrote into files
that are also hand-edited, every re-run would either clobber curation or force a
manual merge — and after that happens twice, re-scraping stops being habitual on
a wiki that changes daily.

Separate files make re-scraping a safe, boring operation. Curated entries may
both **add** new edges and **override** incorrect generated ones by `(from, to,
rel)` key, so a wrong scraped edge is corrected without touching generated
output.

### Extraction tiers

1. **Structural** — `{{RN|…|req = 8,15}}` prerequisite lists, entity
   names/ids/costs. Pure template parsing, no heuristics.
2. **Wikitable** — newer pages. Singularity's tables have explicit
   `Resource Affected` and `Modification Source` columns, which is an edge list
   in tabular form.
3. **Regex over effect strings** — `Relic \d+`, `Refine Node \d+`,
   `(boosts|powered to|stronger|multiplied by)`, operator sigils.
4. **Wikilink targets** — relic effects link their targets; the link target is
   the edge destination.
5. **Hand-curated** — the remainder, plus corrections, plus `observed` edges.

Target: ~75% of edges generated, remainder curated. Fully automated extraction
is not a goal.

### Validation (`build.py`)

Errors (fail the build):
- Dangling edge references to nonexistent node ids
- Duplicate node ids
- Malformed enum values in `system`, `kind`, `rel`, `op`, `confidence`

Reports (never fail the build):
- Orphan nodes with zero edges — the curation to-do list
- Cycles — feedback loops are real mechanics and are surfaced, not rejected
- Entities present in IL2CPP enums but absent from the wiki — known-unknowns
  enumerable without playing
- Coverage percentages per system

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
any node re-centres. Sidebar shows the node's wiki link, raw effect text, and
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
- `confidence: provisional` edges render dashed
- `rel: requires` edges render visually distinct from `rel: boosts`
- `op` (when present) shown as an edge badge: `+` / `×` / `^`

## Maintenance

A scheduled GitHub Action runs `scrape.py` daily and opens a PR when the output
diff is non-empty. The PR body separates:

- **New entities** — pages or template invocations not previously seen
- **Changed effects** — existing entities whose effect text was edited
- **Newly flagged WIP** — pages that gained or lost `{{New Content}}`

New-page appearance is the highest-signal event on a wiki being actively filled
in, and must not be buried among text edits.

Freshness is displayed in the app from the last merge date, satisfying the
"current as of" marker. Error reports route to GitHub issues; no custom
infrastructure.

## v1 scope

**In** — Relics (70), Refine Tree (136), Tarot (78), Dilation Tree (13),
Zodiacs (12), Singularity + Plague (stub-heavy, high value), stat vocabulary
from IL2CPP enums (~50). Roughly **380 nodes**.

This covers the motivating chain end to end: ability-tree node → gold generation
→ relic upgrade → attack power.

**Deferred** — 575 achievements (collapsed to a single group node; they are
mostly leaves granting Souls/Time Flux), 100 common minerals, Elements.

### Build order

The pipeline and the app are independent past the `graph.json` contract, and
should be built in this order:

1. **Pipeline** — `scrape.py`, `extract.py`, `build.py`, schema validation, and
   a hand-curated seed covering the motivating attack-power chain. Deliverable
   is a valid `graph.json` plus a coverage report.
2. **App** — focus view against the committed `graph.json`. Deliverable is a
   deployed site answering "what feeds X?".
3. **Automation** — the daily scraper Action and PR bot. Deliberately last: it
   is only worth building once the parsers are stable enough that a daily diff
   is signal rather than noise.

Gaps view and system overview follow once the focus view is proven.

## Testing

- **Parser unit tests** against checked-in wikitext fixtures, including at least
  one template-style page and one wikitable-style page (Singularity).
- **Schema validation** in `build.py`, run in CI on every PR — this is the
  primary correctness gate, since bad data is the main failure mode.
- **Golden-file test** on a small fixture wiki subset producing a known
  `graph.json`.
- **Regression guard:** the scraper PR bot failing to parse a page must fail
  loudly rather than silently emitting fewer edges. A drop in extracted edge
  count beyond a threshold fails the build.

No end-to-end browser tests in v1.

## Rejected alternatives

- **Sankey diagram** — encodes magnitude, which requires formulas that do not
  exist in any accessible source. Also undefined for cyclic graphs, and idle-game
  feedback loops guarantee cycles.
- **Whole-graph-only view** — unreadable past ~100 nodes.
- **Save-file import** — `ObscuredFileCrypto` encryption, CRC header, device
  locking via `DataFromAnotherDeviceDetected`.
- **Fully automated extraction** — tier 5 content requires human judgement;
  budgeting for 100% coverage would produce silently wrong edges.
- **Backend / graph database** — 450 nodes fits trivially in a static JSON file.

## Risks

| Risk | Mitigation |
|---|---|
| Wiki restructures and breaks parsers | Parsers fail loudly; edge-count regression guard; raw JSON checked in for diffing |
| Curated data drifts out of sync with a changing wiki | Daily PR surfaces changes; `confidence` field makes staleness visible rather than silent |
| Hand-curation burden exceeds appetite | v1 deliberately defers 675 low-value entities; coverage report prioritises by connectivity |
| IL2CPP enum names are a decompilation artifact | Only identifier strings used as vocabulary; standard fan-tooling practice |
