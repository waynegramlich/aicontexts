# Summary of `I.ldsilt` Limit directory searches in large trees

Settled on simple, bounded, deterministic searches (no clock, budgets,
breadth-first walks, `git ls-files` or skip lists, all judged too
complex).  `find_collections()` globs `*/.ai_contexts.json` going up and
stops after a version control root (`.git` or `.hg`, the names in
`VERSION_CONTROL_NAMES`), still checking that directory; without one it
goes to `/`.  `tag_references()` only searches each collection
(`rglob`) and the `.md` files directly in the project directory, and
`update_references()` prints a `grep -rnwF` hint for anywhere else.
Glob results are always sorted, and symbolic links are always checked,
in every path component (a linked collection is skipped too).
Documented in `README.md`, `REFERENCE.md` and `-h`.
