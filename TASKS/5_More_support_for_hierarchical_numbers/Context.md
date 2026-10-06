# LLM Agent Context Log

## 2026-10-05 Design discussion

Rule: no gaps in any level; if 1.3 exists, 1.1 and 1.2 exist.  Numbers
are positions and may change; tags are the stable names.

Decisions:
1. `delete NUMBER` fails if the item has children.  `delete -r NUMBER`
   (or `--recursive`) deletes the subtree after the prompt
   "Do you really want to delete N items Yes(y) or No(n)."  Later
   siblings (and their subtrees) are renumbered down by one.
2. `move RANGE before|after NUMBER` (e.g. `move 1.2.5-6 before 1.1`):
   RANGE is consecutive siblings (or one number), each with its subtree;
   numbers refer to the tree before the move; no gaps afterwards.
3. `rename NUMBER to WORD...`: `to` is required.
4. `create` fails if the number exists or would leave a gap.
5. Gaps already on disk: tell the user to run a `renumber` command.
6. Undo/redo covers `move` and `rename` only.  Create/delete is a fence:
   it clears the undo/redo history, and undo can not cross it.
7. `undo [N]` / `redo [N]` are per collection, stored in `.tracker.json`;
   a new change discards the redo stack.
8. Numbers are never used in text; tags are.  Tags will get a
   per-collection prefix defined at create time (e.g. `T.` for tasks,
   `I.` for issues), so text says `T.fbm` (Task 1.2 Fix Big Mistake).

