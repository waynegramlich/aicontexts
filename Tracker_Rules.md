# Tracker Rules

<!-- --------------------------- 79 characters ---------------------------- -->

The `tracker` program is used to create and manage items (see `README.md`.)
`tracker help` lists all of the commands.  When first used, it ensures that a
`TASKS/` sub-directory exists.  The `tracker create` command (e.g.
`tracker create 1.2.3 New Task`) creates an item directory (e.g.
`TASKS/1.2.3_New_Task/`) containing:

* `Details.md`:
   Edited by the human to describe the item.  Claude only edits it when
   asked to.
* `Context.md`:
   Edited by Claude to retain useful item context across sessions.  Claude
   edits it directly; there is no `tracker` command for it.
* `.item.json`:
   Managed by `tracker`.  Claude changes the state with `tracker pending`,
   `open`, `reference`, `suspend` and `close`, never by editing this file.

New items start out Pending.  The states are Pending, Open, Reference,
Suspended and Closed.  A Reference item is not being worked on, but its
`Context.md` is still loaded, so its context stays available.

Every time `tracker` is successfully run, it overwrites `TASKS/Startup.md`
with `@` imports of the `Details.md` of every item and the `Context.md` of
every Open or Reference item, so that the `@TASKS/Startup.md` import in
`CLAUDE.md` loads them.
