# Tracker: General Purpose Tool for Tracking Items

The `tracker` program manages directories of Items.  It can be used to manage
Issues (i.e. bugs), Tasks (i.e. chunks of work), etc.  Each class of Item is
an independent collection that lives in its own directory (e.g. `ISSUES/`,
`TASKS/`.)  A collection directory is marked by a hidden `.tracker.json`
file, and is created (after asking) with `tracker NAME create`.

Every command names its collection first: `tracker COLLECTION COMMAND ...`.
Collection and command names can be shortened to any unique prefix, in any
case, so `tracker t cl 2` closes item 2 in `TASKS/`.  `tracker` looks for
collections in the current directory, or else the nearest parent directory
that has any, so it works from anywhere inside a project.

Each Item is stored in a dedicated sub-directory (e.g. `TASKS/1.2.3_Title/`)
with the following information:
* Title:
  A short one line description of the item (e.g. `Initialization Fails`.)
* Number:
  A unique hierarchical number (e.g. `1.2.3`) giving the Item's place in
  the tree.  There are never gaps: if `1.3` exists, so do `1.1` and
  `1.2`.  Items can be created or moved to the next free number of a
  level, or `before` or `after` an existing Item, and the others are
  renumbered to make room or close the gap.  Numbers change as Items are
  created, deleted and moved, so they are never used in text; tags are.
* Tag:
  A short name: the capitalized first letter of the collection and a
  period, then the first letter of each word of the Title in lower case,
  ignoring "a", "an", "of" and "the" (e.g. `Division by Zero is Bad` in
  `ISSUES/` is `I.dbzib`.)  Collections must start with different
  letters.  A tag is unique within its collection; when it would clash,
  the newer Item gets the lowest free number added (e.g. `I.cde2`.)  A
  tag never changes on its own, since tags show up in commit messages and
  the like.  Text refers to Items by tag, never by number, and commands
  accept a tag wherever they take a Number.
* Priority:
  An optional level: 0 (catastrophic), 1 (high), 2 (medium) or 3 (low).
  Priority is enabled per collection (`tracker i enable priority`); then
  `ls` shows it and lists Items by priority first.
* State:
  The state of the item: Pending, Open, Reference, Suspended, Closed or
  Rejected (decided against; otherwise treated like Closed).
  New items start out Pending.  A Reference item is not being worked on,
  but its `Context.md` is still loaded like an Open item's.
* `Details.md`:
  A file edited by a human that textually describes the item.  Its first
  line is a heading with the Number and Title (e.g. `# 1.2.3 Title`.)
* `Context.md`:
  A file managed by an AI LLM that has additional AI context information.
* `Summary.md`:
  A short summary of what the Item settled, written by the AI LLM before the
  Item is closed.  Its first line (``# Summary of `T.fbm` Title``) is kept up
  to date by `tracker`.
* `.item.json`:
  A hidden file managed by `tracker` that holds the State, Tag, Priority,
  the created and updated times (in UTC), and a history of every State
  change.

Every time `tracker` runs, it rewrites `TASKS/Startup.md`.  It contains only
Claude Code `@` imports: one for the `Details.md` of every Item that is not
Closed, plus one for the `Context.md` of every Open or Reference Item, for
every collection (e.g. `@../ISSUES/1_Crash/Details.md`).  Then come the
`Summary.md` files of the 50 most recently closed Items, newest first (their
`Details.md` if the summary is still empty), and finally, if there are older
closed Items, `TASKS/Closed.md`, which `tracker` writes to list them by tag
and title only.  (The test suite changes the 50 with
`TRACKER_TEST_CLOSED_SUMMARIES`.)  Adding
`@TASKS/Startup.md` to `CLAUDE.md` loads them at the start of each AI
session.

There is no undo; use a version control system.  Before a move or rename,
if the collection has had no move or rename for over an hour (the time is
kept in its `.tracker.json`), `tracker` recommends taking a snapshot first
(e.g. `git commit`) and asks whether to continue.  The test suite
shortens the hour with the `TRACKER_TEST_MOVE_RENAME_DELAY_SECONDS`
environment variable.

A tag can stand in for its collection: `tracker I.dbzib close` is the same
as `tracker ISSUES close I.dbzib`.  `tracker t show T.fbm` (or `tracker
T.fbm show`) shows everything about an Item: its number, tag, state,
priority, times, state history, directory and `Details.md`.  When a rename
changes a tag, `tracker` lists the writable `.md` files in the project
that use the old tag and offers to update them.

`tracker t ls` leaves out Closed Items (unless asked for by number or tag)
and says how many it left out; `tracker t ls -a` lists them all.

A renumbering (from a create, delete or move) first writes its plan to a
hidden `.renumber.json` in the collection.  If it is interrupted, the next
`tracker` command finishes it and says so.  Every command also checks the
collections it loads, so nobody has to remember to: it fixes what `tracker`
maintains (the number in the `# N Title` heading of `Details.md`, the
heading of `Summary.md`) and reports what a person maintains (a missing
heading, a title edited so that it no longer matches the directory name,
two Items with the same tag), saying how to fix it.

Run `tracker` with no arguments to list the collections, one line each, and
`tracker -h` to list the commands.  `tracker t ls -l` also lists the created
and updated times in the local time zone.
