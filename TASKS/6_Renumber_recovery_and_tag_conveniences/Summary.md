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

Development: the tests are in `tracker_test.py` (`./tracker --test` or
`python3 tracker_test.py`) and every change gets tests; also `ruff check
tracker.py tracker_test.py`, `flake8 tracker.py tracker_test.py` (both use the
repository's 79-column `ruff.toml` and `.flake8`) and `mypy --strict
tracker.py tracker_test.py`.  Coverage: `python3 -m trace --count --missing
--summary -C DIR --ignore-dir=/usr/lib tracker_test.py`, then look for
`>>>>>>` in `DIR/*tracker.tracker.cover`; only `# pragma: no cover` blocks
may be missed.  Try changing commands in a scratch directory, never on the
real items.
