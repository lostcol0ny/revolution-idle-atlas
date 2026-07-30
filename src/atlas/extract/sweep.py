import re
from dataclasses import dataclass
from pathlib import Path

from atlas.extract.manifest import Manifest, RecordTemplateEntry, SweepEntry, WikitableEntry
from atlas.extract.refs import (
    Vocabulary,
    derive_op,
    normalise_space,
    plain_text,
    resolve,
    slugify,
    template_fields,
)
from atlas.extract.result import ExtractResult
from atlas.models import Edge, EdgeConfidence, Effect, Node, NodeConfidence, Rel
from atlas.rawcheck import raw_filename

_TABLE_RE = re.compile(r"\{\|(.*?)\n\|\}", re.DOTALL)
_ROWSPAN_RE = re.compile(r'rowspan\s*=\s*"?(\d+)"?', re.IGNORECASE)


@dataclass(frozen=True)
class SweptRecord:
    """One row or template instance, reduced to the three things a node needs.

    Deliberately not a Node. Minting ids, resolving references and stamping
    confidence are identical for both readers, so they happen once in
    `sweep.extract` rather than twice here. It also means a reader's tests
    assert on strings, which is what actually changes when a wiki page is
    restructured.
    """

    name: str
    effects: list[str]
    per_level: str | None


@dataclass(frozen=True)
class _Cell:
    text: str
    colspan: bool
    rowspan: int


def effect_texts(raws: list[str]) -> list[str]:
    """Clean candidate effect cells and drop the ones that say nothing.

    A cell with no letters in it is never an effect. Plague's ER Upgrades table
    writes "<==" in its Effect column to mean "see the Name column", and such a
    cell can also never carry a reference the resolver could match, so keeping
    it would add nodes whose only stated effect is punctuation.

    Shared with the record_template reader, which needs exactly this rule.
    """
    texts = [plain_text(raw) for raw in raws]
    return [text for text in texts if any(char.isalpha() for char in text)]


def _split_outside(text: str, separator: str) -> list[str]:
    """Split on `separator`, but not inside a template or a link.

    A naive `split("||")` is safe today, but a naive `split("!!")` is not once a
    cell contains `{{Keyword|...}}`, and the two call sites should not differ in
    how much they can be trusted.
    """
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        pair = text[index : index + 2]
        if pair in ("{{", "[["):
            depth += 1
            index += 2
            continue
        if pair in ("}}", "]]"):
            depth = max(0, depth - 1)
            index += 2
            continue
        if depth == 0 and text.startswith(separator, index):
            parts.append(text[start:index])
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(text[start:])
    return parts


def _cell(raw: str) -> _Cell:
    """Strip a cell's HTML attributes off its content.

    Split on the FIRST pipe, not the last: `data-sort-value=1 | {{ZodiacBadge|
    Aries}}` has two pipes and splitting on the last one yields "Aries}}".

    The left side is attributes only when it contains `=` and no markup, so a
    cell whose own text contains a pipe — `Foo [[Bar|Baz]]` — is left alone.
    """
    head, separator, tail = raw.partition("|")
    if separator and "=" in head and "[[" not in head and "{{" not in head:
        span = _ROWSPAN_RE.search(head)
        return _Cell(tail, "colspan" in head.lower(), int(span.group(1)) if span else 1)
    return _Cell(raw, False, 1)


def _groups(body: str) -> list[tuple[bool, list[str]]]:
    """Cut a table body into `|-`-separated groups, flagging the header ones.

    Classifying by group rather than by position is what makes this work on
    every page: Dilation_Tree opens with a data-shaped caption row ABOVE its
    header row, and Plague repeats a header row in the MIDDLE of its data. Any
    rule phrased as "headers are what comes before the first data cell" reads
    one of those two pages wrong.
    """
    groups: list[tuple[bool, list[str]]] = []
    current: list[str] = []
    is_header = False

    def flush() -> None:
        if current or is_header:
            groups.append((is_header, list(current)))

    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("|+"):
            # `|+` is the table caption. It starts with a pipe like a data cell,
            # and read as one it shifts every following row by a column.
            continue
        if stripped.startswith("|-"):
            flush()
            current.clear()
            is_header = False
            continue
        if stripped.startswith("!"):
            is_header = True
            current.extend(_split_outside(stripped[1:], "!!"))
            continue
        if stripped.startswith("|"):
            current.extend(_split_outside(stripped[1:], "||"))
            continue
        if current:
            # A long cell wrapped onto the next source line with no leading
            # pipe. Dropping it truncates the effect text mid-sentence.
            current[-1] = current[-1] + " " + stripped
    flush()
    return groups


