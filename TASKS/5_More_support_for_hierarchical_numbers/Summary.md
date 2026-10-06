# Summary of `T.msfhn` More support for hierarchical numbers

Numbers never have gaps (if 1.3 exists, so do 1.1 and 1.2); they are
positions that change, so text uses tags only.  Tag prefixes are the
collection's capitalized first letter (`T.`, `I.`), unique across
collections; commands take a tag wherever they take a number.  `create` and
`move` take a place: the next free NUMBER, `before NUMBER` or `after NUMBER`.
`delete` is permanent, refuses children unless `-r` (which asks), and
renumbers.  Hand-made gaps are renumbered on load.  `rename NUMBER to
TITLE`.  Undo/redo was built and then removed: version control is the undo,
and a move or rename more than an hour after the last one recommends a
snapshot and asks to continue (`TRACKER_TEST_MOVE_RENAME_DELAY_SECONDS`).
