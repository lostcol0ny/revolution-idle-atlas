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
its kind, wiki page and effects. A curated `effects` list replaces the generated
one. When it rewords exactly one effect and keeps the rest as they were, a
generated edge `note` that quotes the old wording takes the new one; a list that
adds, drops or reorders effects leaves notes alone. A curated edge replaces the
generated one wholesale. A
`suppress:` entry deletes a generated edge outright — the one correction an
overlay cannot express.

A third input, `data/game.yaml`, sits **between** them: precedence is
`derived.yaml` < `game.yaml` < `relationships.yaml`. It holds the game's own name
and description for the nodes it maps, so it corrects a wiki spelling, but a
curated field still wins. It carries no edges itself; `atlas extract` derives
edges from it (see [Edges from game text](#edges-from-game-text)). It is
written only by `atlas game` on a machine with the game installed, never by
`atlas extract` or `atlas build`, so CI rebuilds from the committed copy; when
it is absent the build is exactly the two-file merge. See
[Game files](#game-files).

One more file, `data/sweep.yaml`, is neither half of that pair. It is not data
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
| `data/game/` | Local only, git-ignored. Written by `atlas game` from your own game install; see [Game files](#game-files). |
| `data/game.yaml` | The game's names and descriptions, mapped onto node ids. Written by `atlas game`, read by `atlas build`. Committed. |

`data/derived.yaml`, `public/graph.json` and `docs/coverage.md` are build
products that are committed to the repository. CI rebuilds them and fails if the
result differs. If a CI run goes red on the artifact step, run
`uv run atlas extract && uv run atlas build` and commit the result. A change to
`data/raw/` — the most common trigger — requires the extraction step first;
running only `atlas build` will leave `data/derived.yaml` stale and the step
stays red.

`atlas extract` reads `data/relationships.yaml` and `data/game.yaml` as well as
`data/raw/`, because the curated stats and their aliases are the vocabulary it
matches effect prose against, and the game's descriptions are prose too. Adding
a stat node or an alias therefore changes `data/derived.yaml`, and a run of
`atlas build` alone will not pick it up. It still makes no network request,
which is what keeps it safe to run in CI.

## Commands

```sh
uv sync                  # install
uv run atlas build       # merge both dataset files, validate, then write the artifacts
uv run atlas build --check   # validate only; write nothing
uv run atlas extract     # parse data/raw/ into data/derived.yaml
uv run atlas scrape      # re-fetch data/raw/ from the wiki
uv sync --extra game     # also install UnityPy, needed only by `atlas game`
uv run atlas game        # read English strings from a local game install into data/game/ and data/game.yaml
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

Some warnings belong to `atlas extract` and appear only on an extraction run: a
manifest page that yields no records, a page named in the manifest with no file
in `data/raw/`, two manifest entries minting the same node id, a Tarot card
whose name another node already claims, a Tarot challenge with no card of its
name, or a Tarot page that no longer states the challenge reward (below).
Looking for them after `atlas build` finds nothing, because that command reads
neither `data/sweep.yaml` nor `data/raw/`. Each one names its own subject rather
than a file to open, because the fix can lie in the manifest, in
`data/relationships.yaml`, or nowhere at all when the wiki has simply been
re-worded.

A manifest page yielding no records is a **warning and not an error**, unlike one
of the four hand-written parsers producing no nodes, which is fatal. Those four
cover pages known to hold data, so zero means the page or the parser broke. A
manifest entry is a guess about a page's shape, and one wrong guess must not
block every build — including the artifact check in CI.

A colliding Tarot card name is warned about for the same reason. Card names are
read off a page volunteers edit, so a rename can put a card in contest with a
curated node; the card loses its place in the page vocabulary and the edges it
would have produced, and everything else extracts as usual.

The Tarot challenge tables have no reward column; the page states the reward
once, in prose above them: "Each Challenge provides a boost to the respective
cards effect". While that sentence is on the page, `atlas extract` gives every
swept challenge one `documented` `boosts` edge to its card, matched by name with
a leading "The" ignored (the challenge "Strength" is the card "The Strength").
The rest of that paragraph makes no edges: "a boost to the first effect of every
card in that suit" would be fourteen per challenge, and "All of your Tarot
Challenges combined boost Sacrifice Dust gain" is a boost from the set, not
from one challenge.

`atlas scrape` talks to a live, volunteer-run wiki. Do not run it in a loop. A
scheduled GitHub Actions workflow runs it daily and opens a pull request when the
raw wikitext changes; that PR touches `data/raw/` only.

## Game files

`atlas game` reads the game's own English text from a local Steam install
(`--install PATH`; the default is the standard Steam path on Windows). It needs
the optional `game` dependency group (`uv sync --extra game`) and fails with a
message naming what is missing when UnityPy or the install is absent. It never
runs in CI, which has no game; its one test against a real install is skipped
there.

It opens two Unity Localization bundles under
`Revolution Idle_Data/StreamingAssets/aa/StandaloneWindows64/`:
`localization-assets-shared_assets_all.bundle`, which maps entry ids to keys,
and `localization-string-tables-english(en)_assets_all.bundle`, which maps the
same ids to English text. It writes two files:

- `data/game/strings.en.json` — every string from the `menu` and `patch_note`
  tables, keyed by localization key, with the Steam `buildid` (from
  `steamapps/appmanifest_2763740.acf`, null if absent) and the Unity version.
- `data/game/catalog.yaml` — every family with numbered `<PREFIX>_NAME_<n>` and
  `<PREFIX>_DESC_<n>` keys (relics are `UNI_RELIC`), as `{index, name, desc}`
  lists. A missing half is null, so a gap is visible.

**The text is not value-free, and not a complete source of values either.**
Many descriptions are templates whose numbers the game fills in at runtime
(`{0}`), and its formulas are compiled code, not data. Others contain literal
numbers, such as achievement thresholds.

**`resources.assets` is never read.** Its TextAssets include developer test
saves, some named after real players.

Both of those outputs stay **local and are not committed**: `data/game/` is
git-ignored.

### `data/game.yaml`

`atlas game` then maps catalog families onto the nodes of the current
`data/derived.yaml` and `data/relationships.yaml`, and writes the result to
`data/game.yaml`, which **is** committed. Each entry is a node `id`, the game's
`name` (left out when the game only describes the entity, so the node keeps
the name it has), and its `description`, under the Steam `buildid` it was read
from. Unity rich-text tags are stripped. The numbers the game fills in at
runtime are worded by the sign beside them: `x{0}` becomes "a multiplier",
`^{0}` "an exponent", `/{0}` "a divisor", `{0}%` "a percentage", `+{0}` "an
amount", and a bare `{0}` "a value"; an operator chain such as `^^^{0}` keeps
its operators ("^^^ a value"). A running total such as `(total: x{1})`,
`(cur.: /{0})` or `(x{0} multiplier)`, or a closing `Currently: x{0}` line, is
dropped, since it is the player's state rather than the entity's. `atlas build`
overlays the name and description field by field on the generated node, and a
curated field still wins.

Only families with a clear home in the graph are mapped:

| Family | Onto | Matched by |
|---|---|---|
| `UNI_RELIC` | `relic-<n+1>` | Index, then verified by name. A near spelling (`Magestic` / `Majestic`) passes and is reported as a rename; an unrelated name is reported as unmatched. |
| `INF_CHL` | `infinity-challenge-<n+1>` | Index, verified by the `#<n+1>` the game writes in the name. Named `Infinity Challenge <n> (<title>)`. |
| `ETR_RP_UPGRADE` | `rp-upgrade-<n+1>` | Same as `INF_CHL`; named `RP Upgrade <n> (<title>)`. |
| `PLAGUE_ENDO_UPGRADE` | `plague-er-*` nodes in `plague` | Normalised name. |
| `UNI_MIN_COMMON` | `mineral-*` nodes in `minerals` | Normalised name. No node models a single common-mineral tier, so today all 100 are unmatched. |

Particles keeps its text outside the `_NAME_`/`_DESC_` pairs, so `atlas game`
reads three more families straight from the strings:

| Keys | Onto | Named |
|---|---|---|
| `PARTICLES_BONUS_<GRADE>_<n>` (Rank, Tier, Tetr, Pent) | `particles-<grade>-bonus-<n+1>` in `particles-grades` | By the wiki's Grade Bonuses threshold (`Rank 5 Bonus`), read from `data/raw/Particles.wikitext`, when the wiki lists exactly as many bonuses for that grade as the game has; otherwise by position (`Tetr Bonus #7`). The string is the description, with the formulas it spells out in plain text (`×(1 + 0.05 × rank)`) typeset as `$LaTeX$`; shorthand such as `^1.1` or `×tier` stays prose. |
| `EPSILON_EFFECT_<n>` | `epsilon-tree-a<n-14>` in `epsilon-tree` | `Epsilon Tree A<n-14> (<effect>)`, the label the game's Epsilon Tree screen gives the node; the effect is also the description. Only the 16 outer nodes A1–A16 (15–30) have one, and only those indices, checked against the screen, are labelled: any other, including one a patch adds, is reported unmatched. The 15 inner nodes (`epsilon-tree-b1`…`b8`, `c1`…`c4`, `d1`, `d2` and the centre, `epsilon-tree-epsilon`) share the template "Boosts {0} efficiency", which names no node, so they and their edges are curated in `data/relationships.yaml`: each boosts the two nodes outside it and requires them first. |
| `ENUM_SPARKTYPE_<COLOUR>`, `ENUM_SPARKTYPE_EFFECT_<COLOUR>` | `particles-spark-<colour>` | `UNI_PARTICLES_SPARK_NAME` (`Blue Spark`); the effect is the description. |

Each id is created when no node has it and overlaid when one does.

More families describe nodes the wiki already has. These never create a node:
an entity with no node, or outside the checked index range, is reported.

| Keys | Onto | Matched by |
|---|---|---|
| `UNI_MIN_REF_NODE_REWARD_<n>` | `refine-node-<n+1>` | Index, for 0–199, each checked against the wiki effect of that node. Description only. |
| `UNI_ELEM_TREE_NODE_EFFECT_<ELEMENT>_<n>` | `<element>-node-<n+1>` | Index, for the checked ranges: Fire and Water 0–10, Wind 0–11, Earth 0–9. Description only. |
| `ETR_CHA_REWD_<n>`, `ETR_CHL_NAME_<n>` | `eternity-challenge-<n+1>` | Index, verified by the `#<n+1>` in the name; named `Eternity Challenge <n> (<title>)`. |
| `INF_UPGRADE_NAME_<a>_<b>`, `INF_UPGRADE_REWD_<a>_<b>` | the `infinity-upgrade-<a>-<b>-*` node | Grid cell, verified by name; named `<a>;<b> <title>`. |
| `ETR_ANL_NAME_<a>_<b>`, `ETR_ANL_REWD_<a>_<b>` | `animal-*` in `animals` | Normalised name, else one near spelling. |
| `SING_MILESTONES_NAME_<SING\|ATOM\|PROG>_<n>`, `…_REWD_…` | `singularity-milestone-*` in the track's system | Same. |
| `TAROT_ARTIFACT_PART_NAME_<SUIT>_<n>`, `TAROT_ARTIFACT_PART_<n>_EFFECT_<SUIT>` | `tarot-artifact-*` | Same. |
| `UNI_TAROT_CARD_<SUIT>_<n>` with `…_EFFECT_1_…`/`…_EFFECT_2_…` | `tarot-*` in `tarot` | Same; the effects make the description, leaving out the Arcana's `Cooldown Time: {0}`. The card's `…_<SUIT>_REWARD_<n>` describes `tarot-challenge-<card>` (description only). |

No two entities map onto the same node; a second one is reported.

`ETR_MIL_REWD_<k>` is milestone k+1 on the game's Eternity › Milestones screen,
mapped onto `eternity-milestone-<Eternities needed>` using the thresholds read
off that screen (1, 2, 3, 5, 7, 8, 12, 14, 16, 32, 100). Unlike the families
above, a threshold the wiki has no node for creates one in
`eternity-milestones`. No node models a single tarot upgrade, so
`UNI_TAROT_UPGRADE_EFFECT_*` is reported, not mapped.

Every other family (achievements, `ACH`, among them) has no system to map onto
and is listed as skipped. An entity in the first four catalog families that no node
matches becomes a **new node** in the family's system, at confidence
`documented`, carrying `system` and `kind` in its entry; common minerals are
never created. Anything that cannot be placed — a name that disagrees with its
index, a name two nodes share, an id already taken — is reported per family as
unmatched rather than guessed. `atlas game` prints matched, added and unmatched
counts per family.

A game entry whose node has since disappeared (an extraction renamed its id) and
that names no system is a build **warning**; rerun `atlas game`.

### Edges from game text

`atlas extract`, not `atlas game`, turns `data/game.yaml` into edges, so they
follow the current vocabulary and CI rebuilds them without a game. Two kinds
come out, both with `source: game`:

- **Member links**, `documented`. Every grade bonus `requires` its grade
  (`particles-rank` and so on), every outer Epsilon Tree node (A1–A16) is
  `unlocks`ed by the `epsilon-tree` group, and every spark colour by the
  `particles-sparks` group.
  The game's help text states each; the prefixes live in
  `particles.MEMBER_LINKS`.
- **Description matches**, `uncertain`. The description of a node only the
  game describes — one `atlas game` created, carrying `system` — goes through
  the same resolver as wiki effect prose (see [How prose is
  read](#how-prose-is-read)). A node a wiki page already describes is matched
  on the wiki's effects alone, so one entity is never matched twice in two
  wordings. On top of the resolver's input rules, the game marks an improver as
  an input: "Refinement node 141 improves this bonus" and "(improved by
  refinement node 147)" give an edge *into* the bonus. A grade the text names
  ("+0.01 per rank", "Particle Rank boosts Luck") produces no edge: a bonus
  reads its grade, and the member link already says so.

Correct a wrong one the usual way: a curated edge plus a `suppress` entry in
`data/relationships.yaml`.

## The sweep manifest

`data/sweep.yaml` lets a wiki page be read without writing a parser for it. Each
entry names a page and says which of its columns or template fields carry an
entity's name and its effects.

Everything read through the manifest is deliberately low-confidence: swept nodes
are `provisional` and swept edges are `uncertain`, and `boosts` unless the column
is declared a requirement (below) or the sentence opens on an unlock (see [How
prose is read](#how-prose-is-read)). A column
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
| `effect_columns` | one of these three | Header names. **Each becomes a separate effect**, because a Zodiac really does have four independent bonuses. What an effect names becomes `node → named` `boosts`. |
| `text_columns` | one of these three | Header names kept on the node as effects, after `effect_columns`, and matched into no edge. For a restriction: a Tarot challenge's `Penalty` names the stats it resets and nerfs, and the matcher could only call that a boost. |
| `requirement_columns` | one of these three | Header names kept on the node as effects, after `text_columns`. A **plain threshold** cell turns what it names into `named → node` `requires`: a Tarot challenge's `Completion Requirement` ("Attack Level 3250") is a goal to reach, not something the challenge raises. Any other cell is text only (see below). |
| `per_level_column` | no | Only valid alongside exactly one `effect_columns` entry; with two there would be no way to say which effect it scales. |

An entry needs at least one column among the three column lists, and a column
may appear in only one of them.

A requirement cell is a plain threshold when its amount (`3250`, `105+`, `1e20+`,
`111,111+`, `x5e9`) sits at its start or its end and it holds no condition word
(`with`, `while`, `at`, `when`, `during`, `by`, `after`, `before`, `until`,
`within`): "Attack Level 3250", "105+ Max Mineral Level", "Merge Level 250+". An
action goal puts its number mid-sentence or behind a condition, and what it names
is not a stat to raise: in "Sell a Zodiac for exactly 67 Astrodust" the Astrodust
is the sale's proceeds, and in "Perform a Singularity at Attack Level 5005+" the
Singularity is a reset to perform. Such a cell stays on the node and makes no
edge. The rule reads the shape rather than a list of verbs, because "Merge Level
250+" opens with one.

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
read, so `Trials` needs only one entry to cover all five of its trial tables.

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
`atlas extract` produced them, then nodes that exist only in `data/game.yaml`,
then records that exist only in `data/relationships.yaml`, in that file's
order. A record that overrides an earlier one keeps the earlier one's position.
Keys within each object are sorted alphabetically. **Fields whose value is null
or an empty list are omitted
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
| `description` | string | no | The game's own description, from `data/game.yaml`. Runtime numbers are worded ("by a multiplier"), never `{0}`. |

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

**Prose fields carry inline math.** `text`, `per_level`, a node's `description` and an
edge's `note` are prose in one small format: a wiki `<math>` block becomes `$LaTeX$`,
and outside it a backslash escapes the next character (`\$` is a literal dollar, `\\` a
backslash), so the only bare `$` in a field delimits math. The viewer typesets those
segments with KaTeX and filters on the text with delimiters and escapes removed. Curated
text in `data/relationships.yaml` follows the same rule.

`aliases` exist because the wiki names one stat several ways — "Special Minerals Merge
Factor", "SMMF" and "Merge Factor" are one node. The extraction layer matches effect prose
against every node's `name` plus its `aliases`, longest surface form first. An
ALL-UPPERCASE alias is matched **case-sensitively** so that `AP` cannot fire inside
"Appears"; everything else is matched case-insensitively. Aliases shorter than three
characters are ignored unless they are ALL-UPPERCASE, where two is allowed. Every edge
produced by prose matching is stamped `confidence: uncertain`, because prose is weaker
evidence than a structural table cell.

#### How prose is read

A name found in a sentence is a target — `item boosts name` — unless the
sentence's shape says otherwise. The rules live in `extract/refs.py` (`resolve`)
and apply to every parser. They read one clause at a time: a full stop,
semicolon, " / " or a wiki `<br>` (which prose text shows as " / ") ends one.

- **Inputs point the other way.** A name after "based on", "by amount of",
  "boosted by", "affected by" or "improved by", or before the verb "boost(s)"
  ("Eternities ^2.00 boost DP gain"), is what the item reads, so the edge runs
  `name → item`. The noun does not count: "a boost to X", "Luck boost to
  Water" and the label "Singularity Mult Boost" name targets.
- **Kept and waived things are not boosted.** A clause with "keep … on"
  ("Keep Elements on Singularity Reset") or "does not spend" / "doesn't
  decrease" yields no edge.
- **A reset is not a target.** A name at most one word before "reset(s)"
  ("on Unity Reset", "Alpha Prestige resets nothing") or at most one word
  after "resets" ("Resets SMS Factor to 5,000") yields no edge.
- **An opening unlock is an unlock.** "Unlock(s) X" where X is the whole object
  ("Unlocks Singularity", "Unlock runes and rune upgrades", "Unlocks Plague
  Tab") gives `item unlocks X`. A name naming only a part or mode of the
  object ("Unlocks Auto Unity", "Unlocks Spark Mastery Factor for
  Singularity") yields no edge; what follows "on", "that", "which", "to" or
  "in" is read as usual.
- **A bracket glosses.** A name inside brackets ("(Attacks) Damage Mult",
  "Relic 26 effect (improves Quality donut)", "(see Plague)") is a target only
  when nothing outside the brackets names one.

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
| `source` | string | yes | Where the claim came from. A free string; the convention is `wiki:<PageName>`, `game` (derived from `data/game.yaml`), `game:<STRING_KEY>` (a curated edge citing one game string), `observed`, `il2cpp`, or `discord`. |
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
the React viewer still renders only v1's fields plus `description`. No component
reads `effects` or `targets_effect`, so the thing this pipeline exists to show is
not yet visible in the UI. This is a recorded sequencing decision: the schema
contract was fixed before any UI was built on it.

Every edge produced by the sweep carries `confidence: uncertain`. A consumer that
renders them identically to `documented` edges will present guesses as facts.

### Deployment

Deployed to Vercel as static files. There is no `vercel.json` and no rewrite
rules are needed — deep links use query parameters (`/?node=damage-mult`),
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
