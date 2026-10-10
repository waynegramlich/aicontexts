# Summary of `I.gacrf` Generate the AI Contexts Rules file

The rules for using `ai_contexts` are now `RULES_TEXT` in
`ai_contexts.py`; every run (and `NAME create`) writes them as
`AI_Contexts_Rules.md` into every collection, rewriting only a copy that
differs, and `tag_references()` skips those copies.  `CLAUDE.md` imports
one copy (`@TASKS/AI_Contexts_Rules.md`) and only files known to exist;
`check_claude_imports()` reports an import of a missing file (paths with
a `/` or `.` only).  The text was reviewed on the way in (no `README.md`
or `hg` references; it lists the generated files).  The top-level
`AI_Contexts_Rules.md` is gone; `README.md`, `REFERENCE.md` and `-h`
were updated.  Follows from `T.rrt`.
