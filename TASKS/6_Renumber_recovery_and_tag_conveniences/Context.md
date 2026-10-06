# LLM Agent Context Log

## 2026-10-06 Implementation (items 2-5 of Claude's suggestions)

* Renumber recovery: `renumber()` plans renames (`old` -> `temporary`
  `.renumber_N` -> `new`, plus `old_number`/`new_number`) and
  `do_renumber(renames, phase)` writes `.renumber.json`
  (`{"phase", "renames"}`), does phase 1 (old -> temporary), records
  phase 2, does phase 2 (temporary -> new), phase 3 (headings), then
  removes the marker.  Every step is skipped if already done.  The
  recorded phase matters: if two items share a title, a new name can be
  another item's old name, so phase 1 must not be redone after phase 2
  has started.  `recover_renumber()` runs on every load before
  `load_items()` and reports to stderr.  If the marker can not be
  written nothing moves (and nothing changes in memory).  Test hook:
  `TRACKER_TEST_RENUMBER_INTERRUPT=N` raises `RenumberInterrupted` after
  N steps; `_test_recovery` interrupts a same-title swap after each of
  its 9 steps.
* `tracker TAG COMMAND ...` (`tag_collection()`, `TAG_COMMANDS`): the
  tag becomes the command's first argument; not for create/enable/
  disable/help.  Collection names still win over tags.
* `show NUMBER` (`show_command()`): number, tag, title, state, priority
  (if enabled), created/updated, directory, history, then `Details.md`.
  `s` is now ambiguous (show, suspend).
* Tag references: after a rename that changes the tag,
  `update_references()` uses `tag_references(root, tag)` (writable
  `.md` files under the collections' parent directory; hidden
  directories and symbolic links skipped, so `RULES/` is not searched;
  whole-tag match via `tag_pattern()`), lists them, and asks
  "OK to update them? (y=Yes, n=No)".  No version control searching.
* 325 checks; coverage misses only `# pragma: no cover` lines.
* Still to discuss: item 1, keeping closed items in `Startup.md` more
  compactly.

## 2026-10-06 Closed items (item 1)

* Closed items are no longer imported by `Startup.md`; it imports a
  generated `TASKS/Closed.md` last (only if something is closed; the file
  is removed when nothing is).  `write_closed()` lists the
  `CLOSED_SUMMARIES` (50; `TRACKER_TEST_CLOSED_SUMMARIES` overrides) most
  recently closed items (by the last Closed entry in their history,
  `closed_time()`) with tag, title, closing date and the `## Summary`
  section of their `Context.md` (`context_summary()`; "(no summary)" if
  missing), then the rest as "- `TAG` Title".
* The user's call: the summary lives in `Context.md` because the user may
  be editing `Details.md`.  Claude writes `## Summary` before closing
  (now in `Tracker_Rules.md`); task 1's summary was written this way.
* 333 checks; coverage misses only `# pragma: no cover` lines.
