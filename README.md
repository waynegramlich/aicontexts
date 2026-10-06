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
  A unique hierarchical number (e.g. `1.2.3`) used for sorting.
* State:
  The state of the item: Pending, Open, Reference, Suspended or Closed.
  New items start out Pending.  A Reference item is not being worked on,
  but its `Context.md` is still loaded like an Open item's.
* `Details.md`:
  A file edited by a human that textually describes the item.  Its first
  line is a heading with the Number and Title (e.g. `# 1.2.3 Title`.)
* `Context.md`:
  A file managed by an AI LLM that has additional AI context information.
* `.item.json`:
  A hidden file managed by `tracker` that holds the State, the created and
  updated times (in UTC), and a history of every State change.

Every time `tracker` runs, it rewrites `TASKS/Startup.md`.  It contains only
Claude Code `@` imports: one for the `Details.md` of every Item, plus one for
the `Context.md` of every Open or Reference Item, for every collection (e.g.
`@../ISSUES/1_Crash/Details.md`).  Adding `@TASKS/Startup.md` to `CLAUDE.md`
loads them at the start of each AI session.

Run `tracker` with no arguments to list the commands.  `tracker t ls -l` also
lists the created and updated times in the local time zone.
