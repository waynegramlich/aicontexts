# 7 Explore Having a Rules Collection

<!-- --------------------------- 79 characters ---------------------------- -->

## Goal

Load rule `.md` files that live elsewhere in the file system (e.g.
`../claude_code_rules/Version_Control_Rules.md`) at the start of every
Claude Code session, without editing `~/.claude.json`.  Claude Code will
not import a file outside the project (even through a symbolic link)
without approval, so `tracker` copies each rule into a `RULES/` collection
and `RULES/Active_Rules.md` imports the copy.

## Collection Types

Today every collection behaves the same way: the same states, the same
files in each item, and the same treatment in `Startup.md`.  A rules
collection behaves differently, so each collection gets a type, kept in its
`.tracker.json` (`"type": "items"` or `"type": "rules"`).  A missing type
is `items`, so the existing collections are unchanged.

The types are built into `tracker.py` as a table.  For each type it says:

* The states, and which one a new item starts in.
* Which states are finished (left out by `ls`, summarized at startup).
* Which states get their `Context.md` imported.
* Which files an item has (`Details.md`, `Context.md`, `Summary.md`).
* What is imported for its items, and from where (`Startup.md` or
  `Active_Rules.md`).

| Type    | States            | New item | Files        | Imported          |
|---------|-------------------|----------|--------------|-------------------|
| `items` | Pending, Open,    | Pending  | `Details.md` | As now            |
|         | Reference,        |          | `Context.md` |                   |
|         | Suspended,        |          | `Summary.md` |                   |
|         | Closed, Rejected  |          |              |                   |
| `rules` | Active, InActive  | InActive | `Details.md` | The copy, when    |
|         |                   |          | the copy     | Active, by        |
|         |                   |          |              | `Active_Rules.md` |

A rule's `Details.md` says why the project uses the rule; it is not
imported.  Rules have no `Context.md` or `Summary.md`, and the checks that
add a missing `Summary.md` skip them.  This is the first step of `I.pss`.

`tracker RULES create` makes the collection as now; `tracker r type rules`
then sets its type.  The type can only be changed while the collection is
empty, so that no item is left in a state its type does not have.

## Rule Items

Each rule item keeps three more keys in its `.item.json`:

* `source`: The path of the rule's file, relative to the project root (the
  directory that holds the collections), e.g.
  `../claude_code_rules/Version_Control_Rules.md`.  `tracker` follows
  symbolic links when it reads it.
* `sha256`: The SHA-256 of the content last copied in.
* `refreshed`: When the copy was last written (UTC).

The copy sits in the item directory with the source file's name, e.g.
`RULES/1_Version_Control_Rules/Version_Control_Rules.md`.  A source whose
name clashes with an item file (`Details.md`, ...) is refused.  The copies
are tracked in `git` and `hg`: they are small, and a change to a rule then
shows up as a diff in every project that uses it.

## Refreshing

Every `tracker` run checks every rule item that has a source:

1. Hash the source and the copy.
2. If the copy's hash equals the source's, record it (if it is not already
   recorded) and stop.  This also repairs a run that was interrupted
   after the copy was written but before `.item.json` was.
3. If the copy exists and its hash differs from the recorded one, it was
   edited in place: report it and leave it alone.
4. If the source is missing, report it and keep the last copy.
5. Otherwise write the source's content to a temporary file in the item
   directory, rename it over the copy, record the new hash and time, and
   say `Refreshed R.vcr from ../claude_code_rules/...`.

Rules are a few KB, so hashing them every run costs nothing, and a hash is
not fooled by a checkout, a `cp` or clock skew the way a modification time
is.

## Active_Rules.md

Every `tracker` run writes `RULES/Active_Rules.md` (in each rules
collection) the way it writes `TASKS/Startup.md`: only `@` imports of the
copies of the Active rules, in hierarchical number order.  `CLAUDE.md`
imports it once (`@RULES/Active_Rules.md`, ahead of `@TASKS/Startup.md`)
and `Active_Rules.md` does the rest.  Rules are not in `Startup.md`.

Every rule must stand alone: a copy that contains an `@` import (outside
code spans and code blocks) of a file that exists (relative to the source)
is reported, since it would only pull in a file from outside the project
again.  An `@` that names no file (e.g. `@dataclass`) is not an import.

## Commands

* `tracker RULES create`, then `tracker r type rules`: make the collection.
* `tracker r create 1 FILE...`: make a rule item (InActive) from each
  FILE or glob pattern (see "Creating Rules from Files").
* `tracker r source R.vcr PATH`: set (or change) the source and copy it.
* `tracker r activate R.vcr` / `tracker r deactivate R.vcr`: change the
  state; `activate` refuses a rule with no copy.
* `tracker r refresh R.vcr`: copy the source over an edited copy, after
  asking, discarding the edit.
* `show` adds the source, hash and refresh time.  `ls` shows every rule
  (there is no finished state to hide).
* The state commands of the other type (`open`, `close`, ...) are refused
  in a rules collection, with a message listing its states, and the other
  way around.

## Checks Reported Every Run

* A rule with no source.
* A missing source (the last copy is kept).
* A copy edited in place (fixed with `refresh`).
* An Active rule with no copy.
* A copy that contains an `@` import.
* A copy with the same SHA-256 as a file `CLAUDE.md` imports directly.

## Steps

1. Collection types (the table, `type` in `.tracker.json`, the `type`
   command, per-type states), with tests.
2. Rule items: `create` from files, `source`, refreshing,
   `activate`/`deactivate`, `refresh`, `Active_Rules.md`, the checks, with
   tests.
3. Update `README.md`, `Tracker_Rules.md` and `tracker -h`.
4. In this project: take an `hg` checkpoint, remove the `RULES` symbolic
   link, make the `RULES` collection, add its rules, and import
   `@RULES/Active_Rules.md` in `CLAUDE.md`.

## Decided Questions

* OQ1: A rule's title does not come from its file's `# Heading` line; by
  default it comes from the file name (`Version_Control_Rules.md` is
  "Version Control Rules").
* OQ2: Defined out: every rule stands alone, and a copy with an `@` import
  is reported (see "Active_Rules.md").  Paths are resolved to real paths
  (no symbolic links) before they are compared or stored.
* OQ3: `tracker` warns when a rule copy has the same SHA-256 as a file
  `CLAUDE.md` imports directly (the same rule loaded twice).
* OQ4: The copies are read-only, to discourage editing them in place.
  `tracker` makes them writable just long enough to replace them.
* OQ5: `tracker RULES create` does not guess the type; `tracker r type
  rules` sets it.

## Creating Rules from Files

In a rules collection, `create` takes a place and one or more files or
glob patterns (e.g. `tracker r create 1 '../claude_code_rules/*.md'`); the
shell may expand the pattern itself, or `tracker` does when it is quoted.
Each file becomes its own rule, at the place and then the places after it,
titled from its file name, with its source set and its copy made.  The
pattern is only expanded when the rules are created; a file added to the
directory later needs its own `create`.
