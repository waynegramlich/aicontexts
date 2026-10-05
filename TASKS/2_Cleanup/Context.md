# LLM Agent Context Log

## 2026-10-05 Cleanup (all steps done; step 4 moved to task 3)

What was done, by step in `Details.md`:
1. Rename: Task -> Item, Tasks -> Items, phrase -> title,
   status -> state, identifier -> number, `task.py` -> `tracker`.  Only
   the legacy `.status` name survives (`OLD_STATUS_FILE`, for migration).
2. `Pending` added; new Items start Pending.  New command
   `tracker pending [-r] NUMBER`.
3. `.status` replaced by `.item.json`.
5. `TASKS/Startup` renamed to `TASKS/Startup.md`; `CLAUDE.md` imports
   `@TASKS/Startup.md`.
6. Timestamps added; `tracker ls -l` / `list --long` shows `created` and
   `updated` in local time ("-" if missing, "?" if invalid).
7. `README.md` rewritten (typos fixed); new `Tracker_Rules.md`, imported
   by `CLAUDE.md` in place of `@RULES/Task_Tracking_Rules.md`.

Added after the steps: a `Reference` state (`tracker reference [-r]
NUMBER`).  `CONTEXT_STATES = ("Open", "Reference")` decides which
`Context.md` files `Startup.md` imports.

### `.item.json` format

```json
{
  "state": "Pending",
  "created": "2026-10-05T21:27:56Z",
  "updated": "2026-10-05T21:27:56Z",
  "history": [{"state": "Pending", "time": "2026-10-05T21:27:56Z"}]
}
```

* Times are UTC, `%Y-%m-%dT%H:%M:%SZ`.
* `updated` changes on any state change or rename.  A state change that
  changes nothing (e.g. `open` on an Open Item) is skipped entirely.
* Unknown keys are preserved, so tags can be added later.
* An old `.status` directory is migrated automatically on load, using
  the `.status` file's mtime for `created`/`updated`/history.
* Tasks 1 and 2 were backfilled by hand (created from file birth times:
  13:55 and 14:27 PDT on 2026-10-05).

### Code map (`tracker.py`)

* Module level helpers: `utc_stamp()`, `local_time()`, `new_metadata()`,
  `write_item()`, `read_item()` (does the `.status` migration),
  `update_item(directory, state="")` (sets `updated`, and appends to
  history if `state` is given), `parse_number()`, `clean_title()`,
  `parse_recursive()`, `print_items(items, long)`.
* `Item` dataclass: `name` (tuple of ints), `title`, `state`, `created`,
  `updated`; `number` property gives `"1.2.3"`.
* `Items` class: one collection (default `TASKS/`).  `items` and
  `directories` dicts keyed by the name tuple; `*_item()` methods do the
  work, `*_command()` methods parse arguments; `run_command()` dispatches
  and then always calls `write_startup()`.
* Tests are built in: `Items.test()` with `_test_*` static methods.

### How to check changes

```sh
python3 tracker.py test        # 121 checks at end of task 2
ruff check --config ../claude_notes/ruff.toml tracker.py
flake8 --config ../claude_notes/.flake8 tracker.py
mypy --strict tracker.py
```

Line length is 79.  Ruff flags `raise ValueError` inside an
`isinstance` check (TRY004) and naive `datetime.fromtimestamp()`
(DTZ006); the code is written to avoid both.
