# Summary of `T.hciacos` Hide closed items and check on startup

`ls` hides Closed items unless `-a`/`--all` (or the item is named) and says
how many it hid.  Every load runs `check_items()`: it fixes the number in a
`Details.md` heading and stale `Summary.md` headings, and reports a missing
heading, a title that no longer matches its directory, and shared tags, with
the command that fixes each.  Checking every time costs about 0.2 s per 2000
items, so there is no "check every N hours" timestamp; revisit if
collections reach ~10,000 items.
