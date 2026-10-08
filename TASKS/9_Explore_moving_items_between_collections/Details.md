# 9 Explore moving items between collections

Explore moving an item from one collection to another (e.g. a Task that
turns out to be an Issue), including what happens to its tag prefix and to
the references to its old tag.

<!-- --------------------------- 79 characters ---------------------------- -->

## Design

### Command

A new `transfer` command, `transfer NUMBER COLLECTION [PLACE]`:

    tracker t transfer T.fbm issues             # next free top-level number
    tracker t transfer T.fbm issues 2.3         # a free NUMBER in ISSUES
    tracker t transfer T.fbm issues after I.cde # before/after an item there
    tracker T.fbm transfer i before 1           # the tag picks the source

COLLECTION is any unique prefix, as everywhere else.  NUMBER may be a
range of siblings (`1.2.5-6`), as for `move` now.  The item moves with all
of its children, and keeps their shape under its new number.  (`transfer`
and `type` both start with `t`, so `tr` is the shortest prefix.)

### What Is Allowed

Only between collections of the same type: a Task can become an Issue,
but an Issue can not become a rule (a rule needs a source, and has other
states and files).  A transfer to the same collection is refused; that is
`move`.

### What Changes

* Number: the item (and its children) get numbers in the target from the
  place; the source collection closes the gap and the target makes room,
  as `delete` and `create` do now.
* Tag: the prefix changes (`T.fbm` becomes `I.fbm`).  The rest of the tag
  is kept if it is free in the target, else it gets the lowest free number
  (`I.fbm2`), as `create` does.  Children's tags change the same way.
* References: like a rename, `tracker` lists the writable `.md` files that
  use each old tag and offers to change them (`T.fbm` to `I.fbm`) in one
  pass.  Commit messages can not be changed; the `moves` record (below)
  and `git log` say where an old tag went.
* Kept as is: title, state and its history, created time, `Details.md`,
  `Context.md` and `Summary.md` (its heading is fixed for the new tag).
  The updated time becomes now.
* Priority: kept in `.item.json`.  If the target does not have priority
  enabled it is not shown, and comes back if priority is enabled later.

### Old Tags

`.item.json` gets a `moves` list: `{"from": "T.fbm", "to": "I.fbm",
"time": ...}`, and `show` lists it.  Old tags are not looked up: a command
given an old tag treats it like any unknown tag.  A transfer back to the
first collection gets the old tag back if it is still free.

### Doing It Safely

Transferring an item and its children renames several directories from one
collection directory to another, then renumbers both.  As with
`.renumber.json` now, the whole plan is written first, to a hidden
`.transfer.json` in the source collection (the directory renames, the
new numbers and tags), and the next `tracker` run finishes an interrupted
transfer and says so.  Since both are sibling directories, every step is a
plain `rename` on the same file system.

Before a transfer, the reminder to take a version control snapshot works as
it does for `move` and `rename`.

### Steps

1. `transfer NUMBER COLLECTION [PLACE]`: planning, the type check, the
   directory renames and both renumberings, new tags, headings, the
   `moves` record and `show`, with tests.
2. `.transfer.json` and recovery from an interrupted transfer, with tests.
3. The offer to update references to the old tags, with tests.
4. `README.md`, `Tracker_Rules.md` and `tracker -h`.

### Decided Questions

* OQ1: A separate `transfer` command, not `move ... to COLLECTION`.
* OQ2: A live tag always wins (moot, since old tags are not looked up).
* OQ3: A transfer back gets the old tag back if it is still free.
* OQ4: Old tags are not looked up; the `moves` record and `git log` are
  enough.
