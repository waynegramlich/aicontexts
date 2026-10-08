# Tracker Rules

<!-- --------------------------- 79 characters ---------------------------- -->

The `tracker` program is used to create and manage items in collections
such as `TASKS/` and `ISSUES/` (see `README.md`.)  `tracker` with no
arguments lists the collections, and `tracker -h` lists all of the
commands.  Every command starts with the collection, which (like the
command) may be any unique prefix in any case.
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

Each item has a tag (e.g. `I.dbzib` for "Division by Zero is Bad" in
`ISSUES/`), shown by `tracker t ls`; `tracker I.dbzib show` shows
everything about it.  Use the tag, in back quotes, to refer
to an item in Markdown text and commit messages; never use item numbers,
which change when items are deleted or moved.  Commands accept a tag
wherever they take a number (e.g. `tracker t close T.fbm`), and a tag
can stand in for its collection (`tracker T.fbm close`).  Renaming an item
can change its tag; `tracker` then lists the `.md` files that use the old
tag and offers to update them, and Claude answers yes (after checking the
list) so that every reference changes in the same pass.

Every `tracker` command checks its collections and prints what it fixed
and what needs fixing.  When it reports a problem, Claude fixes it (usually
with the `rename` command it suggests) or tells the user about it.

Item numbers never have gaps.  `create` and `move` take a place: the next
free number of a level (e.g. `1.3`), or `before NUMBER` / `after NUMBER`
(e.g. `tracker t move T.fbm after 2.1`, or `tracker t create before 1.1
Fix Big Mistake`).  `rename NUMBER to TITLE...` changes a title.  There is
no undo: when `tracker` recommends a version control snapshot before a
move or rename and asks whether to continue, Claude answers no, takes an
`hg` checkpoint, and then runs the command again.  `delete` is
permanent: it refuses an item with children unless given `-r` (which asks
first), and renumbers the later items.  Never run `delete` (or other
changing commands) on the real items just to see what happens; try it in
a scratch directory.

When priority is enabled for a collection (e.g. `tracker i enable
priority`, as it is for `ISSUES/`), items may have a priority set with
`tracker i priority NUMBER LEVEL`, and `ls` lists them by priority first:
* **0**: A catastrophic bug that must be avoided at all costs, such as a
  security hole or a defect that escapes to where nobody can fix it.
* **1**: A high priority that needs to be fixed quickly.
* **2**: A medium priority that needs to be fixed next.
* **3**: A low priority that gets put near the end of the list.
`-` removes the priority.

Before closing an item, Claude writes its `Summary.md` (below the heading
line that `tracker` maintains): what was decided and done, with the tags of
related items.  Once the item is closed, only that summary is loaded at
startup (and after the 50 most recently closed, only its tag and title, in
the generated `TASKS/Closed.md`), so it should be enough to know that the
item exists and what it settled.  `tracker T.fbm show` and the
item's files give the rest when needed.

New items start out Pending.  The states (of an "items" collection, like
`TASKS/` and `ISSUES/`) are Pending, Open, Reference, Suspended, Closed and
Rejected.  A Reference item is not being worked on,
but its `Context.md` is still loaded, so its context stays available.  A
Rejected item was decided against (`tracker i reject NUMBER`); it is
treated like a Closed one, and its `Summary.md` says why.

Every time `tracker` is successfully run, it overwrites `TASKS/Startup.md`
with `@` imports of the `Details.md` of every item and the `Context.md` of
every Open or Reference item, in every collection, so that the
`@TASKS/Startup.md` import in `CLAUDE.md` loads them.

`RULES/` is a rules collection (`tracker r type` prints a collection's
type).  Each rule is a read-only copy of a source file elsewhere (e.g.
`../claude_code_rules/Version_Control_Rules.md`), made and refreshed by
`tracker`; its states are Active and InActive (`tracker r activate R.vcr`,
`tracker r deactivate R.vcr`).  `tracker` writes `RULES/Active_Rules.md`,
which imports the Active rules, and `CLAUDE.md` imports it.  Claude never
edits a rule's copy: a change to a rule is made in its source (and only
when asked), and the next `tracker` run copies it.  New rules come from
files with `tracker r create PLACE FILE...`, and `tracker r source R.vcr
FILE` changes a rule's source.  When `tracker` reports a copy edited in
place, a missing source, an `@` import in a rule or a rule that `CLAUDE.md`
also imports, Claude tells the user rather than fixing it with `refresh`.
