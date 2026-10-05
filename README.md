# Tracker: General Purpose Tool for Tracking Items

The `tracker` program manages directories of Items.  It can be used to manage
Issues (i.e. bugs), Tasks (i.e. chunks of work), etc.  Each class of Item
lives in its own directory (e.g. `ISSUES/`, `TASKS/`.)

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
the `Context.md` of every Open or Reference Item.  Adding `@TASKS/Startup.md`
to `CLAUDE.md` loads them at the start of each AI session.

Run `tracker help` to list the commands.  `tracker ls -l` also lists the
created and updated times in the local time zone.
