# Summary of `T.smic` Support Multiple Item Collections

A collection is any directory holding `.tracker.json`, found in the
current directory or the nearest parent that has any.  Commands are
`tracker COLLECTION COMMAND ...`; collection and command names take any
unique case-insensitive prefix, and an ambiguous one lists the options.
`tracker NAME create` makes a collection (name as typed, beside the others,
after a yes/no prompt).  `--help`/`--test` are options.  The one
`TASKS/Startup.md` covers every collection (e.g. `@../ISSUES/...`).
