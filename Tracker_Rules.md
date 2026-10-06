# Tracker Rules

<!-- --------------------------- 79 characters ---------------------------- -->

The `tracker` program is used to create and manage items in collections
such as `TASKS/` and `ISSUES/` (see `README.md`.)  `tracker` with no
arguments lists all of the commands.  Every command starts with the
collection, which (like the command) may be any unique prefix in any case.
The `create` command (e.g. `tracker TASKS create 1.2.3 New Task`, or
`tracker t cr 1.2.3 New Task`) creates an item directory (e.g.
`TASKS/1.2.3_New_Task/`) containing:

* `Details.md`:
   Edited by the human to describe the item.  Claude only edits it when
   asked to.
* `Context.md`:
   Edited by Claude to retain useful item context across sessions.  Claude
   edits it directly; there is no `tracker` command for it.
* `.item.json`:
   Managed by `tracker`.  Claude changes the state with the `pending`,
   `open`, `reference`, `suspend` and `close` commands (e.g.
   `tracker t close 2`), never by editing this file.

New items start out Pending.  The states are Pending, Open, Reference,
Suspended and Closed.  A Reference item is not being worked on, but its
`Context.md` is still loaded, so its context stays available.

Every time `tracker` is successfully run, it overwrites `TASKS/Startup.md`
with `@` imports of the `Details.md` of every item and the `Context.md` of
every Open or Reference item, in every collection, so that the
`@TASKS/Startup.md` import in `CLAUDE.md` loads them.
