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
