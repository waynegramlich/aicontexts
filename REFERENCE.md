# AI Contexts Reference

Design notes on `ai_contexts.py`, written by Claude (an AI), mostly for
Claude to read before changing the program.  They are terse, and they
record what the code does not say: the decisions and why they were
made.  `README.md` is the user's manual; `ai_contexts -h` lists the
commands.

## Collections

* A collection is a directory holding `.ai_contexts.json` (its type,
  `priority` flag and last move time).  The name's first letter gives
  the tag prefix (`TASKS` -> `T.`), so first letters must differ.
* `find_collections()` globs `*/.ai_contexts.json` in the current
  directory and then each parent, stopping after a directory with
  `.git` or `.hg` (`VERSION_CONTROL_NAMES`), which is still checked;
  without one it goes to `/`.  Symbolic links are skipped in every
  path component.  No clocks, budgets or skip lists: kept simple and
  deterministic.
* Types (`TYPES`): "items" (default) and "rules".  A type sets the
  states, new state, finished states, `Context.md` states, commands,
  item files and whether it is in `Startup.md`.  A collection named
  `RULES` is "rules" on creation; otherwise `type` while empty.  A new
  type is a new `TYPES` entry.

## Items

* Directory `NUMBER_Title_Words/` with `Details.md` (heading `# NUMBER
  Title`, kept by `ai_contexts`), `Context.md`, `Summary.md` (heading
  ``# Summary of `TAG` Title``, kept) and `.item.json` (state, tag,
  priority, UTC `created`/`updated`, state `history`, transfer `moves`;
  for a rule also title, source, SHA-256 and `refreshed`).
* Every load runs `check_items()` (about 0.2 s per 2000 items, so no
  "check every N hours"): it fixes what `ai_contexts` keeps and reports
  what a person keeps (a missing heading, a title that no longer
  matches its directory, a shared tag), with the fixing command.

## Numbers

* Hierarchical, never with gaps (hand-made gaps are renumbered on
  load).  Places: next free number, `before N`, `after N`.
* Renumbering writes its plan and phase to `.renumber.json`; an
  interrupted one is finished on the next load.
* No undo (built once, then removed): version control is the undo.  A
  move, rename or transfer over an hour after the last
  (`MOVE_RENAME_DELAY_SECONDS`) recommends a snapshot and asks.

## Tags

* First letter of each title word, lower case, skipping a/an/of/the.
  Unique per collection and stable, since they appear in commit
  messages: on a clash the newer item gets the lowest free number
  (`cde2`).
* Text writes `TAG~NUMBER`; the `~NUMBER` is never updated (it is
  history) and commands ignore it.  Tags are never abbreviated.
* A rename or transfer that changes tags offers to update the `.md`
  files using the old ones (`update_references()`), in one pass.
  `tag_references()` searches only the collections and the `.md` files
  beside them, skipping hidden directories, links and the
  `AI_Contexts_Rules.md` copies, in sorted order; it prints a `grep`
  hint for anywhere else.  Old tags are never looked up.

## States and Startup

* Items: Pending (new), Open, Reference, Suspended, Closed, Rejected.
  Finished (`FINISHED_STATES`): Closed and Rejected, hidden by `ls`
  unless `-a`.  `Context.md` is loaded while Open or Reference.
* `write_startup()` writes `TASKS/Startup.md`, `@` imports only: the
  `Details.md` of unfinished items, `Context.md` per above, then the
  `Summary.md` (or `Details.md` if empty) of the `CLOSED_SUMMARIES`
  (50) most recently finished, newest first; older ones go in
  `TASKS/Closed.md` by tag and title.  A finished child is included
  only while its parent is Reference (`SUMMARY_PARENT_STATES`);
  otherwise the parent speaks for it and it is left out entirely.
* `ls -l` sizes come from `startup_sizes()`, which uses the same
  `startup_files()`, so they always match what is loaded.
* Generated files start with `GENERATED_COMMENT`; Claude Code strips
  HTML comments from imports, so it costs no tokens.

## Transfers

* `transfer` moves items (with children) to a collection of the same
  type.  The tag gets the new prefix and keeps the rest unless taken; a
  transfer back regains a free old tag.  Title, state, history,
  priority and files are kept; `moves` records it.
* The plan goes in `.transfer.json` in the source collection, and
  `do_transfer()` runs four repeatable phases; every load finishes an
  interrupted one first (`recover_transfers()`).

## Rules

* Claude Code will not import a file outside the project without
  approval, so each rule's `Details.md` is a read-only copy of its
  source (kept relative to the project, directories resolved).  The
  title lives in `.item.json`, since the copy keeps the source's
  heading.
* Every run refreshes the copies by SHA-256: a changed source is copied
  (via a temporary file); a copy edited in place is kept and reported
  (`refresh` replaces it after asking); a missing source keeps the last
  copy.  The copies are in version control, so a shared rule's change
  shows as a diff in every project.
* `write_active_rules()` writes `RULES/Active_Rules.md` importing the
  Active copies in number order.
* `screen_sources()` (for `create`, `source` and `copy`) refuses a name
  not ending in `.md`, a hidden or reserved name, and `CLAUDE.md` /
  `CLAUDE.local.md`; `source_doubts()` flags a capitalized stem (e.g.
  `README`) or an `@` import, asked about in one `[y/N]` question.
* Every run reports a rule without a source, an Active rule without a
  copy, an `@` import in a copy, and a copy that `CLAUDE.md` also
  imports; such problems end with `AI_REPORTS`.

## The AI's Rules

* `RULES_TEXT` is written as `AI_Contexts_Rules.md` into every
  collection on every run (only when it differs), so it always matches
  the program.  It holds only policy; command syntax lives in `HELP`,
  and what to answer or do lives in the prompts and messages
  themselves, at the point of need.
* `check_claude_imports()` reports a `CLAUDE.md` import (with a `/` or
  `.`) of a missing file: `CLAUDE.md` imports only files known to
  exist.

## Testing

* `ai_contexts_test.py` (`aic --test`); every change gets tests.
  Environment variables shorten things for it:
  `AI_CONTEXTS_TEST_CLOSED_SUMMARIES`,
  `AI_CONTEXTS_TEST_MOVE_RENAME_DELAY_SECONDS` and
  `AI_CONTEXTS_TEST_RENUMBER_INTERRUPT`.
* Windows and macOS lessons (read-only files, `\r\n`, path printing and
  sorting, `/` globbing) are in `R.gwr`'s "What the Other Systems
  Find".