A. Positions for `create` (the user's example; keep this wording).  Tree:
   1, 1.1, 1.2, 2, 2.1.  Create of any preexisting node always fails:
   `create 1.2` fails.  `create 1.3` succeeds.  `create 3` succeeds.
   `create before 1.1` moves 1.2=>1.3 and 1.1=>1.2 and a new 1.1 is
   created.  `create after 1.1` moves 1.2=>1.3 and creates a new 1.2.
   `move` behaves like `create` (`move RANGE NUMBER`, `move RANGE before
   NUMBER`, `move RANGE after NUMBER`): the moved item takes over the
   position of the old NUMBER and everything after it is adjusted so
   that there are no gaps.

Further answers (supersede 5 above: there is no `renumber`):
B. Gaps never occur; tracker never creates them.
C. There is no `renumber` command.
D. State and priority changes are fences that undo can not cross.
E. The tag prefix is the first letter of the collection directory plus a
   period ("ISSUES" -> "I.", "TASKS" -> "T.").  It must be unique, so
   once `TASKS` exists, creating `TROUBLE` fails.
F. `delete` lists the deleted items and says "do `tracker COLLECTION
   undo` to undo the mistake".  `delete` accepts ranges (`1.2.5-6`, the
   last part greater than the previous).
G. Order: (1) tag prefixes, (2) `delete` -> user commits; then
   (3) `create`/`move` positions, `rename ... to`, and undo/redo together.
H. Reconsidered: `delete` is permanent and a fence (so no "undo" hint
   from F).  `delete -r` keeps its "Do you really want to delete N items
   Yes(y) or No(n)." prompt.
I. A gap made by hand (e.g. a removed directory) is renumbered
   automatically, with an error message listing the gaps found and each
   item's new number.
J. The prefix letter is always capitalized (so uniqueness is effectively
   case-insensitive), to make tags easy to spot in text.
K. `ls` shows the full tag, e.g. `T.fbm` (easy to search for in `.md`
   files).
L. Commands accept a tag in place of a number (`tracker t close T.fbm`).
M. `undo N` / `redo N` with fewer than N steps available refuses and
   changes nothing.

## 2026-10-05 Progress: G.1 tag prefixes and G.2 delete (done)

* `tag_prefix(name)`, `Items.prefix`; tags stored bare in `.item.json`,
  shown with the prefix.  `Items.resolve(word)` takes a number or a tag
  (with or without prefix, any case); used by every command.  Creating a
  collection whose prefix clashes fails ("tools" vs "TASKS").
* No gaps: `create` refuses an existing number, a missing parent, or a
  number past the next free one (and says which is free).
* `Items.gap_free_names()` / `renumber()` (two-phase rename through
  `.renumber_N` temp names, then rewrites the `# N Title` heading).
  `fix_gaps()` runs on every load and reports gaps made by hand.  An item
  whose parent is missing joins its nearest existing ancestor.
* `delete [-r] NUMBER|TAG|RANGE` (`resolve_range()`, e.g. `1.2.5-6`):
  refuses children without `-r`; `-r` asks "Do you really want to delete
  N items Yes(y) or No(n)."; prints the deleted and renumbered items.
  Delete is permanent (a fence once undo exists).
* Test fixtures rewritten without gaps; new `_test_numbering`.
  244 checks; coverage misses only `# pragma: no cover` lines.
* Mistake: Claude ran `./tracker t del 1` on the real TASKS as a "demo";
  it deleted task 1.  Restored from the hg checkpoint (verified only the
  headings had changed).  Demos now go in a scratch directory.
* Next (after the user's commit): G.3 positions for `create`/`move`
  (`before`/`after`), `rename ... to`, and undo/redo.

## 2026-10-05 Progress: G.3 places, move, rename to, undo/redo (done)

* `Items.plan_place(moving, place, target)` plans every renumbering:
  builds ordered child lists, removes the moving siblings (in place!),
  inserts them (or `NEW_ITEM`) at the free number / before / after the
  target (names as before the move), then renumbers the whole tree.
* `create [before|after] NUMBER TITLE` (`create_at_place`, `make_item`);
  `move RANGE [before|after] NUMBER` (`move_items`); `rename NUMBER to
  TITLE` (`to` required).  Output: "Renumbered (old number first):" with
  aligned `old -> new` columns (`print_items(old_numbers=...)`).
* Undo/redo: `.tracker.json` keys "undo"/"redo", lists of steps
  `{"command": "move", "renumbered": [[old, new], ...]}` or
  `{"command": "rename", "number", "old": [title, tag], "new": [...]}`.
  `record()` (limit `UNDO_LIMIT` = 100, clears redo), `clear_history()`
  (fences: create, delete, real state change, priority change, gap fix),
  `step_history(count, undo)` saves after every step; damaged history
  (bad JSON shape, missing items, a move that would leave gaps) is
  reported, not applied.  Fewer than N steps: refused.
* Bugs found by the new tests: `plan_place` replaced a list that was
  still referenced; `renumber` overwrote dict entries when a new name was
  another item's old name.  Both fixed.
* 306 checks; coverage misses only `# pragma: no cover` lines (a new
  `_test_write_failures` covers the write-error returns).

## 2026-10-06 Undo/redo removed

* The user decided undo/redo was not worth it (~10% of `tracker.py`);
  version control is the undo.  Removed: `undo`/`redo` commands,
  `record()`, `clear_history()`, `step_history()`, `history_command()`,
  `UNDO_LIMIT`, the fence calls, and their tests.  (Undo across a delete
  had never been built: delete was already permanent.)
* Instead: `move_command()` / `rename_command()` call
  `remind_to_snapshot()` before the operation and
  `note_move_or_rename()` after it, which saves
  `"last_move_or_rename": <UTC stamp>` in `.tracker.json`.  If there is
  no (valid) stamp or it is at least `MOVE_RENAME_DELAY_SECONDS` (3600)
  old, a reminder to take a version control snapshot goes to stderr; the
  operation still runs.  `TRACKER_TEST_MOVE_RENAME_DELAY_SECONDS`
  (`DELAY_VARIABLE`) overrides the delay; a non-number is ignored.
  Only the command layer reminds, so direct method calls in tests are
  quiet.
* 283 checks; coverage misses only `# pragma: no cover` lines;
  `tracker.py` went from 2885 to about 2715 lines.
* 2026-10-06 follow-up: the reminder now asks "Continue? Yes(y) or
  No(n)." (`confirm_snapshot(ask)`); anything but y/yes (or EOF) gives
  "Not moved" / "Not renamed".  `move_command()` plans the move and
  `rename_command()` checks the item and title first, so a command that
  would fail anyway is not asked about.  291 checks; full coverage apart
  from `# pragma: no cover`.
