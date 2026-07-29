# Bootstrap scripts

One-time seeding scripts, run by hand during initial dataset construction.

**These are not maintained.** They are not tested, not imported by `src/atlas`,
and not run by CI. They print YAML to stdout; a human reviews it and pastes it
into `data/relationships.yaml`.

If a script here stops working because the wiki changed, delete it rather than
fixing it — its job is already done.

`refine_tree.py` was removed in Task 10. The refine tree is now produced
repeatably by `atlas extract` (`src/atlas/extract/refine_tree.py`).
