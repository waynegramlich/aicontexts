# LLM Agent Context Log

## 2026-10-06 Implementation

* `ls` hides Closed items unless `-a`/`--all` or the item is the one
  named; it ends with "(N Closed items not shown; `ls -a` shows them)".
* `Items.check_items()` runs at the end of every load (after
  `fix_gaps()`).  Fixed (tracker-owned): a wrong number in the
  `# N Title` heading of `Details.md`, a stale or missing `Summary.md`
  heading.  Reported (human-owned), with the fixing command: a
  `Details.md` without the heading, a title that no longer matches the
  directory name, a tag shared by several items.  All to stderr; fixes
  happen once, reports repeat until fixed.
* Timing (synthetic 2000-item collection): `tracker t ls` took 0.44 s
  before the checks and 0.64 s with them, so checking every time is fine
  and no "last checked" timestamp was needed.  If collections ever reach
  ~10,000 items, revisit (check every N hours, as the user suggested).
* 355 checks; coverage misses only `# pragma: no cover` blocks.
