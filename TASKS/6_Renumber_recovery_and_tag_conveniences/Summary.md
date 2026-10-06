# Summary of `T.rratc` Renumber recovery and tag conveniences

Renumbering writes its plan and phase to `.renumber.json` and finishes an
interrupted one on the next load (`TRACKER_TEST_RENUMBER_INTERRUPT`).
`tracker TAG COMMAND` uses the tag's collection; `show` prints everything
about an item.  A rename that changes a tag offers to update writable `.md`
files using the old one (hidden directories and symbolic links skipped).
Every item has a `Summary.md` (its heading kept by tracker) that Claude
fills in before closing it.  `Startup.md` imports it for the 50 most recently
closed items (`TRACKER_TEST_CLOSED_SUMMARIES`; `Details.md` if it is empty),
and the generated `TASKS/Closed.md` lists older ones by tag and title.  The
purpose of tracker is focused context.

Development: the tests are built in (`python3 tracker.py --test`) and every
change gets tests; also `ruff check --config ../claude_notes/ruff.toml
tracker.py`, `flake8 --config ../claude_notes/.flake8 tracker.py` and `mypy
--strict tracker.py` (79 columns).  Coverage: `python3 -m trace --count
--missing --summary -C DIR --ignore-dir=/usr/lib tracker.py --test`; only
`# pragma: no cover` lines may be missed.  Try changing commands in a scratch
directory, never on the real items.