def _headers_and_rows(body: str) -> tuple[list[str], list[list[_Cell] | None]]:
    headers: list[str] = []
    rows: list[list[_Cell] | None] = []
    for is_header, raws in _groups(body):
        cells = [_cell(raw) for raw in raws]
        if is_header:
            if not headers:
                # A colspan header cell is a caption ("! colspan=4 |ER
                # Upgrades"), not a column. Counted as one, the table is a
                # column too wide and every real row is rejected.
                named = [normalise_space(c.text) for c in cells if not c.colspan]
                if len(named) >= 2:
                    headers = named
            # None marks a boundary that also breaks any rowspan in progress.
            rows.append(None)
            continue
        rows.append(cells)
    return headers, rows


def _aligned_rows(rows: list[list[_Cell] | None], width: int):
    """Yield rows of exactly `width` cells, carrying rowspan cells downward.

    Rowspan is not an edge case to skip past: on Dilation_Tree the rowspan
    column IS the name column, so dropping short rows would lose three records
    in every four. Carrying the held cell down is what the rendered HTML page
    already shows, so this reads the table correctly rather than guessing.

    A row that still does not reach `width` — or that has cells left over — is
    skipped. That is the precision-first choice: a misaligned row would attach
    one entity's name to another's effect.
    """
    carried: dict[int, tuple[str, int]] = {}
    for cells in rows:
        if cells is None or any(cell.colspan for cell in cells):
            carried.clear()
            continue
        row: list[str] = []
        pending = list(cells)
        for column in range(width):
            held = carried.get(column)
            if held is not None:
                text, remaining = held
                row.append(text)
                if remaining > 1:
                    carried[column] = (text, remaining - 1)
                else:
                    del carried[column]
                continue
            if not pending:
                break
            cell = pending.pop(0)
            row.append(cell.text)
            if cell.rowspan > 1:
                carried[column] = (cell.text, cell.rowspan - 1)
        if len(row) != width or pending:
            continue
        yield row


def read_wikitable(raw: str, entry: WikitableEntry) -> list[SweptRecord]:
    """Read every table on the page whose headers match the manifest entry.

    Every matching table is read, not just the first: Trials repeats the same
    four columns once per difficulty tier, and stopping at the first table would
    sweep the easy trials and silently drop the rest.
    """
    records: list[SweptRecord] = []
    for match in _TABLE_RE.finditer(raw):
        headers, rows = _headers_and_rows(match.group(1))
        if not headers:
            continue
        column_of = {name: index for index, name in enumerate(headers)}
        wanted = [*entry.name_columns, *entry.effect_columns]
        if entry.per_level_column is not None:
            wanted.append(entry.per_level_column)
        if any(headers.count(name) > 1 for name in wanted):
            # Minerals lays two independent upgrade tables side by side in one
            # wikitable, so its headers read "Upgrade|Effects|Cost Scaling|
            # Upgrade|Effects|Cost Scaling". `column_of` keeps only the last of
            # each, which would read the right-hand half and silently drop the
            # left. Skipping the table loses the same rows, but visibly: the
            # page reports zero records and the manifest entry gets a warning.
            continue
        if any(name not in column_of for name in entry.name_columns):
            continue
        present = [name for name in entry.effect_columns if name in column_of]
        if not present:
            continue
        for row in _aligned_rows(rows, len(headers)):
            name = normalise_space(
                " ".join(plain_text(row[column_of[c]]) for c in entry.name_columns)
            )
            effects = effect_texts([row[column_of[c]] for c in present])
            if not name or not effects:
                continue
            per_level = None
            if entry.per_level_column in column_of:
                per_level = plain_text(row[column_of[entry.per_level_column]]) or None
            records.append(SweptRecord(name=name, effects=effects, per_level=per_level))
    return records


def _instances(raw: str, template: str) -> list[str]:
    """Return the body of every `{{template|...}}` on the page.

    Braces are counted rather than matched with a regex so that an instance
    written inline is found as readily as one closing on its own line, and so a
    nested {{Keyword|...}} inside an effect cannot end the instance early.

    Case-insensitive on the template name, matching `_unwrap_template`: the wiki
    writes both `{{Keyword|...}}` and `{{keyword|...}}` for the same template.
    """
    needle = ("{{" + template).lower()
    lowered = raw.lower()
    bodies: list[str] = []
    index = 0
    while True:
        start = lowered.find(needle, index)
        if start == -1:
            return bodies
        after = start + len(needle)
        # The name has to end here. Without this, a search for
        # "Minerals/Special_Minerals" also matches
        # "{{Minerals/Special_MineralsV2" and reads its fields as this one's.
        if raw[after:].lstrip()[:1] not in ("|", "}"):
            index = after
            continue
        cursor = start + 2
        depth = 1
        while cursor < len(raw) and depth:
            pair = raw[cursor : cursor + 2]
            if pair in ("{{", "[["):
                depth += 1
                cursor += 2
            elif pair in ("}}", "]]"):
                depth -= 1
                cursor += 2
            else:
                cursor += 1
        if depth:
            # Unterminated. Everything after this point is unreadable, and
            # guessing where the instance ended would invent a record.
            return bodies
        bodies.append(raw[after : cursor - 2])
        index = cursor


