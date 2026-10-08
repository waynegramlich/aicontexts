# 1 Per-collection state sets

Every collection currently uses the same states (Pending, Open, Reference,
Suspended, Closed, Rejected).  Each type of collection may need its own set
of states.  For example, a Rules collection (`T.ehrc`) only needs Active
(loaded at startup) and InActive.  Decide how a collection declares its
states (probably in its `.tracker.json` configuration), which states
`Startup.md` loads, and what `ls` hides.
