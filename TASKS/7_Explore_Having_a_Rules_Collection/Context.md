# LLM Agent Context Log

## Goal

Load rule `.md` files that live outside the project (e.g.
`../claude_code_rules/Version_Control_Rules.md`) at startup without editing
`~/.claude.json`.  Claude Code will not import them through a symbolic link
(an external import needs approval), so `tracker` copies them in.

## Decisions (2026-10-07)

1. The `RULES` symlink (to `../claude_code_rules/`) is replaced by a `RULES/`
   collection (tag prefix `R.`).  Each Rule item records the path of its
   source file and `tracker` copies it into the item directory, keeping the
   source file's name; `Startup.md` imports the copy.
2. The copy is refreshed on every `tracker` run when the source is newer.
3. A missing source keeps the last copy and is reported on every run.
4. Rules use their own states: Active (like Open: loaded) and InActive.
   Per-collection state sets are `I.pss`.
5. Which files an item has (`Details.md`, `Context.md`, `Summary.md`) is part
   of some collection configuration (type), still to be designed.
6. The copies are tracked in `git` and `hg` (small; changes become visible).
7. Relative `@` imports inside a copied rule: TBD.
8. `Tracker_Rules.md` and `Version_Control_Rules.md` probably stay imported
   directly from `CLAUDE.md`.
9. `Python_Coding_Rules.md` will be renamed at its source, so the copy just
   keeps the source's name.

Setup is `tracker RULES create` (makes the collection) followed by other
commands to configure it and add rules.

## More decisions (2026-10-07)

* Rules load in hierarchical number order, ahead of other items.
* The source path is stored relative to the project root.
* `.item.json` keeps the SHA-256 of the last copy (and a timestamp of when it
  was refreshed); a copy whose SHA-256 no longer matches was edited in place
  and is not overwritten.
* Commands: `tracker r create 1 Title`, `tracker r source R.tag PATH`,
  `tracker r activate` / `deactivate`; `show` adds the source and refresh
  time.
* Ignore `ALT_VENV` in `hg status` (the user is returning to that project).

## Progress

* Step 1 (collection types) is done: `CollectionType` and `TYPES` in
  `tracker.py`; `type` in `.tracker.json` (missing is "items"); `tracker C
  type [TYPE]`, only while empty; each type's state commands (`commands()`
  filters prefix matching by the collection's type); a rule has only
  `Details.md`; rules are left out of `Startup.md`.  Tests in
  `_test_types()` in `tracker_test.py`.  `README.md` and `Tracker_Rules.md`
  are not updated yet (step 3).
* Step 2 (rule items) is done: `create PLACE FILE...` (globs, titles from
  file names), `source`, `refresh` (asks before replacing an edited
  copy), refreshing in `check_rules()` on every load, read-only copies
  written via `.copy.tmp`, `Active_Rules.md` (`write_active_rules()`), and
  the checks.  Only `@` imports of existing files (relative to the source)
  are reported, so `@dataclass` is not.  Tests: `_test_rules()` and
  `_test_rule_failures()`.
* `../claude_code_rules/Python_Coding_Rules.md` line 109 has a typo:
  `` `@dataclass" `` (backtick closed by a double quote).
* Step 4 is done: the `RULES` symlink is gone; `RULES/` is a rules
  collection with `R.vcr` (Active) and `R.pcr` (InActive), both from
  `../claude_code_rules/`.  `CLAUDE.md` imports `@RULES/Active_Rules.md`
  in place of `@Version_Control_Rules.md`; the root copy
  `Version_Control_Rules.md` is no longer imported.  Step 3 (docs) is
  still to do.
* Step 3 is done: `README.md` has collection types and a "Rules
  Collections" section; `Tracker_Rules.md` says how Claude treats
  `RULES/` (never edit a copy; report problems rather than `refresh`).
  The root `Version_Control_Rules.md` was deleted.  `R.pcr` stays
  InActive until the user rewrites it.
