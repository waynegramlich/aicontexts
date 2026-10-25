# AI Contexts Reference

The details of how `ai_contexts` works, for anyone who needs more than
`README.md` gives.  `ai_contexts -h` lists every command.

## Items

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
  the like.  Text refers to an Item by its tag, `~` and its Number when
  the text was written (e.g. `I.dbzib~3`), never by Number alone.  The
  `~NUMBER` is only a help in finding the Item's directory: it is never
  updated, so it records history and may be out of date.  Commands
  accept a tag (with or without a `~NUMBER`, which is ignored) wherever
  they take a Number.
* Priority:
  An optional level: 0 (catastrophic), 1 (high), 2 (medium) or 3 (low).
  Priority is enabled per collection (`ai_contexts i enable priority`);
  then `ls` shows it and lists Items by priority first.
* State:
  The state of the item: Pending, Open, Reference, Suspended, Closed or
  Rejected (decided against; otherwise treated like Closed).
  New items start out Pending.  A Reference item is not being worked on,
  but its `Context.md` is still loaded like an Open item's.  (A rule's
  state is Active or InActive instead.)
* `Details.md`:
  A file edited by a human that textually describes the item.  Its first
  line is a heading with the Number and Title (e.g. `# 1.2.3 Title`.)
* `Context.md`:
  A file managed by an AI LLM that has additional AI context information.
