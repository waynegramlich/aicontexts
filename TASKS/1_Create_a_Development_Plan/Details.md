# 1 Create a Development Plan

Have a discussion with Claude about the previous work already done on
`tracker.py`.  Create a sequence of tasks to work flesh out future development.

The resulting plan:
* Task 2 (Cleanup): bring `tracker.py` into alignment with `README.md`.
* Task 3 (Support Multiple Item Collections): let `tracker`
  manage several independent collections of Items (e.g. `ISSUES/`,
  `TASKS/`), each in its own directory.
* Task 4 (Add support for Issues): create an Issues collection for
  tracking bugs, and settle anything Issues need that Tasks do not.
* Task 5 (More support for hierarchical numbers): keep item numbers free
  of gaps as items are deleted and moved around the tree (if 1.3 exists,
  1.1 and 1.2 must exist), with `delete`, `move`, `rename ... to ...`,
  `undo` and `redo` commands.
* Task 6 (Renumber recovery and tag conveniences): recover automatically
  from an interrupted renumber, offer to update `.md` files that refer to
  a tag changed by a rename, let a tag alone name its collection (e.g.
  `tracker I.dbzib close`), and add a `show` command.
* Task 7 (Review README.md together): review `README.md` together,
  section by section, so that it describes `tracker` accurately and reads
  well for a human.