def read_record_template(
    raw: str, entry: RecordTemplateEntry
) -> list[SweptRecord]:
    """Read every instance of one record template on the page."""
    records: list[SweptRecord] = []
    for body in _instances(raw, entry.template):
        fields = template_fields(body)
        name = plain_text(fields.get(entry.name_field.lower(), ""))
        effects = effect_texts(
            [fields[f.lower()] for f in entry.effect_fields if f.lower() in fields]
        )
        if not name or not effects:
            continue
        per_level = None
        if entry.per_level_field is not None:
            per_level = plain_text(fields.get(entry.per_level_field.lower(), "")) or None
        records.append(SweptRecord(name=name, effects=effects, per_level=per_level))
    return records


def _read(raw: str, entry: SweepEntry) -> list[SweptRecord]:
    if isinstance(entry, WikitableEntry):
        return read_wikitable(raw, entry)
    return read_record_template(raw, entry)


def _build(
    record: SweptRecord, entry: SweepEntry, vocabulary: Vocabulary
) -> ExtractResult:
    name = record.name
    if entry.name_prefix is not None:
        name = f"{entry.name_prefix} {name}"
    node_id = f"{entry.id_prefix}-{slugify(name)}"
    per_level = record.per_level
    effects = [
        Effect(
            text=text,
            # The manifest permits per_level only alongside a single effect
            # column or field, so there is never a second effect it could have
            # belonged to instead.
            per_level=per_level if index == 0 else None,
            op=derive_op(per_level) if index == 0 else None,
        )
        for index, text in enumerate(record.effects)
    ]
    node = Node(
        id=node_id,
        name=name,
        system=entry.system,
        kind=entry.kind,
        wiki=entry.page,
        # The wiki names this entity in a table, so it exists. `provisional`
        # says nobody has reviewed the reading — not that its existence is in
        # doubt, which is what `unknown` would mean.
        confidence=NodeConfidence.PROVISIONAL,
        effects=effects,
    )

    edges: list[Edge] = []
    for effect in effects:
        for reference in resolve(effect.text, vocabulary):
            if reference.target_id == node_id:
                # "Red Gem gain is doubled" is how the wiki writes a
                # self-scaling effect. validate_dataset rejects a self-edge as
                # an error, so emitting one turns normal phrasing into a broken
                # build.
                continue
            edges.append(
                Edge(
                    from_=node_id,
                    to=reference.target_id,
                    # Always `boosts`. The sweep's job is finding that a
                    # relationship exists; deciding it is really an unlock or a
                    # requirement is curation, and guessing from prose is how a
                    # wrong edge gets made. `op` is left unset for the same
                    # reason — the effect carries it, the edge does not claim it.
                    rel=Rel.BOOSTS,
                    targets_effect=reference.targets_effect,
                    source=f"wiki:{entry.page}",
                    # Prose matching is weaker evidence than a structural table
                    # cell. This is the one field standing between the sweep and
                    # hundreds of guesses asserted as fact.
                    confidence=EdgeConfidence.UNCERTAIN,
                )
            )
    return ExtractResult(nodes=[node], edges=edges)


def extract(
    raw_dir: Path, manifest: Manifest, vocabulary: Vocabulary
) -> ExtractResult:
    """Sweep every page the manifest names.

    A page that cannot be read is a warning, never an error. `run_all` raises
    when one of the four hand-written parsers returns nothing, because those
    pages are known to hold data. A manifest entry is a guess about a page's
    shape, and under the same rule one wrong guess would block every build —
    including the CI artifact guard.
    """
    result = ExtractResult()
    # Two entries can name the same entity: Minerals describes its ten Special
    # Minerals once as templates and again in a later table with different
    # effect wording. `to_yaml`'s node dedup is first-wins, so the second
    # reading would vanish with nothing to say it had. Report it instead.
    minted: dict[str, str] = {}
    for entry in manifest.pages:
        path = raw_dir / raw_filename(entry.page)
        if not path.is_file():
            result.warnings.append(
                f"sweep page '{entry.page}': no {path.name} in data/raw/ — "
                "the manifest names a page the scrape does not fetch"
            )
            continue
        records = _read(path.read_text(encoding="utf-8"), entry)
        if not records:
            result.warnings.append(
                f"sweep page '{entry.page}': the {entry.reader} reader found no "
                "records — the page's shape has probably changed"
            )
            continue
        for record in records:
            built = _build(record, entry, vocabulary)
            node_id = built.nodes[0].id
            owner = minted.get(node_id)
            if owner is not None:
                result.warnings.append(
                    f"sweep page '{entry.page}': node id '{node_id}' was already "
                    f"minted from '{owner}' — the later reading is discarded"
                )
                continue
            minted[node_id] = entry.page
            result.extend(built)
    return result
