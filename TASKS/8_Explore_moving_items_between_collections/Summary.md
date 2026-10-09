# Summary of `T.emibc` Explore moving items between collections

`tracker C transfer NUMBER COLLECTION [PLACE]` moves items (with children,
or a range of siblings) to another collection of the same type, by
default at its next free top-level number; both collections are
renumbered.  The tag gets the new prefix and keeps the rest unless it is
taken (then the lowest free number); a transfer back regains a free old
tag.  Title, state, history, priority and files are kept; each transfer
is recorded in `moves` in `.item.json` ("Transfers:" in `show`).  Old tags
are not looked up; `update_references()` offers to change every old tag
in the project's `.md` files in one pass (also used by `rename`).  The
plan goes in `.transfer.json` and `do_transfer()` runs it in four
repeatable phases; every `Items` load first finishes interrupted transfers
(`recover_transfers()`).  `do_renumber()` became a module function.
Documented in `README.md`, `Tracker_Rules.md` and `tracker -h`.
