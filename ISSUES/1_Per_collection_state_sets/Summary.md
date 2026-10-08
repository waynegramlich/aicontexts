# Summary of `I.pss` Per-collection state sets

Settled by collection types (`T.ehrc`): each collection's `.tracker.json`
has a `type` ("items", the default, or "rules") whose entry in `TYPES` in
`tracker.py` gives its states, new-item state, finished states (hidden by
`ls`), `Context.md` states, state commands, item files and what is loaded
at startup.  "items" keeps Pending, Open, Reference, Suspended, Closed and
Rejected; "rules" has Active and InActive (`activate`, `deactivate`).  A
new type is a new `TYPES` entry.
