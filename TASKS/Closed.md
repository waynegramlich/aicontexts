# Closed Items

<!-- Written by tracker; do not edit. -->

The most recently closed items (up to 50), with summaries:

- `T.c` Cleanup (closed 2026-10-06):
  Renamed Task/phrase/status/identifier to Item/title/state/number.  States:
  Pending (new items), Open, Reference, Suspended, Closed; Open and Reference
  items get their `Context.md` loaded.  `.status` became `.item.json` (state,
  UTC `created`/`updated`, state `history`, later `tag` and `priority`); an old
  `.status` is migrated on load.  `TASKS/Startup` became `TASKS/Startup.md`.
  `README.md` was rewritten and `Tracker_Rules.md` added; `CLAUDE.md` imports
  it instead of `RULES/Task_Tracking_Rules.md`, which `../alt_venv` still uses
  with `RULES/task.py` (`claude_notes/task.py` will eventually be deleted).
- `T.smic` Support Multiple Item Collections (closed 2026-10-06):
  A collection is any directory holding `.tracker.json`, found in the
  current directory or the nearest parent that has any.  Commands are
  `tracker COLLECTION COMMAND ...`; collection and command names take any
  unique case-insensitive prefix, and an ambiguous one lists the options.
  `tracker NAME create` makes a collection (name as typed, beside the others,
  after a yes/no prompt).  `--help`/`--test` are options.  The one
  `TASKS/Startup.md` covers every collection (e.g. `@../ISSUES/...`).
- `T.asfi` Add support for Issues (closed 2026-10-06):
  Created `ISSUES/` (prefix `I.`).  Tags: the first letter of each title word,
  lower case, ignoring a/an/of/the; unique per collection and stable -- a clash
  gives the new item the lowest free number (`cde2`), the first keeps `cde`,
  because tags show up in commit messages.  Priority 0 (catastrophic) to 3
  (low) is optional in `.item.json`; `enable`/`disable priority` per
  collection (on for ISSUES) shows a priority column and sorts `ls` by it.
- `T.msfhn` More support for hierarchical numbers (closed 2026-10-06):
  Numbers never have gaps (if 1.3 exists, so do 1.1 and 1.2); they are
  positions that change, so text uses tags only.  Tag prefixes are the
  collection's capitalized first letter (`T.`, `I.`), unique across
  collections; commands take a tag wherever they take a number.  `create` and
  `move` take a place: the next free NUMBER, `before NUMBER` or `after NUMBER`.
  `delete` is permanent, refuses children unless `-r` (which asks), and
  renumbers.  Hand-made gaps are renumbered on load.  `rename NUMBER to
  TITLE`.  Undo/redo was built and then removed: version control is the undo,
  and a move or rename more than an hour after the last one recommends a
  snapshot and asks to continue (`TRACKER_TEST_MOVE_RENAME_DELAY_SECONDS`).
- `T.rratc` Renumber recovery and tag conveniences (closed 2026-10-06):
  Renumbering writes its plan and phase to `.renumber.json` and finishes an
  interrupted one on the next load (`TRACKER_TEST_RENUMBER_INTERRUPT`).
  `tracker TAG COMMAND` uses the tag's collection; `show` prints everything
  about an item.  A rename that changes a tag offers to update writable `.md`
  files using the old one (hidden directories and symbolic links skipped).
  Closed items leave `Startup.md`; the generated `TASKS/Closed.md` gives the 50
  most recent (`TRACKER_TEST_CLOSED_SUMMARIES`) with their `## Summary`, the
  rest by tag and title.  The purpose of tracker is focused context.

  Development: the tests are built in (`python3 tracker.py --test`) and every
  change gets tests; also `ruff check --config ../claude_notes/ruff.toml
  tracker.py`, `flake8 --config ../claude_notes/.flake8 tracker.py` and `mypy
  --strict tracker.py` (79 columns).  Coverage: `python3 -m trace --count
  --missing --summary -C DIR --ignore-dir=/usr/lib tracker.py --test`; only
  `# pragma: no cover` lines may be missed.  Try changing commands in a scratch
  directory, never on the real items.
- `T.cdp` Create a Development Plan (closed 2026-10-05):
  Turned `tracker.py` (a copy of `claude_notes/task.py`) into a plan to
  match `README.md`: Items with Title, Number, State, a tag and optional
  priority; one collection per class of Item (`TASKS/`, `ISSUES/`), each
  marked by `.tracker.json`; per-item metadata in `.item.json`; a single
  `TASKS/Startup.md` of `@` imports.  The work became tasks 2 to 6
  (`T.c`, `T.smic`, `T.asfi`, `T.msfhn`, `T.rratc`).
