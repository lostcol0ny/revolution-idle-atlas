from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from atlas.models import Kind


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The wiki page TITLE, not the filename. `rawcheck.raw_filename` converts
    # a title to a file stem (" " -> "_", "/" -> "__"), and the same string is
    # written to each swept node's `wiki` field — so "Minerals/Refine_Tree"
    # style titles work without a second field to keep in sync.
    page: str
    system: str
    kind: Kind
    id_prefix: str
    # Prepended to the name, for a table whose name column is a bare number.
    # Singularity's tree table numbers its rows "1", "2", "3.1"; a node named
    # "1" is useless in the UI. With `name_prefix: Tree Node` it reads "Tree
    # Node 1". Display only: the id is minted from the raw name, where
    # `id_prefix` already supplies the noun.
    name_prefix: str | None = None

    @field_validator("page")
    @classmethod
    def _page_is_underscored(cls, value: str) -> str:
        """Reject a space in the title, because only the file lookup forgives it.

        `rawcheck.raw_filename` normalises " " to "_", so "Dilation Tree" finds
        the right file and the sweep reads the page. The verbatim string is what
        lands in each node's `wiki` field, though, and the coverage report
        compares that against `coverage.page_title`, which always underscores —
        so a spaced title reads the page and then reports it as never swept, with
        the pipeline succeeding either way. One accepted spelling is cheaper than
        reconciling two.
        """
        if " " in value:
            raise ValueError(
                f"page '{value}' contains a space — write the underscored form "
                f"'{value.replace(' ', '_')}', which is what the wiki: field on "
                "every node in this repo uses"
            )
        return value


class WikitableEntry(_Entry):
    reader: Literal["wikitable"]
    # Joined with a space when a page needs two columns to name a row uniquely
    # (Dilation_Tree's rows are identified by Axis + Index, neither alone).
    name_columns: list[str] = Field(min_length=1)
    # Restricts the entry to the one table carrying this `|+` caption, so a page
    # that repeats a column layout can still be swept into different systems.
    # Singularity's three milestone tables are all Name/Requirement/Reward and
    # are told apart only by their captions; without this the entry takes all
    # three and every milestone lands in one bucket. Matched against the whole
    # caption, not a prefix, so a later "Atom Milestones II" is a new table the
    # entry ignores rather than a silent second source of rows.
    caption: str | None = None
    # A list because one row can carry several effects: a Zodiac has four
    # bonus columns and each is a separate effect, not one concatenated blob.
    effect_columns: list[str] = Field(min_length=1)
    per_level_column: str | None = None

    @model_validator(mode="after")
    def _per_level_needs_one_effect(self) -> Self:
        if self.per_level_column is not None and len(self.effect_columns) != 1:
            raise ValueError(
                "per_level_column requires exactly one effect_column, "
                f"got {len(self.effect_columns)}"
            )
        return self


class RecordTemplateEntry(_Entry):
    reader: Literal["record_template"]
    template: str
    name_field: str
    effect_fields: list[str] = Field(min_length=1)
    per_level_field: str | None = None

    @model_validator(mode="after")
    def _per_level_needs_one_effect(self) -> Self:
        if self.per_level_field is not None and len(self.effect_fields) != 1:
            raise ValueError(
                "per_level_field requires exactly one effect_field, "
                f"got {len(self.effect_fields)}"
            )
        return self


SweepEntry = Annotated[
    WikitableEntry | RecordTemplateEntry, Field(discriminator="reader")
]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[SweepEntry] = []

    @model_validator(mode="after")
    def _no_id_prefix_contains_another(self) -> Self:
        """Reject an `id_prefix` that is a proper prefix of another entry's.

        Node ids are `{id_prefix}-{slug}`, so nested prefixes put two entries one
        row name apart from minting the same id: with `singularity` alongside
        `singularity-tree`, a milestone called "Tree Node 7" mints
        `singularity-tree-node-7`, and whichever entry runs second loses its
        reading to the first-wins dedup. Two entries sharing one prefix exactly
        is a different thing — that is one page read twice — and stays allowed.

        Rejected at load time because it is a mistake in this file that can be
        seen without reading a single wiki page.
        """
        prefixes = [entry.id_prefix for entry in self.pages]
        for prefix in prefixes:
            for other in prefixes:
                if other != prefix and other.startswith(prefix):
                    raise ValueError(
                        f"id_prefix '{prefix}' is a prefix of id_prefix "
                        f"'{other}' — the two entries can mint the same node "
                        "id, so give one of them a longer, distinct prefix"
                    )
        return self


def load_manifest(path: Path) -> Manifest:
    """Read the sweep manifest, or return an empty one if it does not exist.

    Absence is silent because the sweep is additive: a checkout with no
    `data/sweep.yaml` must still extract the four original pages.

    Parsed with `yaml.SafeLoader` for the same reason `atlas.loader` is — a
    data file may never construct a Python object.
    """
    if not path.is_file():
        return Manifest()
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
    return Manifest.model_validate(data or {})