* `Summary.md`:
  A short summary of what the Item settled, written by the AI LLM before the
  Item is closed.  Its first line (``# Summary of `T.fbm` Title``) is kept up
  to date by `ai_contexts`.
* `.item.json`:
  A hidden file managed by `ai_contexts` that holds the State, Tag, Priority,
  the created and updated times (in UTC), and a history of every State
  change, and of every transfer to another collection; for a rule, also
  its Title, its source, the SHA-256 of its copy (its `Details.md`) and
  when the copy was refreshed.

<!-- Let's mostly focus on the stuff above. -->

Every time `ai_contexts` runs, it rewrites `TASKS/Startup.md`.  It contains
only Claude Code `@` imports: one for the `Details.md` of every Item that is
not Closed, plus one for the `Context.md` of every Open or Reference Item, for
every collection (e.g. `@../ISSUES/1_Crash/Details.md`).  Then come the
`Summary.md` files of the 50 most recently closed Items, newest first (their
`Details.md` if the summary is still empty), and finally, if there are older
closed Items, `TASKS/Closed.md`, which `ai_contexts` writes to list them by
tag and title only.  (The test suite changes the 50 with
`AI_CONTEXTS_TEST_CLOSED_SUMMARIES`.)  Adding `@TASKS/Startup.md` to
`CLAUDE.md` loads them at the start of each AI session.  Rules are not in
`TASKS/Startup.md` (see "Rules Collections".)

There is no undo; use a version control system.  Before a move, rename or
transfer, if the collection has had none for over an hour (the time is kept in
its `.ai_contexts.json`), `ai_contexts` recommends taking a snapshot first
(e.g. `git commit`) and asks whether to continue.  The test suite shortens the
hour with the `AI_CONTEXTS_TEST_MOVE_RENAME_DELAY_SECONDS` environment
variable.

A tag can stand in for its collection: `ai_contexts I.dbzib close` is the same
as `ai_contexts ISSUES close I.dbzib`.  `ai_contexts t show T.fbm` (or
`ai_contexts T.fbm show`) shows everything about an Item: its number, tag,
state, priority, times, state history, directory and `Details.md`.  When a
rename changes a tag, `ai_contexts` lists the writable `.md` files that
use the old tag and offers to update them.  Only the collections (all the
way down) and the `.md` files directly in the directory that holds them
are searched, so a big project tree is never walked; a `grep` command is
suggested for anywhere else.  Hidden directories, the generated
`AI_Contexts_Rules.md` copies and anything reached through a symbolic
link are skipped, and the files are always searched in sorted order.

The collections are found in the current directory, or else the nearest
parent directory that has any.  The search stops at a version control
root (a directory with `.git` or `.hg`), still checking that directory
itself, so it never finds the collections of an enclosing project;
without one, it goes all the way to `/`.  A collection that is a
symbolic link is skipped.

An Item that belongs in another collection (e.g. a Task that turns out to
be an Issue) is moved there, with its children, by `ai_contexts t transfer
T.fbm issues [PLACE]`.  The PLACE is as for `move` (by default the next
free top-level number), and both collections are renumbered to leave no
gaps.  The tag gets the new collection's prefix (`T.fbm` becomes `I.fbm`),
and keeps the rest unless that is taken there (then it gets the lowest
free number, as for `create`); a transfer back gets the old tag back if it
is free.  The title, state and its history, priority and files are kept,
and the transfer is recorded in `.item.json` and shown by `show`.  Old
tags are not looked up, but, as for a rename, `ai_contexts` offers to
update every `.md` file that uses them, in one pass; this drops an old
tag's `~NUMBER` (`T.fbm~12` becomes `I.fbm`), since that number was in
the other collection.  Items can only be
transferred between collections of the same type.

`ai_contexts t ls` leaves out Closed Items (unless asked for by number or
tag) and says how many it left out; `ai_contexts t ls -a` lists them all.

A renumbering (from a create, delete or move) first writes its plan to a
hidden `.renumber.json` in the collection, and a transfer writes its plan
to a hidden `.transfer.json` in the collection it comes from.  If either
is interrupted, the next `ai_contexts` command finishes it and says so.
Every command also checks the collections it loads, so nobody has to
remember to: it fixes what `ai_contexts` maintains (the number in the `# N
Title` heading of `Details.md`, the heading of `Summary.md`) and reports
what a person maintains (a missing heading, a title edited so that it no
longer matches the directory name, two Items with the same tag), saying
how to fix it.

Run `ai_contexts` with no arguments to list the collections, one line
each, and `ai_contexts -h` to list the commands.  `ai_contexts t ls -l`
also lists the created and updated times in the local time zone.

Every run also writes `AI_Contexts_Rules.md`, the rules for using
`ai_contexts` that the AI loads, into every collection.  Its text is
built into `ai_contexts.py` (`RULES_TEXT`), so it always matches the
program and nothing else has to be installed; a copy that differs (such
as one edited by hand) is replaced, and one that matches is left alone.
`CLAUDE.md` imports one copy (e.g. `@TASKS/AI_Contexts_Rules.md`).  The
copies are skipped when a rename or transfer looks for `.md` files that
use an old tag.  Every run also reports an `@` import in `CLAUDE.md`
whose file does not exist (only an import that looks like a file, with a
`/` or a `.` in its path), since `CLAUDE.md` should only import files
that are known to exist.

## Rules Collections

A rules collection (e.g. `RULES/`) holds rules that Claude Code should
load at the start of every session, such as version control or coding
rules shared by several projects.  The rule files can live anywhere in
the file system, but Claude Code will not import a file outside the
project (even through a symbolic link) without approval, so `ai_contexts`
copies each rule into the project:

    ai_contexts RULES create
    ai_contexts r type rules
    ai_contexts r create 1 ../shared_rules/Version_Control_Rules.md \
                           ../shared_rules/Python_Coding_Rules.md \
                           ../shared_rules/Code_Marker_Rules.md
    ai_contexts r activate R.vcr

`create PLACE FILE...` makes one rule from each file (or glob pattern), at
PLACE and then after it, titled from the file name
(`Version_Control_Rules.md` is "Version Control Rules").  Each rule
directory holds only a `Details.md` and the `.item.json`, like a Task or
an Issue (which also have a `Context.md` and a `Summary.md`).  A rule's
`Details.md` is a read-only copy of its source file (e.g.
`RULES/1_Version_Control_Rules/Details.md` for
`../shared_rules/Version_Control_Rules.md`), so it starts with the
source's own heading, which `ai_contexts` leaves alone; the rule's title
is kept in `.item.json` instead.  (A rule made before this had a
heading-only `Details.md` and a copy with the source's name; the next
run moves it to the new layout.)  The source is kept relative to the
directory that holds the collections, with its directories resolved to
real ones; `ai_contexts r source R.vcr FILE` changes it.

Some files are not meant to be rules, and a glob like `*.md` can pick
them up.  `create` and `source` insist on a file whose name ends in
`.md`, and refuse a `CLAUDE.md` (or
`CLAUDE.local.md`) file, since Claude Code loads those by itself, and
nothing is created.  A file named in capital letters (like `README.md`)
is usually about the project, and a file with an `@` import of a file
does not stand alone, so they are listed in one question; unless the
answer is yes, they are skipped and the other files are used.

A new rule is InActive; `activate` (which needs a copy) and `deactivate` change
that.  Every time `ai_contexts` runs, it rewrites `RULES/Active_Rules.md` with
an `@` import of the copy of every Active rule, in number order, so adding
`@RULES/Active_Rules.md` to `CLAUDE.md` loads them.

Every run also refreshes the copies.  A copy that matches its source is
left alone; a changed source is copied again (to a temporary file that
then replaces the copy) and its SHA-256 is recorded.  A copy whose SHA-256
is no longer the recorded one was edited in place: it is reported and
kept, and `ai_contexts r refresh R.vcr` replaces it after asking.  A missing
source is reported, and the last copy is kept.  The copies are small and
are meant to be kept in version control, so a change to a shared rule
shows up as a diff in each project that uses it.

A rule must stand alone, so every run also reports a rule with no source,
an Active rule with no copy, an `@` import of a file in a copy (outside
code spans and blocks, relative to the source), and a copy that is the
same as a file that `CLAUDE.md` imports directly (the same rule loaded
twice).
