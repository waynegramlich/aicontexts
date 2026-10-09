# LLM Agent Context Log

## Progress

* Step 1 is done: `transfer NUMBER COLLECTION [PLACE]` (`check_transfer()`,
  `transfer_items()`, `transfer_item()`, `transfer_command()` in
  `tracker.py`), with `moves` in `.item.json` and "Transfers:" in `show`.
  Tests: `_test_transfer()` and `_test_transfer_failures()`.  It renames
  directories and renumbers with no transfer plan yet (step 2).
* Step 2 is done: `transfer_items()` plans everything first (target room
  for all siblings at once via `plan_place(..., count)`, new tags, source
  gap renames) and `do_transfer()` runs it in 4 idempotent phases with
  `.transfer.json` in the source: move dirs to `.transfer_N` in the target,
  renumber the source, renumber the target, then fix headings,
  `.item.json` and rename.  `recover_transfers()` runs at the start of
  every `Items` load (before `recover_renumber()`), for all sibling
  collections, since the target has gaps mid-transfer.  `do_renumber()`
  is now a module function; `renumber()` uses `rename_records()` and
  `apply_renames()`.  Tests: `_test_transfer_failures()`,
  `_test_transfer_recovery()` / `_test_interrupted_transfer()` (interrupt
  after every step, two scenarios).
* Step 3 is done: `update_references()` takes a dict of old to new tags
  and changes them all in one pass (one combined pattern, so a new tag is
  never changed again); `rename` passes one tag, `transfer` all of the
  transferred ones.  Step 4 (docs) is left.
