# Summary of `T.rrt` Review README.md together

`README.md` is now a user's manual: the reader should think "useful and
not hard to use."  It opens with the three categories (Tasks, Issues,
Rules) and the benefit (switch the AI's context with your focus; the AI
does the bookkeeping and only summaries of closed work stay loaded),
then Getting Started (collections, `CLAUDE.md` lines, a first task,
tags, name shortening, hierarchical numbers, context files, a task's
life), States, Moving Things Around, Priorities, Other Conveniences,
Rules Collections and Installation.  Internals moved word for word to
`REFERENCE.md`, which `CLAUDE.md` does not import: `CLAUDE.md` only
points at content known to exist.  That rule led to `I.gacrf` (rules
text built into `ai_contexts.py` and written into every collection),
which also covers reviewing `AI_Contexts_Rules.md`; `I.ldsilt` limits
directory searches in large trees.
